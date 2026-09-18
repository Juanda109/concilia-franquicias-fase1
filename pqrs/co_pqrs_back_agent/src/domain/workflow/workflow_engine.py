"""Workflow engine that navigates decision-tree conversations from YAML."""

from __future__ import annotations

import json
import random
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
)
from domain.workflow.general_messages import load_general_messages
from domain.workflow.models import (
    WorkflowCatalog,
    WorkflowDefinition,
    WorkflowGeneralCatalog,
    WorkflowRoutingEntry,
    WorkflowSelectorGroup,
    WorkflowSelectorOption,
    WorkflowStep,
    WorkflowStepOption,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import ConfigurationError

logger = get_logger(__name__)


@dataclass(frozen=True)
class WorkflowEntryShortcut:
    """Safe workflow shortcut that preloads prior answers and jumps to a step."""

    step_id: str
    flow_answers: dict[str, str]


# Marca de turno (transitoria): el turno solo repinto un paso multi_select
# -- una casilla o un cambio de pagina -- en vez de avanzar el flujo. Quien
# arma el turno la lee para ACTUALIZAR la tarjeta ya enviada en vez de
# agregar otra al historial. Se limpia en cada turno.
MULTI_SELECT_REFRESH_KEY = "multi_select_refresh"


class WorkflowEngine:
    """Drive a numbered workflow tree and mutate the runtime conversation state."""

    def __init__(self, workflow_path: str | Path | None = None) -> None:
        self.workflow_path = (
            Path(workflow_path) if workflow_path is not None else Path(__file__).parent
        )
        self.workflows_directory = (
            self.workflow_path
            if self.workflow_path.is_dir()
            else self.workflow_path.parent
        )
        self.general_catalog_path = (
            self.workflow_path
            if self.workflow_path.is_file()
            else self.workflows_directory / "general.yml"
        )
        self.general_messages = load_general_messages()
        self.catalog = self._load_catalog()
        logger.info(
            "WorkflowEngine initialized general_catalog_path=%s workflows_directory=%s",
            self.general_catalog_path,
            self.workflows_directory,
        )

    @log_execution
    def generate_response(self, conversation: Conversation, user_content: str) -> str:
        """
        Process the latest user input and return the assistant response.

        The method mutates the provided conversation to keep the workflow state
        synchronized with the persisted conversation object.
        """

        logger.info(
            "Generating workflow response conversation_id=%s workflow=%s current_step=%s status=%s user_content=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
            conversation.status.value,
            user_content,
        )
        normalized_input = self._normalize_text(user_content)

        if conversation.status == ConversationStatus.CLOSED and conversation.workflow:
            return (
                "Este flujo ya fue completado. Si deseas iniciar uno nuevo, "
                "usa un nuevo conversation_id."
            )

        if conversation.workflow is None:
            return self._handle_workflow_selection(conversation, normalized_input)

        workflow_definition = self._get_workflow_definition(conversation.workflow)
        current_step = workflow_definition.steps[conversation.current_step]
        return self._handle_workflow_step(
            conversation,
            workflow_definition,
            current_step,
            normalized_input,
            user_content,
        )

    @log_execution
    def get_current_step(
        self, conversation: Conversation
    ) -> tuple[str, WorkflowStep] | None:
        """Return the current workflow step for the provided conversation."""

        logger.info(
            "Resolving current workflow step conversation_id=%s workflow=%s current_step=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
        )
        if conversation.workflow is None:
            return None

        workflow_definition = self._get_workflow_definition(conversation.workflow)
        step = workflow_definition.steps.get(conversation.current_step)

        if step is None:
            return None

        return conversation.current_step, step

    @log_execution
    def render_current_step_prompt(self, conversation: Conversation) -> str | None:
        """Render the current workflow prompt using any dynamic step data."""

        logger.info(
            "Rendering current step prompt conversation_id=%s workflow=%s current_step=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
        )
        current_step_data = self.get_current_step(conversation)

        if current_step_data is None:
            return None

        step_id, step = current_step_data
        return self._render_step_prompt(conversation, step_id, step)

    @log_execution
    def build_routing_catalog(self) -> list[WorkflowRoutingEntry]:
        """Build a normalized catalog used by the start-phase workflow router."""

        routing_entries: list[WorkflowRoutingEntry] = []

        for group in self.catalog.welcome.groups:
            for option in group.options:
                routing_entries.append(
                    WorkflowRoutingEntry(
                        general_workflow_key=group.key,
                        general_workflow_label=group.label,
                        routing_criteria=group.routing_criteria,
                        workflow=option.workflow,
                        workflow_label=option.label,
                        description=self._build_workflow_description(option),
                        examples=option.examples,
                        no_usar=option.no_usar,
                        se_confunde_con=option.se_confunde_con,
                        preconditions=option.preconditions,
                        contraejemplos=option.contraejemplos,
                        steps_preview=self._build_workflow_steps_preview(
                            option.workflow
                        ),
                    )
                )

        logger.info(
            "Built workflow routing catalog entry_count=%s", len(routing_entries)
        )
        return routing_entries

    @log_execution
    def build_workflow_confirmation_message(
        self,
        workflow_name: str,
        *,
        confidence: str = "medium",
    ) -> str:
        """Build the start-phase confirmation for an ambiguous (low-confidence) route.

        Usa una frase natural por workflow (``confirmation_hints`` en
        general_messages.yml) o, si falta, el label del catálogo, y pregunta
        "¿Te refieres a {hint}?".

        DETERMINISTA: no recibe ni usa texto redactado por el LLM. Antes aceptaba
        `rationale` y `assistant_message` del router y los ignoraba; se eliminaron
        para que nadie los reintroduzca por error en el mensaje al cliente.
        """

        _, option = self._find_workflow_selector_option(workflow_name)
        hint = (self.general_messages.confirmation_hints or {}).get(
            workflow_name
        ) or option.label
        return f"¿Te refieres a {hint}?"

    @log_execution
    def build_routing_clarification_message(self) -> str:
        """Build a generic clarification message when no workflow can be routed."""

        # Pool aleatorio (caso: tema bancario en alcance pero sin flujo soportado).
        pool = self.general_messages.routing_clarification_messages
        if pool:
            return random.choice(pool)

        sample_workflows = [
            option.label
            for group in self.catalog.welcome.groups
            for option in group.options[:3]
        ]
        examples = ", ".join(sample_workflows[:6])
        return self.general_messages.routing_clarification_template.format(
            sample_workflows=examples or "algunas opciones disponibles",
        )

    @log_execution
    def build_routing_retry_message(self) -> str:
        """Message asking the customer to rephrase on the FIRST routing no-match.

        Tono distinto al de `build_routing_clarification_message`: ahi se informa
        que el tema no se puede resolver; aqui se pide mas detalle porque todavia
        no se sabe que necesita el cliente. Cascada: pool propio -> pool de
        aclaracion -> plantilla.
        """

        pool = self.general_messages.routing_retry_messages
        if pool:
            return random.choice(pool)
        return self.build_routing_clarification_message()

    @log_execution
    def build_unintelligible_input_message(self) -> str:
        """Message for input with no interpretable words ('9+', '...', '??')."""

        pool = self.general_messages.unintelligible_input_messages
        if pool:
            return random.choice(pool)
        return self.build_routing_retry_message()

    @log_execution
    def start_workflow(
        self,
        conversation: Conversation,
        workflow_name: str,
        *,
        entry_hint: str | None = None,
    ) -> str:
        """Assign a workflow to the conversation and return its first prompt."""

        group, option = self._find_workflow_selector_option(workflow_name)
        workflow_definition = self._get_workflow_definition(option.workflow)
        conversation.general_workflow = group.label
        conversation.workflow = option.workflow
        conversation.flow_version = workflow_definition.version
        conversation.current_step = workflow_definition.start_step
        conversation.status = ConversationStatus.ACTIVE
        self._apply_workflow_entry_shortcut(
            conversation=conversation,
            workflow_name=option.workflow,
            workflow_definition=workflow_definition,
            entry_hint=entry_hint,
        )

        logger.info(
            "Started workflow conversation_id=%s general_workflow=%s workflow=%s start_step=%s entry_hint=%s",
            conversation.conversation_id,
            conversation.general_workflow,
            conversation.workflow,
            conversation.current_step,
            entry_hint,
        )
        return self._render_step_prompt(
            conversation,
            conversation.current_step,
            workflow_definition.steps[conversation.current_step],
        )

    @log_execution
    def _apply_workflow_entry_shortcut(
        self,
        *,
        conversation: Conversation,
        workflow_name: str,
        workflow_definition: WorkflowDefinition,
        entry_hint: str | None,
    ) -> None:
        """Apply a safe workflow shortcut when the routed request allows it."""

        shortcut = self._get_workflow_entry_shortcut(
            workflow_name=workflow_name,
            workflow_definition=workflow_definition,
            entry_hint=entry_hint,
        )

        if shortcut is None:
            return

        if shortcut.step_id not in workflow_definition.steps:
            raise ConfigurationError(
                "Workflow entry shortcut points to an invalid step.",
                details={
                    "workflow": workflow_name,
                    "entry_hint": entry_hint,
                    "step_id": shortcut.step_id,
                },
            )

        conversation.flow_answers.update(shortcut.flow_answers)
        conversation.current_step = shortcut.step_id
        logger.info(
            "Applied workflow entry shortcut conversation_id=%s workflow=%s entry_hint=%s step_id=%s prefilled_answers=%s",
            conversation.conversation_id,
            workflow_name,
            entry_hint,
            shortcut.step_id,
            shortcut.flow_answers,
        )

    @log_execution
    def _get_workflow_entry_shortcut(
        self,
        *,
        workflow_name: str,
        workflow_definition: WorkflowDefinition,
        entry_hint: str | None,
    ) -> WorkflowEntryShortcut | None:
        """Return a safe entry shortcut for a routed workflow when configured."""

        if not entry_hint:
            return None

        start_step = workflow_definition.steps[workflow_definition.start_step]
        if start_step.input_type != "choice" or not start_step.options:
            return None

        selected_option, _ = self._match_step_option(
            start_step.options,
            self._normalize_text(entry_hint),
        )
        if selected_option is None:
            return None

        flow_answers: dict[str, str] = {}
        if start_step.save_as:
            flow_answers[start_step.save_as] = selected_option.key

        return WorkflowEntryShortcut(
            step_id=selected_option.next_step,
            flow_answers=flow_answers,
        )

    @log_execution
    def _load_catalog(self) -> WorkflowCatalog:
        """Load the general workflow selector plus one YAML file per workflow."""

        logger.info(
            "Loading workflow catalog general_catalog_path=%s workflows_directory=%s",
            self.general_catalog_path,
            self.workflows_directory,
        )
        if not self.general_catalog_path.exists():
            raise ConfigurationError(
                "General workflow catalog file not found.",
                details={"general_catalog_path": str(self.general_catalog_path)},
            )

        raw_catalog = yaml.safe_load(
            self.general_catalog_path.read_text(encoding="utf-8")
        )

        if not isinstance(raw_catalog, dict):
            raise ConfigurationError(
                "General workflow catalog file is invalid.",
                details={"general_catalog_path": str(self.general_catalog_path)},
            )

        general_catalog = WorkflowGeneralCatalog.model_validate(raw_catalog)
        flows: dict[str, WorkflowDefinition] = {}

        for group in general_catalog.welcome.groups:
            for option in group.options:
                workflow_name = option.workflow

                if workflow_name in flows:
                    continue

                workflow_path = self._resolve_workflow_path(group.key, workflow_name)
                logger.info(
                    "Loading workflow definition workflow=%s group=%s workflow_path=%s",
                    workflow_name,
                    group.key,
                    workflow_path,
                )

                if not workflow_path.exists():
                    raise ConfigurationError(
                        "Workflow definition file not found.",
                        details={
                            "workflow": workflow_name,
                            "workflow_path": str(workflow_path),
                        },
                    )

                raw_workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

                if not isinstance(raw_workflow, dict):
                    raise ConfigurationError(
                        "Workflow definition file is invalid.",
                        details={
                            "workflow": workflow_name,
                            "workflow_path": str(workflow_path),
                        },
                    )

                flows[workflow_name] = WorkflowDefinition.model_validate(raw_workflow)

        # Workflows INTERNOS: no estan en general.yml (no seleccionables ni ruteables
        # por el LLM). Se usan solo por transiciones programaticas (goto), p.ej. el
        # escalamiento a formulario PQRS cuando el ruteo no encuentra flujo. Se cargan
        # aqui para que tambien hereden los shared_steps (satisfaction_check, etc.).
        internal_workflows = {"pqrs_no_ruteo": Path("pqrs") / "pqrs_no_ruteo.yml"}
        for internal_name, internal_relpath in internal_workflows.items():
            if internal_name in flows:
                continue
            internal_path = self.workflows_directory / internal_relpath
            if not internal_path.exists():
                continue
            raw_internal = yaml.safe_load(internal_path.read_text(encoding="utf-8"))
            if isinstance(raw_internal, dict):
                flows[internal_name] = WorkflowDefinition.model_validate(raw_internal)

        shared_steps_path = self.workflows_directory / "shared_steps.yml"
        if shared_steps_path.exists():
            shared_raw = yaml.safe_load(shared_steps_path.read_text(encoding="utf-8"))
            if isinstance(shared_raw, dict):
                shared_steps = {
                    k: WorkflowStep.model_validate(v) for k, v in shared_raw.items()
                }
                for flow in flows.values():
                    for step_key, step_value in shared_steps.items():
                        flow.steps.setdefault(step_key, step_value)
                logger.info(
                    "Injected shared steps into all workflows shared_step_count=%s",
                    len(shared_steps),
                )

        return WorkflowCatalog(
            welcome=general_catalog.welcome,
            flows=flows,
        )

    @log_execution
    def _resolve_workflow_path(
        self,
        group_key: str,
        workflow_name: str,
    ) -> Path:
        """Resolve the YAML file path for a workflow inside its group folder."""

        logger.info(
            "Resolving workflow path group_key=%s workflow=%s",
            group_key,
            workflow_name,
        )
        nested_path = (
            self.workflows_directory
            / group_key
            / workflow_name
            / f"{workflow_name}.yml"
        )

        if nested_path.exists():
            logger.info(
                "Using nested workflow path workflow=%s nested_path=%s",
                workflow_name,
                nested_path,
            )
            return nested_path

        grouped_path = self.workflows_directory / group_key / f"{workflow_name}.yml"

        if grouped_path.exists():
            return grouped_path

        legacy_path = self.workflows_directory / f"{workflow_name}.yml"

        if legacy_path.exists():
            logger.info(
                "Using legacy workflow path workflow=%s legacy_path=%s",
                workflow_name,
                legacy_path,
            )
            return legacy_path

        return nested_path

    @log_execution
    def _handle_workflow_selection(
        self,
        conversation: Conversation,
        normalized_input: str,
    ) -> str:
        """Handle the greeting stage and workflow selection."""

        logger.info(
            "Handling workflow selection conversation_id=%s normalized_input=%s",
            conversation.conversation_id,
            normalized_input,
        )
        if len(conversation.messages) == 1 and conversation.general_workflow is None:
            conversation.current_step = "0"
            conversation.status = ConversationStatus.ACTIVE
            return self._build_welcome_message()

        if conversation.general_workflow is None:
            return self._handle_general_workflow_selection(
                conversation,
                normalized_input,
            )

        return self._handle_specific_workflow_selection(
            conversation,
            normalized_input,
        )

    @log_execution
    def _handle_general_workflow_selection(
        self,
        conversation: Conversation,
        normalized_input: str,
    ) -> str:
        """Handle the selection of a top-level general workflow group."""

        logger.info(
            "Handling general workflow selection conversation_id=%s normalized_input=%s",
            conversation.conversation_id,
            normalized_input,
        )
        selected_group = self._match_general_workflow(normalized_input)

        if selected_group is None:
            conversation.current_step = "0"
            return (
                "No pude identificar la categoria que deseas iniciar.\n\n"
                f"{self._build_welcome_message()}"
            )

        conversation.general_workflow = selected_group.label
        conversation.current_step = "0.1"
        conversation.status = ConversationStatus.ACTIVE
        return self._build_general_workflow_message(selected_group)

    @log_execution
    def _handle_specific_workflow_selection(
        self,
        conversation: Conversation,
        normalized_input: str,
    ) -> str:
        """Handle the selection of a concrete workflow inside a general group."""

        logger.info(
            "Handling specific workflow selection conversation_id=%s general_workflow=%s normalized_input=%s",
            conversation.conversation_id,
            conversation.general_workflow,
            normalized_input,
        )
        general_group = self._get_general_workflow_group(conversation.general_workflow)
        selected_workflow = self._match_workflow(general_group, normalized_input)

        if selected_workflow is None:
            switched_group = self._match_general_workflow(
                normalized_input,
                include_index=False,
            )

            if switched_group is not None:
                conversation.general_workflow = switched_group.label
                conversation.current_step = "0.1"
                return self._build_general_workflow_message(switched_group)

            conversation.current_step = "0.1"
            return (
                "No pude identificar el flujo que deseas iniciar.\n\n"
                f"{self._build_general_workflow_message(general_group)}"
            )

        workflow_definition = self._get_workflow_definition(selected_workflow.workflow)
        conversation.workflow = selected_workflow.workflow
        conversation.flow_version = workflow_definition.version
        conversation.current_step = workflow_definition.start_step
        conversation.status = ConversationStatus.ACTIVE

        return self._render_step_prompt(
            conversation,
            workflow_definition.start_step,
            workflow_definition.steps[workflow_definition.start_step],
        )

    @log_execution
    def _handle_workflow_step(
        self,
        conversation: Conversation,
        workflow_definition: WorkflowDefinition,
        current_step: WorkflowStep,
        normalized_input: str,
        raw_input: str,
    ) -> str:
        """Resolve a numbered workflow step and return the next assistant prompt."""

        logger.info(
            "Handling workflow step conversation_id=%s workflow=%s current_step=%s input_type=%s",
            conversation.conversation_id,
            conversation.workflow,
            conversation.current_step,
            current_step.input_type,
        )
        if current_step.input_type == "terminal" or current_step.terminal:
            conversation.status = ConversationStatus.CLOSED
            return current_step.question

        # "date"/"number" se comportan igual que "text": el front real pinta un
        # calendario o un campo de moneda, pero el motor solo guarda lo que llegue.
        if current_step.input_type in ("text", "date", "number"):
            self._store_answer(conversation, current_step, raw_input.strip())
            return self._advance_to_next_step(
                conversation,
                workflow_definition,
                current_step.next_step,
            )

        if current_step.input_type == "multi_select":
            return self._handle_multi_select_step(
                conversation=conversation,
                workflow_definition=workflow_definition,
                current_step=current_step,
                normalized_input=normalized_input,
                raw_input=raw_input,
            )

        # El botón "Formulario PQR" (key=pqr) se envía como opción sintética en
        # los mensajes de formulario PQRS; al oprimirlo, el flujo pasa siempre a
        # la verificación de satisfacción.
        if normalized_input.strip().lower() == "pqr":
            self._store_answer(conversation, current_step, "pqr")
            return self._advance_to_next_step(
                conversation,
                workflow_definition,
                "satisfaction_check",
            )

        selected_option, selected_key = self._match_step_option(
            current_step.options,
            normalized_input,
            self._dynamic_option_labels(conversation, conversation.current_step),
            self._dynamic_option_keys(conversation, conversation.current_step),
        )

        if selected_option is None:
            return (
                f"No pude identificar una opcion valida para el paso "
                f"{conversation.current_step}.\n\n"
                f"{self._render_step_prompt(conversation, conversation.current_step, current_step)}"
            )

        # Se guarda la key DINAMICA cuando existe (p. ej. movimiento_7 en la
        # pagina 2 del selector): lleva el indice ABSOLUTO que usan los
        # resolvedores. Sin keys dinamicas, la del YAML, como siempre.
        self._store_answer(conversation, current_step, selected_key or selected_option.key)
        return self._advance_to_next_step(
            conversation,
            workflow_definition,
            selected_option.next_step,
        )

    @log_execution
    def _advance_to_next_step(
        self,
        conversation: Conversation,
        workflow_definition: WorkflowDefinition,
        next_step_id: str | None,
    ) -> str:
        """Advance the conversation state to the next workflow step."""

        logger.info(
            "Advancing workflow step conversation_id=%s next_step_id=%s",
            conversation.conversation_id,
            next_step_id,
        )
        if not next_step_id:
            conversation.status = ConversationStatus.CLOSED
            return (
                "El flujo no tiene un siguiente paso configurado. "
                "La conversacion sera cerrada."
            )

        next_step = workflow_definition.steps[next_step_id]
        conversation.current_step = next_step_id
        conversation.status = (
            ConversationStatus.CLOSED
            if next_step.input_type == "terminal" or next_step.terminal
            else ConversationStatus.ACTIVE
        )

        return self._render_step_prompt(conversation, next_step_id, next_step)

    @log_execution
    def _render_step_prompt(
        self,
        conversation: Conversation,
        step_id: str,
        step: WorkflowStep,
    ) -> str:
        """Render a step using dynamic prompt data when available."""

        dynamic_prompt = conversation.captured_data.get(f"dynamic_prompt_{step_id}")

        if dynamic_prompt:
            logger.info(
                "Using dynamic step prompt conversation_id=%s step_id=%s",
                conversation.conversation_id,
                step_id,
            )
            return dynamic_prompt

        logger.debug(
            "No dynamic prompt found; using static prompt from workflow step_id=%s conversation_id=%s",
            step_id,
            conversation.conversation_id,
        )
        return self._format_step_prompt(step_id, step)

    def _dynamic_option_labels(
        self,
        conversation: Conversation,
        step_id: str,
    ) -> list[str] | None:
        """Etiquetas que el paso mostro de verdad, si las sobrescribio."""

        crudo = conversation.captured_data.get(f"dynamic_option_labels_{step_id}")
        if not crudo:
            return None
        try:
            etiquetas = json.loads(crudo)
        except (TypeError, ValueError):
            logger.warning(
                "Dynamic option labels ilegibles conversation_id=%s step_id=%s",
                conversation.conversation_id,
                step_id,
            )
            return None
        if not isinstance(etiquetas, list):
            return None
        return [str(e) for e in etiquetas]

    @log_execution
    def _build_welcome_message(self) -> str:
        """Build the greeting message that lists the available general workflows."""

        lines = [self.catalog.welcome.message, "", "Categorias disponibles:"]

        for index, group in enumerate(self.catalog.welcome.groups, start=1):
            lines.append(f"{index}. {group.label}")

        lines.append("")
        lines.append("Responde con la categoria que deseas iniciar.")
        return "\n".join(lines)

    @log_execution
    def _build_general_workflow_message(self, group: WorkflowSelectorGroup) -> str:
        """Build the message that lists workflows available inside a group."""

        logger.info(
            "Building general workflow message general_workflow=%s option_count=%s",
            group.label,
            len(group.options),
        )
        lines = [group.message, "", "Flujos disponibles:"]

        for index, option in enumerate(group.options, start=1):
            lines.append(f"{index}. {option.label}")

        lines.append("")
        lines.append("Responde con el nombre del flujo que deseas iniciar.")
        return "\n".join(lines)

    @log_execution
    def _find_workflow_selector_option(
        self,
        workflow_name: str,
    ) -> tuple[WorkflowSelectorGroup, WorkflowSelectorOption]:
        """Return the selector group and option associated with a workflow."""

        logger.info("Finding selector option workflow=%s", workflow_name)
        normalized_workflow_name = self._normalize_text(workflow_name)

        for group in self.catalog.welcome.groups:
            for option in group.options:
                if normalized_workflow_name == self._normalize_text(option.workflow):
                    return group, option

        raise ConfigurationError(
            "Workflow selector option not found in catalog.",
            details={"workflow": workflow_name},
        )

    @log_execution
    def get_limit_category(self, workflow_name: str) -> str:
        """Return the daily-interaction limit category for a workflow.

        Resolves the group that owns the workflow and returns its
        ``limit_category`` (data-driven from ``general.yml``). Falls back to
        ``"general"`` when the group does not declare one or the workflow is
        unknown, so the per-category cap never blocks on missing data.
        """

        try:
            group, _ = self._find_workflow_selector_option(workflow_name)
        except ConfigurationError:
            logger.warning(
                "Limit category fallback: workflow not found workflow=%s",
                workflow_name,
            )
            return "general"

        category = (group.limit_category or "").strip()
        return category or "general"

    @log_execution
    def get_limit_key(self, workflow_name: str) -> str:
        """Return the per-CASE daily-limit key for a workflow.

        Unlike :meth:`get_limit_category` (which groups several workflows under
        a shared category such as ``"general"``), the limit KEY is the workflow
        itself, so every one of the 20 cases keeps its OWN independent daily
        counter (max 3/day). Centrales de riesgo is counted at sub-flow
        granularity (``centrales_de_riesgo:<subflow>``) at step 1.4.1 in
        ``chat_service``, not here.

        Falls back to the workflow name (or ``"general"``) when the workflow is
        unknown, so the cap never blocks on missing data.
        """

        try:
            _, option = self._find_workflow_selector_option(workflow_name)
        except ConfigurationError:
            logger.warning(
                "Limit key fallback: workflow not found workflow=%s",
                workflow_name,
            )
            return (workflow_name or "").strip() or "general"

        key = (option.workflow or option.key or workflow_name or "").strip()
        return key or "general"

    @log_execution
    def get_all_limit_categories(self) -> set[str]:
        """Return the distinct daily-limit categories declared across groups.

        Used to decide whether a client has exhausted their FULL daily allowance
        (every limit category is capped) — the only per-turn condition that
        actually terminates the session. Data-driven from ``general.yml``.
        """

        categories: set[str] = set()
        for group in self.catalog.welcome.groups:
            category = (group.limit_category or "").strip()
            if category:
                categories.add(category)
        return categories

    @log_execution
    def _build_workflow_description(self, option: WorkflowSelectorOption) -> str:
        """Resolve the best available description for a workflow routing option."""

        if option.description:
            return option.description

        steps_preview = self._build_workflow_steps_preview(option.workflow)
        if steps_preview:
            first_preview = steps_preview[0]
            _, _, description = first_preview.partition(". ")
            if description:
                return description

        return option.label

    @log_execution
    def _build_workflow_steps_preview(self, workflow_name: str) -> list[str]:
        """Build a high-level ordered preview of the steps defined in a workflow."""

        workflow_definition = self._get_workflow_definition(workflow_name)
        preview_lines: list[str] = []
        seen_summaries: set[str] = set()

        for step_id in self._sort_step_ids(workflow_definition.steps.keys()):
            # Skip shared/non-numeric steps (e.g. satisfaction_check) — they are
            # internal steps not relevant for routing-catalog preview.
            if not step_id.split(".")[0].isdigit():
                continue
            step = workflow_definition.steps[step_id]
            summary = self._extract_step_summary(step)

            if not summary:
                continue

            normalized_summary = self._normalize_text(summary)
            if normalized_summary in seen_summaries:
                continue

            seen_summaries.add(normalized_summary)
            preview_lines.append(f"{step_id}. {summary}")

        return preview_lines

    @log_execution
    def _sort_step_ids(self, step_ids: list[str] | set[str]) -> list[str]:
        """Sort dotted numeric step identifiers in natural workflow order."""

        return sorted(
            step_ids,
            key=lambda step_id: [
                (0, int(part)) if part.isdigit() else (1, part)
                for part in step_id.split(".")
            ],
        )

    @log_execution
    def _extract_step_summary(self, step: WorkflowStep) -> str:
        """Extract a short readable summary from a workflow step question."""

        ignored_summaries = {
            "gracias por comunicarte.",
            "lo siento, pero aun no puedo hacer esto. gracias por comunicarte.",
        }

        lines = [line.strip() for line in step.question.splitlines() if line.strip()]

        summary = ""
        for line in lines:
            cleaned_line = line.replace("`", "").replace("**", "").lstrip("#").strip()
            if cleaned_line:
                summary = cleaned_line
                break

        if not summary:
            return ""

        normalized_summary = self._normalize_text(summary)
        if normalized_summary in ignored_summaries:
            return ""

        if normalized_summary.startswith("hola") and step.input_type == "choice":
            return "Identificar el tipo de consulta inicial."

        return summary.rstrip(":")

    @log_execution
    def _format_step_prompt(self, step_id: str, step: WorkflowStep) -> str:
        """Render a numbered workflow step for the assistant response."""

        logger.info(
            "Formatting workflow prompt step_id=%s input_type=%s",
            step_id,
            step.input_type,
        )
        if step.input_type == "terminal" or step.terminal:
            return step.question

        return step.question

    @log_execution
    def _get_workflow_definition(
        self,
        workflow: str,
    ) -> WorkflowDefinition:
        """Return the workflow definition associated with a workflow enum."""

        logger.info("Getting workflow definition workflow=%s", workflow)
        try:
            return self.catalog.flows[workflow]
        except KeyError as exc:
            raise ConfigurationError(
                "Workflow definition not found in catalog.",
                details={"workflow": workflow},
            ) from exc

    @log_execution
    def _get_general_workflow_group(
        self,
        general_workflow: str | None,
    ) -> WorkflowSelectorGroup:
        """Return the general workflow group associated with the conversation."""

        logger.info(
            "Getting general workflow group general_workflow=%s", general_workflow
        )
        if general_workflow is None:
            raise ConfigurationError(
                "General workflow group was not selected.",
                details={"general_workflow": general_workflow},
            )

        normalized_general_workflow = self._normalize_text(general_workflow)

        for group in self.catalog.welcome.groups:
            if normalized_general_workflow in {
                self._normalize_text(group.key),
                self._normalize_text(group.label),
            }:
                return group

        raise ConfigurationError(
            "General workflow group not found in catalog.",
            details={"general_workflow": general_workflow},
        )

    @log_execution
    def _match_general_workflow(
        self,
        normalized_input: str,
        *,
        include_index: bool = True,
    ) -> WorkflowSelectorGroup | None:
        """Match user input to one of the available general workflow groups."""

        logger.info(
            "Matching general workflow normalized_input=%s include_index=%s",
            normalized_input,
            include_index,
        )
        for index, group in enumerate(self.catalog.welcome.groups, start=1):
            candidates = {
                self._normalize_text(group.key),
                self._normalize_text(group.label),
            }

            if include_index:
                candidates.add(str(index))

            if normalized_input in candidates:
                return group

        return None

    @log_execution
    def _match_workflow(
        self,
        group: WorkflowSelectorGroup,
        normalized_input: str,
    ) -> WorkflowSelectorOption | None:
        """Match user input to one of the workflows inside a general group."""

        logger.info(
            "Matching workflow normalized_input=%s general_workflow=%s option_count=%s",
            normalized_input,
            group.label,
            len(group.options),
        )
        for index, option in enumerate(group.options, start=1):
            candidates = {
                self._normalize_text(option.key),
                self._normalize_text(option.label),
                str(index),
            }

            if normalized_input in candidates:
                return option

        return None

    @log_execution
    def _dynamic_option_keys(
        self,
        conversation: Conversation,
        step_id: str,
    ) -> list[str] | None:
        """Keys que el paso publico de verdad, si las sobrescribio (H-02)."""

        crudo = conversation.captured_data.get(f"dynamic_option_keys_{step_id}")
        if not crudo:
            return None
        try:
            keys = json.loads(crudo)
        except (TypeError, ValueError):
            return None
        if not isinstance(keys, list):
            return None
        return [str(k) for k in keys]

    @log_execution
    def _match_step_option(
        self,
        options: list[WorkflowStepOption],
        normalized_input: str,
        dynamic_labels: list[str] | None = None,
        dynamic_keys: list[str] | None = None,
    ) -> tuple[WorkflowStepOption | None, str]:
        """Match user input to a step option by numeric order, key, or label.

        `dynamic_labels` son las etiquetas que el cliente ve de verdad cuando
        el paso las sobrescribe en tiempo de ejecucion (productos, movimientos).
        Sin ellas solo casaban las del YAML ("Producto 1"), que ya nadie ve, y
        devolver la etiqueta mostrada no avanzaba el paso.
        """

        logger.info(
            "Matching step option normalized_input=%s option_count=%s dynamic=%s",
            normalized_input,
            len(options),
            bool(dynamic_labels),
        )
        yaml_por_key = {self._normalize_text(o.key): o for o in options}
        for index, option in enumerate(options, start=1):
            candidates = {
                self._normalize_text(option.key),
                self._normalize_text(option.label),
                str(index),
            }
            dyn_key = ""
            if dynamic_keys and index <= len(dynamic_keys):
                dyn_key = str(dynamic_keys[index - 1])
                candidates.add(self._normalize_text(dyn_key))
            if dynamic_labels and index <= len(dynamic_labels):
                candidates.add(self._normalize_text(dynamic_labels[index - 1]))

            if normalized_input in candidates:
                # Con paginacion, las opciones FIJAS (no_encuentro,
                # mas_movimientos) cambian de posicion segun cuantos
                # movimientos trae la pagina: el destino lo manda la key
                # dinamica si es una key declarada en el YAML; si no
                # (movimiento_7), la casilla posicional del YAML.
                ruta = yaml_por_key.get(self._normalize_text(dyn_key)) if dyn_key else None
                return (ruta or option), dyn_key

        return None, ""

    @log_execution
    def _store_answer(
        self,
        conversation: Conversation,
        step: WorkflowStep,
        answer: str,
    ) -> None:
        """Persist the normalized user answer on the runtime conversation."""

        logger.info(
            "Storing workflow answer conversation_id=%s current_step=%s save_as=%s answer=%s",
            conversation.conversation_id,
            conversation.current_step,
            step.save_as,
            answer,
        )
        if step.save_as:
            conversation.flow_answers[step.save_as] = answer

    @log_execution
    def _normalize_text(self, value: str) -> str:
        """Normalize a user input value for workflow matching."""

        normalized_value = unicodedata.normalize("NFKD", value.strip().casefold())
        return "".join(
            character
            for character in normalized_value
            if not unicodedata.combining(character)
        )


    @log_execution
    def _handle_multi_select_step(
        self,
        *,
        conversation: Conversation,
        workflow_definition: WorkflowDefinition,
        current_step: WorkflowStep,
        normalized_input: str,
        raw_input: str,
    ) -> str:
        """Procesa selección múltiple sin avanzar de paso."""

        del raw_input

        conversation.captured_data.pop(MULTI_SELECT_REFRESH_KEY, None)

        selected_option, selected_key = self._match_step_option(
            current_step.options,
            normalized_input,
            self._dynamic_option_labels(
                conversation,
                conversation.current_step,
            ),
            self._dynamic_option_keys(
                conversation,
                conversation.current_step,
            ),
        )

        if selected_option is None:
            prompt = self._render_step_prompt(
                conversation,
                conversation.current_step,
                current_step,
            )
            return (
                f"No pude identificar una opcion valida para el paso "
                f"{conversation.current_step}.\n\n"
                f"{prompt}"
            )

        option_key = str(selected_key or selected_option.key)

        # El hook de Doble Cobro aplica el toggle/paginacion leyendo
        # esta respuesta desde flow_answers.
        self._store_answer(
            conversation,
            current_step,
            option_key,
        )

        if option_key in {
            "reportar_seleccionados",
            "no_encuentro",
        }:
            return self._advance_to_next_step(
                conversation,
                workflow_definition,
                selected_option.next_step,
            )

        # Casilla o paginacion: el paso no se mueve y la respuesta REEMPLAZA
        # a la tarjeta anterior, no se encola detras de ella.
        conversation.captured_data[MULTI_SELECT_REFRESH_KEY] = "true"
        return self._render_step_prompt(
            conversation,
            conversation.current_step,
            current_step,
        )


    @log_execution
    def _store_multi_select_answer(
        self,
        conversation: Conversation,
        step: WorkflowStep,
        values: list[str],
    ) -> None:
        """Persiste la selección múltiple como JSON."""

        if not step.save_as:
            return

        conversation.flow_answers[step.save_as] = json.dumps(
            values,
            ensure_ascii=False,
        )

        logger.info(
            "Storing multi-select answer "
            "conversation_id=%s step=%s save_as=%s values=%s",
            conversation.conversation_id,
            conversation.current_step,
            step.save_as,
            values,
        )