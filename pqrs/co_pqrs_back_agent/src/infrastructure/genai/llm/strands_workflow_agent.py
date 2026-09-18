"""Strands-based agent wrapper for workflow answer validation and closing messages."""

from __future__ import annotations

import json
import time
import unicodedata
from collections.abc import Mapping
from typing import Any

from domain.conversation.models import Conversation, TokenUsage
from domain.genai.llm.models import (
    GroupRoutingDecision,
    StepOptionClassification,
    WorkflowAnswerValidation,
    WorkflowRoutingDecision,
)
from domain.workflow.group_prefilter import build_group_prefilter_prompt
from domain.workflow.models import WorkflowRoutingEntry, WorkflowStep
from domain.workflow.routing_prompt_builder import (
    build_routing_system_prompt,
    build_routing_user_prompt,
)
from guardrail import routing_scope_prompt_suffix
from infrastructure.core.config import load_env_constants
from infrastructure.core.logger import (
    get_logger,
    log_execution,
)
from infrastructure.entrypoint.api.errors.exceptions import (
    AgentExecutionError,
    ConfigurationError,
)
from infrastructure.observability.trace_audit import schedule_trace_event
from strands import Agent

# Claves de ``captured_data`` que son metadatos de analitica, no datos del
# cliente: no deben llegar al LLM ni a los resumenes que ve el usuario.
# "source" es la marca benchmark/live que persiste el agente al abrir la sesion.
_ANALYTICS_ONLY_CAPTURED_KEYS: frozenset[str] = frozenset({"source"})


def _business_captured_data(conversation: Conversation) -> dict[str, Any]:
    """``captured_data`` sin las claves que solo existen para la analitica."""

    return {
        key: value
        for key, value in (conversation.captured_data or {}).items()
        if key not in _ANALYTICS_ONLY_CAPTURED_KEYS
    }

logger = get_logger(__name__)

# Vocabulario de saludo/cortesia (normalizado: minusculas, sin acentos) usado por
# el ruteo local de respaldo para responder con calidez cuando el LLM remoto no
# esta disponible. Solo se consideran tokens de longitud >= 3 (ver
# _tokenize_routing_text), por eso aqui no hay palabras de 1-2 letras.
_FALLBACK_GREETING_TOKENS: frozenset[str] = frozenset(
    {
        "hola",
        "holaa",
        "holaaa",
        "ola",
        "hello",
        "hey",
        "buenas",
        "buenos",
        "buen",
        "dia",
        "dias",
        "tarde",
        "tardes",
        "noche",
        "noches",
        "saludos",
        "saludo",
        "cordial",
        "que",
        "tal",
        "como",
        "estas",
        "esta",
        "todo",
        "bien",
        "gracias",
        "muchas",
        "mil",
        "blue",
        "asistente",
        "bot",
    }
)

_GROUP_PREFILTER_SYSTEM_PROMPT = (
    "Eres un clasificador de CATEGORIAS para un asistente de PQRS bancario en espanol. "
    "Recibes el mensaje de un cliente y el catalogo de categorias con su criterio de ruteo. "
    "Devuelve las 2 categorias mas probables, la mejor primero, usando EXACTAMENTE las "
    "claves del catalogo. Ante la duda entre varias, incluye las dos mas plausibles en vez "
    "de arriesgar una sola. No clasifiques el tramite concreto: solo la categoria. "
    "Responde unicamente con la estructura solicitada."
)


class StrandsWorkflowAgent:
    """Encapsulate Strands calls used by the workflow engine."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        model_id: str,
        embeddings_model: str | None = None,
        ssl_verify: bool | str = True,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.model_id = model_id
        self.embeddings_model = embeddings_model
        self.ssl_verify = ssl_verify
        self.model: Any | None = None
        logger.info(
            "StrandsWorkflowAgent initialized endpoint=%s model_id=%s embeddings_model=%s ssl_verify=%s",
            self.endpoint,
            self.model_id,
            self.embeddings_model,
            self.ssl_verify,
        )

    @classmethod
    @log_execution
    def from_env(cls, env_path: str = ".env") -> StrandsWorkflowAgent:
        """Build the Strands workflow agent from environment variables."""

        constants = load_env_constants(env_path)
        required_keys = ("API_KEY", "ENDPOINT", "LLM_MODEL")
        missing_keys = [key for key in required_keys if key not in constants]

        if missing_keys:
            raise AgentExecutionError(
                "Missing required environment variables for the Strands agent.",
                details={"missing_keys": missing_keys},
            )

        return cls(
            api_key=constants["API_KEY"],
            endpoint=constants["ENDPOINT"],
            model_id=constants["LLM_MODEL"],
            embeddings_model=constants.get("LLM_EMBEDDINGS"),
            ssl_verify=cls._resolve_ssl_verify(constants),
        )

    @log_execution
    def _log_agent_response(
        self,
        *,
        conversation_id: str,
        agent_name: str,
        response_payload: str,
    ) -> None:
        """Log the model response with a stable marker that is easy to search."""

        logger.info(
            "AGENT_RESPONSE START agent=%s conversation_id=%s\n%s\nAGENT_RESPONSE END agent=%s conversation_id=%s",
            agent_name,
            conversation_id,
            response_payload,
            agent_name,
            conversation_id,
        )

    def _trace_llm(
        self,
        *,
        operation: str,
        outcome: str,
        conversation: Conversation,
        elapsed_ms: float | None = None,
        usage: TokenUsage | None = None,
        error: BaseException | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit a per-client observability trace for an LLM interaction.

        outcome: started | ok | error | fallback_no_output. Makes visible when
        the OpenAI/Azure call is (not) consumed and when we fall back locally.
        """

        response_summary: dict[str, Any] = {}
        if usage is not None:
            response_summary = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                # Por operacion se ve QUE llamada acierta el cache de prefijo.
                "cached_input_tokens": usage.cached_input_tokens,
            }
        schedule_trace_event(
            event_type="llm",
            operation=operation,
            outcome=outcome,
            elapsed_ms=elapsed_ms,
            target=self.model_id,
            conversation_id=conversation.conversation_id,
            customer_id=conversation.user_id,
            request_summary=dict(extra or {}),
            response_summary=response_summary,
            error_type=type(error).__name__ if error else None,
            error_message=str(error) if error else None,
            tags=["llm", operation, outcome],
        )

    @log_execution
    async def route_initial_workflow(
        self,
        *,
        conversation: Conversation,
        user_message: str,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> WorkflowRoutingDecision:
        """Route the first user message to the most likely workflow."""

        decision, _ = await self.route_initial_workflow_with_usage(
            conversation=conversation,
            user_message=user_message,
            routing_catalog=routing_catalog,
        )
        return decision

    @log_execution
    async def route_initial_workflow_with_usage(
        self,
        *,
        conversation: Conversation,
        user_message: str,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> tuple[WorkflowRoutingDecision, TokenUsage]:
        """Route the first user message to a workflow and return token usage."""

        logger.info(
            "Routing initial workflow conversation_id=%s user_message_length=%s catalog_size=%s",
            conversation.conversation_id,
            len(user_message),
            len(routing_catalog),
        )
        agent = Agent(
            model=self._get_model(),
            system_prompt=self._build_routing_system_prompt(),
            callback_handler=None,
            name="Workflow Routing Agent",
            description="Classifies the first user request into the most likely configured workflow.",
        )

        prompt = self._build_routing_prompt(
            user_message=user_message,
            routing_catalog=routing_catalog,
        )

        self._trace_llm(
            operation="route_initial_workflow",
            outcome="started",
            conversation=conversation,
            extra={
                "user_message_length": len(user_message),
                "catalog_size": len(routing_catalog),
            },
        )
        start = time.perf_counter()
        try:
            result = await agent.invoke_async(
                prompt,
                structured_output_model=WorkflowRoutingDecision,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "Strands routing FAILED (LLM not consumed), using local fallback "
                "conversation_id=%s model=%s elapsed_ms=%s reason=%s",
                conversation.conversation_id,
                self.model_id,
                elapsed_ms,
                repr(exc),
            )
            self._trace_llm(
                operation="route_initial_workflow",
                outcome="error",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                error=exc,
            )
            return (
                self._fallback_workflow_routing(
                    user_message=user_message,
                    routing_catalog=routing_catalog,
                ),
                self._empty_usage(),
            )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        usage = self._extract_usage(result)

        if result.structured_output is None:
            logger.error(
                "Strands routing returned NO structured output, using local fallback "
                "conversation_id=%s model=%s elapsed_ms=%s",
                conversation.conversation_id,
                self.model_id,
                elapsed_ms,
            )
            self._trace_llm(
                operation="route_initial_workflow",
                outcome="fallback_no_output",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                usage=usage,
            )
            return (
                self._fallback_workflow_routing(
                    user_message=user_message,
                    routing_catalog=routing_catalog,
                ),
                usage,
            )

        decision = WorkflowRoutingDecision.model_validate(
            result.structured_output.model_dump()
        )
        self._trace_llm(
            operation="route_initial_workflow",
            outcome="ok",
            conversation=conversation,
            elapsed_ms=elapsed_ms,
            usage=usage,
            extra={
                "is_match": decision.is_match,
                "workflow": decision.workflow,
                "confidence": decision.confidence,
            },
        )
        self._log_agent_response(
            conversation_id=conversation.conversation_id,
            agent_name="Workflow Routing Agent",
            response_payload=json.dumps(
                decision.model_dump(),
                ensure_ascii=False,
                #indent=2,
            ),
        )
        logger.info(
            "Initial workflow routing completed conversation_id=%s is_match=%s workflow=%s confidence=%s total_tokens=%s",
            conversation.conversation_id,
            decision.is_match,
            decision.workflow,
            decision.confidence,
            usage.total_tokens,
        )
        return decision, usage

    @log_execution
    async def validate_step_answer(
        self,
        *,
        conversation: Conversation,
        step_id: str,
        step: WorkflowStep,
        user_answer: str,
    ) -> WorkflowAnswerValidation:
        """Validate a free-text answer against the current workflow step."""

        validation, _ = await self.validate_step_answer_with_usage(
            conversation=conversation,
            step_id=step_id,
            step=step,
            user_answer=user_answer,
        )
        return validation

    @log_execution
    async def validate_step_answer_with_usage(
        self,
        *,
        conversation: Conversation,
        step_id: str,
        step: WorkflowStep,
        user_answer: str,
    ) -> tuple[WorkflowAnswerValidation, TokenUsage]:
        """Validate a free-text answer and return the associated token usage."""

        logger.info(
            "Validating workflow answer with Strands conversation_id=%s workflow=%s step_id=%s",
            conversation.conversation_id,
            conversation.workflow,
            step_id,
        )
        agent = Agent(
            model=self._get_model(),
            system_prompt=self._build_validation_system_prompt(),
            callback_handler=None,
            name="Workflow Validation Agent",
            description="Validates workflow answers and extracts normalized data.",
        )

        prompt = self._build_validation_prompt(
            conversation=conversation,
            step_id=step_id,
            step=step,
            user_answer=user_answer,
        )

        self._trace_llm(
            operation="validate_step_answer",
            outcome="started",
            conversation=conversation,
            extra={"step_id": step_id, "workflow": self._get_workflow_name(conversation)},
        )
        start = time.perf_counter()
        try:
            result = await agent.invoke_async(
                prompt,
                structured_output_model=WorkflowAnswerValidation,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "Strands validation FAILED (LLM not consumed), using local fallback "
                "conversation_id=%s step_id=%s model=%s elapsed_ms=%s reason=%s",
                conversation.conversation_id,
                step_id,
                self.model_id,
                elapsed_ms,
                repr(exc),
            )
            self._trace_llm(
                operation="validate_step_answer",
                outcome="error",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                error=exc,
                extra={"step_id": step_id},
            )
            return (
                self._fallback_validation(
                    step_id=step_id,
                    step=step,
                    user_answer=user_answer,
                ),
                self._empty_usage(),
            )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        if result.structured_output is None:
            logger.error(
                "Strands validation returned NO structured output, using local fallback "
                "conversation_id=%s step_id=%s model=%s elapsed_ms=%s",
                conversation.conversation_id,
                step_id,
                self.model_id,
                elapsed_ms,
            )
            self._trace_llm(
                operation="validate_step_answer",
                outcome="fallback_no_output",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                usage=self._extract_usage(result),
                extra={"step_id": step_id},
            )
            return (
                self._fallback_validation(
                    step_id=step_id,
                    step=step,
                    user_answer=user_answer,
                ),
                self._extract_usage(result),
            )

        validation = WorkflowAnswerValidation.model_validate(
            result.structured_output.model_dump()
        )
        self._trace_llm(
            operation="validate_step_answer",
            outcome="ok",
            conversation=conversation,
            elapsed_ms=elapsed_ms,
            usage=self._extract_usage(result),
            extra={"step_id": step_id, "is_valid": validation.is_valid},
        )
        self._log_agent_response(
            conversation_id=conversation.conversation_id,
            agent_name="Workflow Validation Agent",
            response_payload=json.dumps(
                validation.model_dump(),
                ensure_ascii=False,
                indent=2,
            ),
        )

        if validation.is_valid and step.save_as and validation.normalized_answer:
            validation.captured_data.setdefault(
                step.save_as, validation.normalized_answer
            )

        usage = self._extract_usage(result)
        logger.info(
            "Strands validation completed conversation_id=%s step_id=%s is_valid=%s total_tokens=%s",
            conversation.conversation_id,
            step_id,
            validation.is_valid,
            usage.total_tokens,
        )
        return validation, usage

    @log_execution
    async def classify_step_option_with_usage(
        self,
        *,
        conversation: Conversation,
        step_id: str,
        step: WorkflowStep,
        entry_hint: str,
    ) -> tuple[StepOptionClassification, TokenUsage]:
        """Classify an entry hint against a smart-route step's options and return usage."""

        logger.info(
            "Classifying step option conversation_id=%s step_id=%s entry_hint_length=%s",
            conversation.conversation_id,
            step_id,
            len(entry_hint),
        )
        agent = Agent(
            model=self._get_model(),
            system_prompt=self._build_option_classification_system_prompt(),
            callback_handler=None,
            name="Step Option Classification Agent",
            description="Classifies a user request into one of the available step options.",
        )

        prompt = self._build_option_classification_prompt(
            step_id=step_id,
            step=step,
            entry_hint=entry_hint,
        )

        self._trace_llm(
            operation="classify_step_option",
            outcome="started",
            conversation=conversation,
            extra={"step_id": step_id, "entry_hint_length": len(entry_hint)},
        )
        start = time.perf_counter()
        try:
            result = await agent.invoke_async(
                prompt,
                structured_output_model=StepOptionClassification,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "Step option classification FAILED (LLM not consumed), defaulting to show menu "
                "conversation_id=%s step_id=%s model=%s elapsed_ms=%s reason=%s",
                conversation.conversation_id,
                step_id,
                self.model_id,
                elapsed_ms,
                repr(exc),
            )
            self._trace_llm(
                operation="classify_step_option",
                outcome="error",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                error=exc,
                extra={"step_id": step_id},
            )
            return StepOptionClassification(is_match=False), self._empty_usage()

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        usage = self._extract_usage(result)

        if result.structured_output is None:
            logger.error(
                "Step option classification returned NO structured output "
                "conversation_id=%s step_id=%s model=%s elapsed_ms=%s",
                conversation.conversation_id,
                step_id,
                self.model_id,
                elapsed_ms,
            )
            self._trace_llm(
                operation="classify_step_option",
                outcome="fallback_no_output",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                usage=usage,
                extra={"step_id": step_id},
            )
            return StepOptionClassification(is_match=False), usage

        classification = StepOptionClassification.model_validate(
            result.structured_output.model_dump()
        )
        self._trace_llm(
            operation="classify_step_option",
            outcome="ok",
            conversation=conversation,
            elapsed_ms=elapsed_ms,
            usage=usage,
            extra={
                "step_id": step_id,
                "is_match": classification.is_match,
                "option_key": classification.option_key,
            },
        )
        self._log_agent_response(
            conversation_id=conversation.conversation_id,
            agent_name="Step Option Classification Agent",
            response_payload=json.dumps(
                classification.model_dump(),
                ensure_ascii=False,
                indent=2,
            ),
        )
        logger.info(
            "Step option classification completed conversation_id=%s step_id=%s is_match=%s option_key=%s confidence=%s",
            conversation.conversation_id,
            step_id,
            classification.is_match,
            classification.option_key,
            classification.confidence,
        )
        return classification, usage

    @log_execution
    async def generate_final_response(
        self,
        *,
        conversation: Conversation,
        default_message: str,
        closure_mode: str = "resolved_data",
    ) -> str:
        """Generate a generic closing response using the gathered workflow data."""

        response, _ = await self.generate_final_response_with_usage(
            conversation=conversation,
            default_message=default_message,
            closure_mode=closure_mode,
        )
        return response

    @log_execution
    async def generate_final_response_with_usage(
        self,
        *,
        conversation: Conversation,
        default_message: str,
        closure_mode: str = "resolved_data",
    ) -> tuple[str, TokenUsage]:
        """Generate a generic closing response and return the associated token usage."""

        logger.info(
            "Generating final workflow response conversation_id=%s workflow=%s current_step=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
        )
        agent = Agent(
            model=self._get_model(),
            system_prompt=self._build_summary_system_prompt(),
            callback_handler=None,
            name="Workflow Summary Agent",
            description="Builds concise final workflow responses based on captured data.",
        )

        prompt = self._build_summary_prompt(
            conversation=conversation,
            default_message=default_message,
            closure_mode=closure_mode,
        )

        self._trace_llm(
            operation="generate_final_response",
            outcome="started",
            conversation=conversation,
            extra={
                "workflow": self._get_workflow_name(conversation),
                "closure_mode": closure_mode,
            },
        )
        start = time.perf_counter()
        try:
            result = await agent.invoke_async(prompt)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            conversation.captured_data["llm_response_source"] = (
                "local_fallback_exception"
            )
            conversation.captured_data["llm_usage_status"] = "not_available"
            conversation.captured_data["llm_fallback_reason"] = exc.__class__.__name__
            logger.exception(
                "Strands summary FAILED (LLM not consumed), using local fallback "
                "conversation_id=%s workflow=%s model=%s elapsed_ms=%s reason=%s",
                conversation.conversation_id,
                self._get_workflow_name(conversation),
                self.model_id,
                elapsed_ms,
                repr(exc),
            )
            self._trace_llm(
                operation="generate_final_response",
                outcome="error",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                error=exc,
            )
            return (
                self._build_local_summary(
                    conversation,
                    default_message,
                    closure_mode=closure_mode,
                ),
                self._empty_usage(),
            )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response_text = str(result).strip()
        usage = self._extract_usage(result)
        self._trace_llm(
            operation="generate_final_response",
            outcome="ok" if response_text else "fallback_empty",
            conversation=conversation,
            elapsed_ms=elapsed_ms,
            usage=usage,
            extra={"response_source": "model" if response_text else "empty_model_response"},
        )
        final_response = response_text or self._build_local_summary(
            conversation,
            default_message,
            closure_mode=closure_mode,
        )
        self._log_agent_response(
            conversation_id=conversation.conversation_id,
            agent_name="Workflow Summary Agent",
            response_payload=final_response,
        )
        conversation.captured_data["llm_response_source"] = (
            "model" if response_text else "local_fallback_empty_model_response"
        )
        conversation.captured_data["llm_usage_status"] = (
            "reported" if usage.total_tokens > 0 else "missing_from_provider"
        )
        conversation.captured_data["llm_input_tokens"] = str(usage.input_tokens)
        conversation.captured_data["llm_output_tokens"] = str(usage.output_tokens)
        conversation.captured_data["llm_total_tokens"] = str(usage.total_tokens)
        conversation.captured_data.pop("llm_fallback_reason", None)
        logger.info(
            "Strands final response completed conversation_id=%s workflow=%s response_source=%s total_tokens=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.captured_data["llm_response_source"],
            usage.total_tokens,
        )
        return final_response, usage

    @log_execution
    def _build_option_classification_system_prompt(self) -> str:
        """Return the system instructions for the smart-route step option classifier."""

        return (
            "Eres un agente que clasifica el texto inicial de un usuario contra las opciones disponibles "
            "en un paso de un flujo de atencion guiada. "
            "Tu tarea es determinar si el texto del usuario indica con claridad suficiente cual de las "
            "opciones disponibles aplica para su caso. "
            "Si el texto menciona de forma directa o con alta probabilidad una opcion concreta, "
            "marca is_match=true con confidence=high o medium y devuelve el option_key exacto del catalogo. "
            "Si el texto es ambiguo, no menciona el tema de ninguna opcion o no hay suficiente claridad, "
            "marca is_match=false y deja option_key vacio. "
            "No asumas informacion que no este en el texto del usuario. "
            "Usa unicamente los option_key definidos en available_options."
        )

    @log_execution
    def _build_option_classification_prompt(
        self,
        *,
        step_id: str,
        step: WorkflowStep,
        entry_hint: str,
    ) -> str:
        """Build the prompt used to classify an entry hint against step options."""

        payload = {
            "step_id": step_id,
            "step_question": step.question.strip(),
            "entry_hint": entry_hint,
            "available_options": [
                {"key": opt.key, "label": opt.label} for opt in step.options
            ],
        }
        return (
            "Clasifica el texto inicial del usuario contra las opciones disponibles para este paso del flujo.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "Reglas:\n"
            "- option_key debe corresponder exactamente a una clave del campo available_options.\n"
            "- Solo usa is_match=true cuando el texto indica con claridad una opcion concreta.\n"
            "- confidence=high si es muy explicito; confidence=medium si es probable pero no literal.\n"
            "- Si el texto no permite distinguir la opcion con suficiente certeza, devuelve is_match=false y option_key vacio.\n"
            "- rationale debe ser breve y concreta."
        )

    @log_execution
    def _build_routing_system_prompt(self) -> str:
        """Return the system instructions for the start-phase workflow router."""

        return (
            build_routing_system_prompt() + "\n\n" + routing_scope_prompt_suffix()
        )

    @log_execution
    def _build_routing_prompt(
        self,
        *,
        user_message: str,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> str:
        """Build the prompt used during the initial workflow routing stage."""

        return build_routing_user_prompt(
            user_message=user_message,
            routing_catalog=routing_catalog,
        )

    @log_execution
    def _build_validation_system_prompt(self) -> str:
        """Return the system instructions for workflow answer validation."""

        return (
            "Eres un agente que valida respuestas de usuarios dentro de un flujo guiado. "
            "Debes decidir si la respuesta del usuario contesta correctamente la pregunta actual. "
            "Si la respuesta es valida, normalizala en espanol claro y extrae solo los datos "
            "utiles que realmente se mencionan. "
            "Si la respuesta no es valida o es insuficiente, marca is_valid=false y redacta "
            "assistant_message con una aclaracion breve y amable para pedir el dato correcto. "
            "No inventes datos, no asumas informacion faltante y mantente alineado al paso actual."
        )

    @log_execution
    def _build_summary_system_prompt(self) -> str:
        """Return the system instructions for the closing response generator."""

        return (
            "Eres un asistente que responde cierres de guia rapida de forma breve, clara y amable. "
            "Debes redactar una respuesta final segun el closing_mode recibido. "
            "Si closing_mode es 'resolved_data', responde solo con informacion resuelta disponible en resolved_data. "
            "Si closing_mode es 'opt_out', responde con una despedida amable, agradece el contacto y deja abierta la posibilidad de volver cuando lo necesite. "
            "Si closing_mode es 'privacy_guidance', responde con empatia sobre la consulta no autorizada, "
            "agradece el contacto y explica de forma general que el caso debe revisarse por los canales correspondientes. "
            "Si closing_mode es 'passive_product_guidance', responde con empatia, "
            "agradece el contacto y explica de forma general que el caso requiere revision por los canales correspondientes. "
            "Si closing_mode es 'central_risk_account_status_guidance', usa resolved_data y default_message "
            "como base obligatoria para redactar una respuesta amable, clara y fiel a los hechos del caso. "
            "Puedes mejorar el tono y el formato, pero no debes cambiar plazos, estados, recomendaciones ni detalles del embargo. "
            "user_request contiene la consulta original del usuario y sirve solo como contexto; "
            "recent_conversation contiene mensajes recientes y sirve solo para entender el contexto conversacional; "
            "no la conviertas en una respuesta ni la presentes como informacion confirmada. "
            "Si closing_mode es 'no_information' o resolved_data no aporta datos utiles, responde exactamente: "
            "'Lo siento, pero actualmente no puedo responder esto. Gracias por comunicarte.' "
            "No inventes datos, no prometas acciones no ejecutadas y evita frases como "
            "'hemos recibido tu consulta' o 'la informacion fue registrada'."
        )

    @log_execution
    def _build_validation_prompt(
        self,
        *,
        conversation: Conversation,
        step_id: str,
        step: WorkflowStep,
        user_answer: str,
    ) -> str:
        """Build the validation prompt for the current workflow step."""

        logger.info(
            "Building validation prompt conversation_id=%s workflow=%s step_id=%s",
            conversation.conversation_id,
            conversation.workflow,
            step_id,
        )
        context_payload = {
            "workflow": self._get_workflow_name(conversation),
            "step_id": step_id,
            "question": step.question,
            "action": step.action,
            "save_as": step.save_as,
            "input_type": step.input_type,
            "current_answers": conversation.flow_answers,
            "captured_data": _business_captured_data(conversation),
            "user_answer": user_answer,
        }

        return (
            "Valida la siguiente respuesta del usuario contra la pregunta del flujo.\n\n"
            f"{json.dumps(context_payload, ensure_ascii=False, indent=2)}\n\n"
            "Criterios:\n"
            "- is_valid=true solo si la respuesta contesta de forma directa la pregunta actual.\n"
            "- normalized_answer debe contener la mejor version limpia de la respuesta.\n"
            "- captured_data debe incluir solo pares clave-valor utiles y textuales.\n"
            "- assistant_message solo debe llenarse cuando is_valid sea false.\n"
            "- validation_reason debe ser breve y concreta.\n"
            "- Si save_as existe y la respuesta es valida, captured_data debe incluir esa clave."
        )

    @log_execution
    def _build_summary_prompt(
        self,
        *,
        conversation: Conversation,
        default_message: str,
        closure_mode: str,
    ) -> str:
        """Build the prompt used to generate the final generic response."""

        logger.info(
            "Building summary prompt conversation_id=%s workflow=%s current_step=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
        )
        context_payload: dict[str, Any] = {
            "workflow": self._get_workflow_name(conversation),
            "current_step": conversation.current_step,
            "closing_mode": closure_mode,
            "user_request": conversation.flow_answers,
            "resolved_data": _business_captured_data(conversation),
            "recent_conversation": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in conversation.messages[-6:]
            ],
            "default_message": default_message,
        }

        return (
            "Redacta una respuesta final corta para el usuario a partir del siguiente contexto.\n\n"
            f"{json.dumps(context_payload, ensure_ascii=False, indent=2)}\n\n"
            "La respuesta debe:\n"
            "- estar en espanol\n"
            "- ser clara y amable\n"
            "- respetar el valor de closing_mode\n"
            "- usar solo resolved_data como base de la respuesta cuando closing_mode sea resolved_data\n"
            "- usar user_request solo para entender la pregunta original\n"
            "- usar recent_conversation solo para entender el contexto de la conversacion\n"
            "- responder de forma util cuando closing_mode sea resolved_data y existan datos\n"
            "- agradecer con calidez cuando closing_mode sea opt_out\n"
            "- orientar con empatia cuando closing_mode sea privacy_guidance\n"
            "- orientar con empatia cuando closing_mode sea passive_product_guidance\n"
            "- si closing_mode es central_risk_account_status_guidance, usar default_message como referencia de negocio obligatoria y resolved_data como soporte\n"
            "- devolver el mensaje de disculpa si closing_mode es no_information"
        )

    @log_execution
    def _fallback_workflow_routing(
        self,
        *,
        user_message: str,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> WorkflowRoutingDecision:
        """Route the first user request locally when the remote model is unavailable."""

        logger.info(
            "Running local fallback workflow routing user_message_length=%s catalog_size=%s",
            len(user_message),
            len(routing_catalog),
        )
        normalized_message = self._normalize_routing_text(user_message)
        message_tokens = self._tokenize_routing_text(normalized_message)

        # Mensaje muy corto o solo saludo/cortesia: responder con calidez en lugar
        # del mensaje frio de error, incluso cuando el LLM remoto no esta disponible.
        if len(message_tokens) < 2 or self._is_fallback_greeting(message_tokens):
            return WorkflowRoutingDecision(
                is_match=False,
                confidence="none",
                assistant_message="",
                clarification_message=self._build_fallback_greeting_message(
                    routing_catalog=routing_catalog,
                ),
            )

        best_entry: WorkflowRoutingEntry | None = None
        best_score = 0
        second_best_score = 0

        for entry in routing_catalog:
            score = self._score_routing_entry(
                normalized_message=normalized_message,
                message_tokens=message_tokens,
                entry=entry,
            )

            if score > best_score:
                second_best_score = best_score
                best_score = score
                best_entry = entry
            elif score > second_best_score:
                second_best_score = score

        if best_entry is None or best_score <= 0:
            return WorkflowRoutingDecision(
                is_match=False,
                confidence="none",
                assistant_message="",
                clarification_message=self._build_fallback_scope_message(
                    routing_catalog=routing_catalog,
                ),
            )

        confidence = "low"
        if best_score >= 6 and (best_score - second_best_score) >= 2:
            confidence = "high"
        elif best_score >= 3:
            confidence = "medium"

        return WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key=best_entry.general_workflow_key,
            workflow=best_entry.workflow,
            confidence=confidence,
            rationale=(
                f"La solicitud coincide con {best_entry.workflow_label} "
                f"por el vocabulario usado en el mensaje inicial."
            ),
            assistant_message=self._build_fallback_routing_assistant_message(
                entry=best_entry,
            ),
            clarification_message="",
        )

    @log_execution
    def _build_fallback_routing_assistant_message(
        self,
        *,
        entry: WorkflowRoutingEntry,
    ) -> str:
        """Build a friendly routing explanation when the remote model is unavailable."""

        return (
            "Segun el contexto que me das, entiendo que tu consulta se relaciona con "
            f"{entry.workflow_label}. Creo que el flujo adecuado para ayudarte a avanzar "
            f"es {entry.general_workflow_label} -> {entry.workflow_label}, porque coincide "
            "con lo que describes en tu mensaje."
        )

    @log_execution
    def _is_fallback_greeting(self, message_tokens: set[str]) -> bool:
        """Return whether every comparable token belongs to the greeting vocabulary."""

        if not message_tokens:
            return False

        return all(token in _FALLBACK_GREETING_TOKENS for token in message_tokens)

    @log_execution
    def _fallback_categories(
        self,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> list[str]:
        """Return the unique general-workflow labels preserving catalog order."""

        categories: list[str] = []
        for entry in routing_catalog:
            label = (entry.general_workflow_label or "").strip()
            if label and label not in categories:
                categories.append(label)
        return categories

    @log_execution
    def _build_fallback_greeting_message(
        self,
        *,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> str:
        """Build a warm welcome used by the local fallback for greetings/short input."""

        categories = self._fallback_categories(routing_catalog)
        category_text = (
            f"Puedo ayudarte con temas de: {', '.join(categories)}.\n"
            if categories
            else ""
        )
        return (
            "Hola, soy tu asistente de PQRs de BBVA. "
            "Con gusto te ayudo.\n\n"
            f"{category_text}"
            "Cuentame que necesitas. Por ejemplo: \"necesito mi paz y salvo\", "
            "\"por que me cobran cuota de manejo\" o "
            "\"no reconozco un reporte en centrales de riesgo\"."
        )

    @log_execution
    def _build_fallback_scope_message(
        self,
        *,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> str:
        """Build a warm scope message when no workflow matches in the local fallback."""

        categories = self._fallback_categories(routing_catalog)
        category_text = (
            f" Puedo ayudarte con temas de: {', '.join(categories)}."
            if categories
            else ""
        )
        return (
            "Por ahora solo puedo ayudarte con temas de PQRS y servicios del banco."
            f"{category_text}\n\n"
            "Cuentame con un poco mas de detalle que necesitas resolver para orientarte mejor."
        )

    @log_execution
    def _get_workflow_name(self, conversation: Conversation) -> str:
        """Return a printable workflow name for prompts."""

        return conversation.workflow or "Sin workflow"

    @log_execution
    def _build_model(self) -> Any:
        """Create the Strands model wrapper backed by an OpenAI-compatible endpoint."""

        logger.info(
            "Building Strands model endpoint=%s model_id=%s",
            self.endpoint,
            self.model_id,
        )
        try:
            import openai
            from strands.models import OpenAIModel
        except ModuleNotFoundError as exc:
            raise ConfigurationError(
                "The `openai` package required by Strands is not installed.",
                details={"missing_dependency": "openai"},
            ) from exc

        http_client = openai.DefaultAsyncHttpxClient(verify=self.ssl_verify)
        base_url = self._resolve_base_url()
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
            http_client=http_client,
            # Hard cap so a slow/degenerate prompt cannot hang the turn for the
            # SDK default (600s x 2). The 120s background turn cap dominates.
            timeout=120,
            max_retries=1,
        )

        return OpenAIModel(
            client=client,
            model_id=self.model_id,
        )

    @log_execution
    def _get_model(self) -> Any:
        """Return the lazily initialized Strands model."""

        if self.model is None:
            self.model = self._build_model()

        return self.model

    @log_execution
    def _fallback_validation(
        self,
        *,
        step_id: str,
        step: WorkflowStep,
        user_answer: str,
    ) -> WorkflowAnswerValidation:
        """Validate a text answer locally when Strands is unavailable."""

        logger.info(
            "Running local fallback validation step_id=%s save_as=%s",
            step_id,
            step.save_as,
        )
        cleaned_answer = user_answer.strip()
        normalized_answer = cleaned_answer.casefold()
        invalid_answers = {
            "",
            "no se",
            "nose",
            "ns",
            "n/a",
            "na",
            "no aplica",
            "ninguno",
            "ninguna",
            "no tengo",
        }

        if normalized_answer in invalid_answers or len(cleaned_answer) < 3:
            return WorkflowAnswerValidation(
                is_valid=False,
                normalized_answer="",
                captured_data={},
                validation_reason="The answer is too vague to complete the current step.",
                assistant_message=(
                    f"Necesito que respondas correctamente el paso {step_id}. "
                    f"{step.question}"
                ),
            )

        captured_data = {step.save_as: cleaned_answer} if step.save_as else {}
        return WorkflowAnswerValidation(
            is_valid=True,
            normalized_answer=cleaned_answer,
            captured_data=captured_data,
            validation_reason="Validated locally because the Strands connection was unavailable.",
            assistant_message="",
        )

    @log_execution
    def _build_local_summary(
        self,
        conversation: Conversation,
        default_message: str,
        *,
        closure_mode: str,
    ) -> str:
        """Build a generic local summary when the remote model is unavailable."""

        logger.info(
            "Building local summary conversation_id=%s workflow=%s current_step=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
        )
        values = list(
            dict.fromkeys(
                value
                for value in list(_business_captured_data(conversation).values())
                if value
            )
        )

        if closure_mode == "opt_out":
            return (
                "Muchas gracias por comunicarte. Cuando quieras retomar esta consulta, "
                "estare aqui para ayudarte."
            )

        if closure_mode == "privacy_guidance":
            return (
                "Gracias por comunicarte. Entiendo tu inquietud sobre una consulta de informacion "
                "sin tu permiso. Te recomiendo continuar esta revision por los canales de atencion "
                "correspondientes para validar el caso."
            )

        if closure_mode == "passive_product_guidance":
            return (
                "Gracias por comunicarte. Entiendo la novedad que identificaste en este producto. "
                "Te recomiendo continuar la revision por los canales de atencion correspondientes "
                "para validar el caso con mayor detalle."
            )

        if closure_mode == "central_risk_account_status_guidance":
            return default_message

        if not values:
            return default_message

        details = "; ".join(values)
        return (
            f"Con la informacion disponible, esto es lo que puedo indicarte: {details}"
        )

    @log_execution
    def _score_routing_entry(
        self,
        *,
        normalized_message: str,
        message_tokens: set[str],
        entry: WorkflowRoutingEntry,
    ) -> int:
        """Score how well a user message matches a routing entry."""

        searchable_fragments = [
            entry.workflow,
            entry.workflow_label,
            entry.general_workflow_key,
            entry.general_workflow_label,
            entry.description,
            *entry.examples,
            *entry.steps_preview,
        ]

        score = 0
        for fragment in searchable_fragments:
            normalized_fragment = self._normalize_routing_text(fragment)
            if not normalized_fragment:
                continue

            fragment_tokens = self._tokenize_routing_text(normalized_fragment)
            overlap = message_tokens & fragment_tokens
            score += len(overlap)

            if normalized_fragment in normalized_message:
                score += 3

        return score

    @log_execution
    def _normalize_routing_text(self, value: str) -> str:
        """Normalize routing text so comparisons ignore accents and casing."""

        normalized_value = unicodedata.normalize("NFKD", value.strip().casefold())
        return "".join(
            character
            for character in normalized_value
            if not unicodedata.combining(character)
        )

    @log_execution
    def _tokenize_routing_text(self, value: str) -> set[str]:
        """Tokenize normalized routing text into comparable words."""

        sanitized = "".join(
            character if character.isalnum() else " " for character in value
        )
        return {token for token in sanitized.split() if len(token) >= 3}

    @staticmethod
    @log_execution
    def _resolve_ssl_verify(constants: dict[str, str]) -> bool | str:
        """Resolve the SSL verification strategy from environment constants."""

        ca_bundle = constants.get("SSL_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ca_bundle

        ssl_verify = constants.get("SSL_VERIFY", "true").strip().casefold()
        return ssl_verify not in {"0", "false", "no", "off"}

    @log_execution
    def _extract_usage(self, result: Any) -> TokenUsage:
        """Extract token usage from a Strands agent result."""

        logger.info("Extracting token usage from Strands result")
        for source_name, usage_payload in self._iter_usage_candidates(result):
            usage = self._build_token_usage(usage_payload)
            if (
                usage.total_tokens > 0
                or usage.input_tokens > 0
                or usage.output_tokens > 0
            ):
                logger.info(
                    "Token usage extracted source=%s input_tokens=%s output_tokens=%s total_tokens=%s",
                    source_name,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                )
                return usage

        logger.warning(
            "Strands result did not expose token usage in any known location"
        )
        return self._empty_usage()

    @log_execution
    def _iter_usage_candidates(self, result: Any) -> list[tuple[str, Any]]:
        """Collect possible token-usage payloads from the Strands result object."""

        metrics = getattr(result, "metrics", None)
        candidates: list[tuple[str, Any]] = []

        if metrics is not None:
            candidates.append(
                (
                    "metrics.accumulated_usage",
                    getattr(metrics, "accumulated_usage", None),
                )
            )

            latest_invocation = getattr(metrics, "latest_agent_invocation", None)
            if latest_invocation is not None:
                candidates.append(
                    (
                        "metrics.latest_agent_invocation.usage",
                        getattr(latest_invocation, "usage", None),
                    )
                )

            agent_invocations = getattr(metrics, "agent_invocations", None) or []
            if agent_invocations:
                candidates.append(
                    (
                        "metrics.agent_invocations[-1].usage",
                        getattr(agent_invocations[-1], "usage", None),
                    )
                )

            if hasattr(metrics, "get_summary"):
                try:
                    summary = metrics.get_summary()
                except Exception as exc:
                    logger.warning(
                        "Unable to read Strands metrics summary while extracting usage: %s",
                        exc,
                    )
                else:
                    candidates.append(
                        (
                            "metrics.get_summary().accumulated_usage",
                            summary.get("accumulated_usage"),
                        )
                    )

        state = getattr(result, "state", None)
        if isinstance(state, Mapping):
            candidates.append(("result.state.usage", state.get("usage")))
            candidates.append(
                ("result.state.accumulated_usage", state.get("accumulated_usage"))
            )

        return candidates

    @log_execution
    def _build_token_usage(self, usage_payload: Any) -> TokenUsage:
        """Normalize a raw usage payload into the local token model."""

        input_tokens = self._read_usage_int(
            usage_payload,
            "inputTokens",
            "input_tokens",
            "prompt_tokens",
        )
        output_tokens = self._read_usage_int(
            usage_payload,
            "outputTokens",
            "output_tokens",
            "completion_tokens",
        )
        total_tokens = self._read_usage_int(
            usage_payload,
            "totalTokens",
            "total_tokens",
            "total",
        )

        if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
            total_tokens = input_tokens + output_tokens

        cached_input_tokens = self._read_cached_input_tokens(usage_payload)

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=cached_input_tokens,
        )

    @log_execution
    def _read_cached_input_tokens(self, usage_payload: Any) -> int:
        """Read the prompt-cache hit size from a usage payload.

        Without this the cache is invisible in the benchmark: raw input tokens
        cannot tell a prompt served from cache from one billed in full, so a run
        that reuses the static routing prefix looks identical to one that does
        not.

        Azure/OpenAI nest it under `prompt_tokens_details.cached_tokens`; other
        providers expose a flat key. Both are tried, and a missing value is 0
        (meaning "no cache reported", not "cache missed").
        """

        flat = self._read_usage_int(
            usage_payload,
            "cached_tokens",
            "cache_read_input_tokens",
            "cacheReadInputTokens",
        )
        if flat:
            return flat

        details: Any | None = None
        for key in ("prompt_tokens_details", "input_tokens_details"):
            if isinstance(usage_payload, Mapping):
                details = usage_payload.get(key)
            else:
                details = getattr(usage_payload, key, None)
            if details is not None:
                break

        if details is None:
            return 0

        return self._read_usage_int(details, "cached_tokens", "cache_read_input_tokens")

    @log_execution
    def _read_usage_int(self, usage_payload: Any, *keys: str) -> int:
        """Read an integer usage field from mappings or attribute-based objects."""

        if usage_payload is None:
            return 0

        for key in keys:
            value: Any | None = None

            if isinstance(usage_payload, Mapping):
                value = usage_payload.get(key)
            else:
                value = getattr(usage_payload, key, None)

            if value is None:
                continue

            try:
                return int(value)
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring non-integer token usage value key=%s value=%r",
                    key,
                    value,
                )

        return 0

    @log_execution
    def _empty_usage(self) -> TokenUsage:
        """Return a zeroed token usage payload."""

        return TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )

    @log_execution
    def _resolve_base_url(self) -> str:
        """Normalize the configured endpoint into an OpenAI-compatible base URL."""

        endpoint = self.endpoint.strip().rstrip("/")
        normalized_endpoint = endpoint.casefold()

        if normalized_endpoint.endswith("/openai/v1"):
            return f"{endpoint}/"

        if (
            "openai.azure.com" in normalized_endpoint
            and "/openai/" not in normalized_endpoint
        ):
            return f"{endpoint}/openai/v1/"

        return f"{endpoint}/"

    @log_execution
    async def select_groups_with_usage(
        self,
        *,
        conversation: Conversation,
        user_message: str,
        routing_catalog: list[WorkflowRoutingEntry],
    ) -> tuple[list[str], TokenUsage]:
        """Nivel 1: pre-filtro de categorias antes del ruteo fino.

        FALLA ABIERTO: ante cualquier error devuelve lista vacia, que el caller
        interpreta como "sin filtro" -> el ruteo corre con el catalogo completo,
        exactamente como hoy.
        """

        valid_keys = {entry.general_workflow_key for entry in routing_catalog}
        agent = Agent(
            model=self._get_model(),
            system_prompt=_GROUP_PREFILTER_SYSTEM_PROMPT,
            callback_handler=None,
            name="Group Prefilter Agent",
            description="Narrows the routing catalog to the most likely groups.",
        )
        prompt = build_group_prefilter_prompt(
            user_message=user_message,
            routing_catalog=routing_catalog,
        )

        self._trace_llm(
            operation="select_groups",
            outcome="started",
            conversation=conversation,
            extra={"user_message_length": len(user_message)},
        )
        start = time.perf_counter()
        try:
            result = await agent.invoke_async(
                prompt,
                structured_output_model=GroupRoutingDecision,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "Group prefilter FAILED, using FULL catalog conversation_id=%s reason=%s",
                conversation.conversation_id,
                repr(exc),
            )
            self._trace_llm(
                operation="select_groups",
                outcome="error",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                error=exc,
            )
            return [], self._empty_usage()

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        usage = self._extract_usage(result)

        if result.structured_output is None:
            logger.error(
                "Group prefilter returned NO structured output, using FULL catalog "
                "conversation_id=%s elapsed_ms=%s",
                conversation.conversation_id,
                elapsed_ms,
            )
            self._trace_llm(
                operation="select_groups",
                outcome="fallback_no_output",
                conversation=conversation,
                elapsed_ms=elapsed_ms,
                usage=usage,
            )
            return [], usage

        decision = GroupRoutingDecision.model_validate(
            result.structured_output.model_dump()
        )
        # Descartar claves alucinadas; si no queda ninguna valida -> sin filtro.
        selected = [key for key in decision.group_keys if key in valid_keys]

        self._trace_llm(
            operation="select_groups",
            outcome="ok",
            conversation=conversation,
            elapsed_ms=elapsed_ms,
            usage=usage,
            extra={"group_keys": selected, "confidence": decision.confidence},
        )
        logger.info(
            "Group prefilter completed conversation_id=%s groups=%s confidence=%s total_tokens=%s",
            conversation.conversation_id,
            selected,
            decision.confidence,
            usage.total_tokens,
        )
        return selected, usage
