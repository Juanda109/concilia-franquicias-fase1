"""Chat example routes."""

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from application.chat.chat_service import (
    get_conversation_snapshot,
    process_chat_message_with_timeout,
    process_end_conversation,
    process_start_message,
)
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from domain.workflow.models import WorkflowStepOption
from domain.workflow.workflow_engine import WorkflowEngine
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from infrastructure.core.logger import bind_correlation, log_execution
from infrastructure.entrypoint.api.dependencies import (
    get_app_logger,
    get_back_data_service_url,
    get_control_table_store,
    get_conversation_store,
    get_strands_workflow_agent,
    get_trx_service_url,
    get_workflow_engine,
)
from infrastructure.entrypoint.api.errors.exceptions import AgentepqrError
from infrastructure.entrypoint.api.router.v0.model.chat_models import (
    ChatMessageContent,
    ChatMessageEnvelope,
    ChatMessageOption,
    ChatRequest,
    ChatResponse,
    EndRequest,
    EndResponse,
    MessageInputType,
    PollingData,
    PollingRequest,
    PollingResponse,
    StartMessageContent,
    StartMessageEnvelope,
    StartRequest,
    StartResponse,
)
from infrastructure.genai.llm.strands_workflow_agent import StrandsWorkflowAgent
from infrastructure.observability.benchmark_context import set_model
from infrastructure.persistence.control_table_store import ControlTableStore
from infrastructure.persistence.conversation_store import ConversationStore

router = APIRouter()
_START_ROUTING_STATE_KEY = "start_routing_state"
_START_ROUTING_WORKFLOW_KEY = "start_routing_workflow"
_START_ROUTING_PENDING_STATE = "pending_confirmation"


_WAITING_MESSAGE_TEXT = (
    "Estoy revisando tu información, por favor espera un momento..."
)

_BENCHMARK_TIMEOUT_SECONDS = 120.0


def _build_waiting_message() -> ChatMessageEnvelope:
    """Return a static in-progress message while an async turn is still processing."""

    return ChatMessageEnvelope(
        message_id=str(uuid4()),
        sender="bot",
        timestamp=datetime.now(UTC),
        input_type="text",
        content=ChatMessageContent(label=_WAITING_MESSAGE_TEXT),
    )


def _raise_http_error(exc: AgentepqrError) -> None:
    """Translate a domain/application error into an HTTPException."""

    raise HTTPException(
        status_code=exc.http_status_code,
        detail=exc.to_dict()["error"],
    ) from exc


def _normalize_display_text(value: str) -> str:
    """Normalize markdown-like prompt fragments for frontend rendering."""

    normalized_lines: list[str] = []

    for line in value.splitlines():
        stripped_line = line.strip()

        if not stripped_line:
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue

        if stripped_line:
            normalized_lines.append(stripped_line)

    return "\n".join(normalized_lines).strip()


def _build_choice_options(
    *,
    step_options: list[WorkflowStepOption],
    option_labels_override: list[str] | None = None,
    option_keys_override: list[str] | None = None,
) -> list[ChatMessageOption]:
    """Build structured options for a workflow choice step.

    When a dynamic label override is provided (e.g. the customer products
    resolved at runtime from ASO), the option list is truncated to the number of
    override labels so the frontend only renders the options that were actually
    found, instead of the full set of static placeholders declared in the YAML.
    The keys stay positional (``producto_1`` … ``producto_N``), which keeps the
    downstream selection mapping intact.
    """

    effective_options = step_options
    if option_labels_override is not None:
        effective_options = step_options[: len(option_labels_override)]

    # Las keys son POSICIONALES respecto al YAML. Cuando el paso pinta una
    # lista variable (movimientos), la ultima opcion fija -- "no encuentro"
    # -- caia en la key del hueco que ocupaba, y el flujo la interpretaba
    # como si el cliente hubiera elegido un movimiento inexistente. Con el
    # override de keys, quien construye la lista declara a que destino va
    # cada boton y deja de depender del orden del YAML.
    return [
        ChatMessageOption(
            key=(
                option_keys_override[index]
                if option_keys_override and index < len(option_keys_override)
                else option.key
            ),
            label=(
                option_labels_override[index]
                if option_labels_override and index < len(option_labels_override)
                else _normalize_display_text(option.label)
            ),
        )
        for index, option in enumerate(effective_options)
    ]


def _build_confirmation_options() -> list[ChatMessageOption]:
    """Build the structured continue/exit options for a pending start confirmation."""

    return [
        ChatMessageOption(key="continuar", label="Continuar"),
        ChatMessageOption(key="salir", label="Salir"),
    ]


def _build_repeat_flow_options() -> list[ChatMessageOption]:
    """Build the structured yes/no options for a repeated-flow warning."""

    return [
        ChatMessageOption(key="continuar", label="Continuar con otra solicitud"),
        ChatMessageOption(key="salir", label="No, gracias"),
    ]


def _is_pending_start_confirmation(conversation: Conversation) -> bool:
    """Return whether the conversation is waiting for workflow confirmation."""

    return conversation.captured_data.get(
        _START_ROUTING_STATE_KEY
    ) == _START_ROUTING_PENDING_STATE and bool(
        conversation.captured_data.get(_START_ROUTING_WORKFLOW_KEY)
    )


def _is_pending_repeat_flow_warning(conversation: Conversation) -> bool:
    return conversation.captured_data.get(
        "repeat_flow_warning_state"
    ) == "pending_confirmation" and bool(
        conversation.captured_data.get("repeat_flow_workflow")
    )


def _is_pending_pqrs_clarify_continue(conversation: Conversation) -> bool:
    """Whether the conversation is on step 1 of the PQR-causal clarification.

    En ese paso mostramos un boton "Continuar" para que el cliente pase a
    describir el motivo de su PQR (ver _resolve_start_phase en chat_service).
    """

    return (
        conversation.captured_data.get("pqrs_clarify_state") == "await_continue"
    )


def _build_pqrs_clarify_options() -> list[ChatMessageOption]:
    """Build the single 'Continuar' option for the PQR-causal clarification."""

    return [ChatMessageOption(key="continuar", label="Continuar")]


def _build_message_content(
    *,
    conversation: Conversation,
    assistant_content: str,
    workflow_engine: WorkflowEngine,
) -> ChatMessageContent:
    """Serialize the assistant message into the frontend-friendly shape."""

    if _is_pending_start_confirmation(conversation):
        label_lines = [
            line
            for line in assistant_content.splitlines()
            if not line.startswith('Si este es el flujo correcto, responde "si"')
            and not line.startswith('Si no corresponde a tu necesidad, responde "no"')
            and not line.startswith('Responde "continuar"')
        ]
        return ChatMessageContent(
            label=_normalize_display_text("\n".join(label_lines)),
            options=_build_confirmation_options(),
        )

    if _is_pending_repeat_flow_warning(conversation):
        return ChatMessageContent(
            label=_normalize_display_text(assistant_content),
            options=_build_repeat_flow_options(),
        )

    if _is_pending_pqrs_clarify_continue(conversation):
        return ChatMessageContent(
            label=_normalize_display_text(assistant_content),
            options=_build_pqrs_clarify_options(),
        )

    # El formulario PQRS ya NO se envía como link inline en el texto: se envía
    # como un botón {key:"pqr", label:"Formulario PQR"}. La señal
    # ``centrales_riesgo_form_option`` marca que el mensaje actual es un
    # formulario PQRS; al oprimir el botón, el ruteo lleva a satisfaction_check.
    if conversation.captured_data.get("centrales_riesgo_form_option"):
        return ChatMessageContent(
            label=_normalize_display_text(assistant_content),
            options=[ChatMessageOption(key="pqr", label="Formulario PQR")],
        )

    if conversation.status == ConversationStatus.ERROR:
        return ChatMessageContent(
            label=_normalize_display_text(assistant_content),
            options=[],
        )

    current_step_data = workflow_engine.get_current_step(conversation)

    if current_step_data is None:
        return ChatMessageContent(
            label=_normalize_display_text(assistant_content),
            options=[],
        )

    _, current_step = current_step_data

    # NOTA: el formulario de PQRS NUNCA se envía como botón; va como link inline
    # en el texto del mensaje. Los botones se reservan para menús (smart_route),
    # satisfacción (sí/no), confirmaciones (continuar/salir) y selección de producto.

    if current_step.input_type in {"choice", "multi_select"} and current_step.options:
        step_id = current_step_data[0]
        label = _normalize_display_text(assistant_content)
        raw_labels = conversation.captured_data.get(f"dynamic_option_labels_{step_id}")
        option_labels_override = json.loads(raw_labels) if raw_labels else None
        raw_keys = conversation.captured_data.get(f"dynamic_option_keys_{step_id}")
        option_keys_override = json.loads(raw_keys) if raw_keys else None
        return ChatMessageContent(
            label=label or _normalize_display_text(current_step.question),
            options=_build_choice_options(
                step_options=current_step.options,
                option_labels_override=option_labels_override,
                option_keys_override=option_keys_override,
            ),
        )

    return ChatMessageContent(
        label=_normalize_display_text(assistant_content),
        options=[],
    )


def _get_latest_assistant_message(conversation: Conversation) -> Message:
    """Return the most recent assistant message available in the conversation."""

    for message in reversed(conversation.messages):
        if message.role == MessageRole.ASSISTANT:
            return message

    return conversation.messages[-1]


def _resolve_message_input_type(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
    default_input_type: MessageInputType = "text",
) -> MessageInputType:
    """Resolve the input type associated with the current assistant response."""

    if _is_pending_start_confirmation(conversation):
        return "choice"

    if _is_pending_pqrs_clarify_continue(conversation):
        return "choice"

    if conversation.captured_data.get("centrales_riesgo_form_option"):
        return "choice"

    if conversation.status == ConversationStatus.ERROR:
        return default_input_type

    current_step_data = workflow_engine.get_current_step(conversation)
    if current_step_data is None:
        return default_input_type

    _, current_step = current_step_data
    return current_step.input_type


def _build_start_response_message(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
) -> StartMessageEnvelope:
    """Build the structured assistant message returned by `POST /start`.

    `POST /start` es idempotente y REANUDA una sesion en curso (Arquitectura
    A). Al reanudar sobre un paso de opciones hay que devolver sus botones y
    el input_type real: serializarlo siempre como texto plano dejaba al
    cliente viendo la pregunta sin nada que pulsar -- p.ej. recargar el front
    en el paso del Formulario PQR. Para el saludo inicial no hay opciones y
    la respuesta es identica a la de antes.
    """

    assistant_message = _get_latest_assistant_message(conversation)
    timestamp = (
        assistant_message.timing.responded_at or assistant_message.timing.received_at
    )
    content = _build_message_content(
        conversation=conversation,
        assistant_content=assistant_message.content,
        workflow_engine=workflow_engine,
    )

    return StartMessageEnvelope(
        sender="bot",
        timestamp=timestamp,
        input_type=_resolve_message_input_type(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
        content=StartMessageContent(
            label=content.label,
            options=content.options,
        ),
    )


def _build_chat_response_message(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
) -> ChatMessageEnvelope:
    """Build the structured assistant message returned by `POST /chat` and `POST /end`."""

    assistant_message = _get_latest_assistant_message(conversation)
    timestamp = (
        assistant_message.timing.responded_at or assistant_message.timing.received_at
    )

    return ChatMessageEnvelope(
        message_id=assistant_message.id,
        sender="bot",
        timestamp=timestamp,
        input_type=_resolve_message_input_type(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
        content=_build_message_content(
            conversation=conversation,
            assistant_content=assistant_message.content,
            workflow_engine=workflow_engine,
        ),
    )


def _log_received_event(
    *,
    logger: logging.Logger,
    event_name: str,
    payload: StartRequest | ChatRequest,
) -> None:
    """Log the full inbound event payload (DEBUG) when the request reaches the route."""

    logger.debug("Received %s event:\n%s", event_name, payload.model_dump_json(indent=2))


def _customer_id_from_conversation_id(conversation_id: str) -> str:
    """Extract the customer id prefix from a `<customer_id>_<yyyymmdd>` value."""

    return conversation_id.rsplit("_", maxsplit=1)[0] if "_" in conversation_id else conversation_id


def _safe_excerpt(text: str | None, limit: int = 30) -> str:
    """Return the first `limit` chars on a single line, for log tracing.

    NOTE: this surfaces a short snippet of the user's message in the terminal
    logs (and the log pipeline). Kept intentionally short for traceability.
    """

    if not text:
        return ""
    return text[:limit].replace("\n", " ").replace("\r", " ")


@router.post(
    "/start",
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
    tags=["start"],
)
@log_execution
async def start_conversation(
    payload: StartRequest,
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
    workflow_engine: WorkflowEngine = Depends(get_workflow_engine),
    control_store: ControlTableStore = Depends(get_control_table_store),
    x_benchmark_mode: str | None = Header(default=None),
) -> StartResponse:
    """Create a conversation and return the configured assistant greeting.

    The ``X-Benchmark-Mode`` header (benchmark/canary client) marks the
    conversation persistently as ``source="benchmark"`` for analytics.
    """

    bind_correlation(customer_id=str(payload.user_id))
    _log_received_event(logger=logger, event_name="start", payload=payload)
    logger.info(
        "Received start request user_id=%s content_length=%s content_excerpt=%r",
        payload.user_id,
        len(payload.content or ""),
        _safe_excerpt(payload.content, 30),
    )

    try:
        conversation = await process_start_message(
            benchmark_mode=bool(x_benchmark_mode),
            user_id=str(payload.user_id),
            store=store,
            control_store=control_store,
        )
    except AgentepqrError as exc:
        logger.warning(
            "Start request rejected user_id=%s error_code=%s message=%s",
            payload.user_id,
            exc.error_code,
            exc.message,
        )
        _raise_http_error(exc)

    bind_correlation(conversation_id=conversation.conversation_id)
    logger.info(
        "Completed start request conversation_id=%s current_step=%s status=%s message_count=%s",
        conversation.conversation_id,
        conversation.current_step,
        conversation.status.value,
        len(conversation.messages),
    )
    logger.debug(
        "Conversation state after start:\n%s", conversation.model_dump_json(indent=2)
    )

    return StartResponse(
        status=conversation.status.value,
        conversation_id=conversation.conversation_id,
        message=_build_start_response_message(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Receive a chat message",
    tags=["chat"],
    responses={
        201: {
            "description": "Message processed or still running — body always present.",
        }
    },
)
@log_execution
async def receive_chat_message(
    payload: ChatRequest,
    x_benchmark_mode: str | None = Header(default=None),
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
    workflow_engine: WorkflowEngine = Depends(get_workflow_engine),
    strands_agent: StrandsWorkflowAgent = Depends(get_strands_workflow_agent),
    control_store: ControlTableStore = Depends(get_control_table_store),
    back_data_service_url: str | None = Depends(get_back_data_service_url),
    trx_service_url: str | None = Depends(get_trx_service_url),
) -> Response:
    """Receive a chat payload, persist workflow context, and return the next prompt."""

    bind_correlation(
        conversation_id=str(payload.conversation_id),
        customer_id=_customer_id_from_conversation_id(str(payload.conversation_id)),
    )
    _log_received_event(logger=logger, event_name="chat", payload=payload)
    logger.info(
        "Received chat request conversation_id=%s content_length=%s content_excerpt=%r",
        payload.conversation_id,
        len(payload.content),
        _safe_excerpt(payload.content, 30),
    )

    benchmark_on = bool(x_benchmark_mode)
    if benchmark_on:
        set_model(strands_agent.model_id)

    timeout_kwargs = (
        {"processing_timeout_seconds": _BENCHMARK_TIMEOUT_SECONDS}
        if benchmark_on
        else {}
    )

    try:
        conversation = await process_chat_message_with_timeout(
            content=payload.content,
            conversation_id=str(payload.conversation_id),
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            control_store=control_store,
            back_data_service_url=back_data_service_url,
            trx_service_url=trx_service_url,
            **timeout_kwargs,
        )
    except AgentepqrError as exc:
        logger.warning(
            "Chat request rejected conversation_id=%s error_code=%s message=%s",
            payload.conversation_id,
            exc.error_code,
            exc.message,
        )
        _raise_http_error(exc)

    if conversation is None:
        logger.info(
            "Chat request still running conversation_id=%s — returning waiting message",
            payload.conversation_id,
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=json.loads(
                ChatResponse(
                    status=ConversationStatus.RUNNING.value,
                    conversation_id=str(payload.conversation_id),
                    message=_build_waiting_message(),
                ).model_dump_json()
            ),
        )

    logger.info(
        "Completed chat request conversation_id=%s current_step=%s status=%s message_count=%s",
        conversation.conversation_id,
        conversation.current_step,
        conversation.status.value,
        len(conversation.messages),
    )
    logger.debug("Conversation state:\n%s", conversation.model_dump_json(indent=2))

    # Pausa de prueba desactivada (experimento temporal; bloqueaba la respuesta
    # 8s y excedía el presupuesto ~5s del front):
    # if (
    #     conversation.status == ConversationStatus.CLOSED
    #     and conversation.satisfaction_result is not None
    # ):
    #     await asyncio.sleep(8)

    return ChatResponse(
        status=conversation.status.value,
        conversation_id=payload.conversation_id,
        message=_build_chat_response_message(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
    )


@router.post(
    "/polling",
    response_model=PollingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check whether an async chat turn has finished",
    tags=["polling"],
    responses={
        303: {
            "description": "The async chat turn finished — follow Location header to GET /polling/{id}.",
        },
    },
)
@log_execution
async def poll_conversation_status(
    payload: PollingRequest,
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
) -> PollingResponse | Response:
    """Check whether the latest async chat turn has finished processing."""

    bind_correlation(
        conversation_id=str(payload.conversation_id),
        customer_id=_customer_id_from_conversation_id(str(payload.conversation_id)),
    )
    logger.info(
        "Received polling request conversation_id=%s",
        payload.conversation_id,
    )

    try:
        conversation = await get_conversation_snapshot(
            conversation_id=str(payload.conversation_id),
            store=store,
        )
    except AgentepqrError as exc:
        logger.warning(
            "Polling request rejected conversation_id=%s error_code=%s",
            payload.conversation_id,
            exc.error_code,
        )
        _raise_http_error(exc)

    if conversation.status == ConversationStatus.RUNNING:
        polling_response = PollingResponse(data=PollingData(status=conversation.status.value))
        logger.info(
            "Polling response status=201 conversation_id=%s body=%s",
            payload.conversation_id,
            polling_response.model_dump_json(),
        )
        return polling_response

    polling_location = f"/polling/{payload.conversation_id}"
    logger.info(
        "Polling response status=303 conversation_id=%s location=%s body=<empty>",
        payload.conversation_id,
        polling_location,
    )
    return Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": polling_location},
    )


@router.get(
    "/polling/{conversation_id}",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the latest bot message for a conversation",
    tags=["polling"],
)
@log_execution
async def get_polling_message(
    conversation_id: str,
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
    workflow_engine: WorkflowEngine = Depends(get_workflow_engine),
) -> Response:
    """Return the latest assistant message once polling indicates completion."""

    bind_correlation(
        conversation_id=str(conversation_id),
        customer_id=_customer_id_from_conversation_id(str(conversation_id)),
    )
    logger.info("Received polling message request conversation_id=%s", conversation_id)

    try:
        conversation = await get_conversation_snapshot(
            conversation_id=str(conversation_id),
            store=store,
        )
    except AgentepqrError as exc:
        logger.warning(
            "Polling message request rejected conversation_id=%s error_code=%s",
            conversation_id,
            exc.error_code,
        )
        _raise_http_error(exc)

    if conversation.status == ConversationStatus.RUNNING:
        logger.info(
            "Polling message request still running conversation_id=%s — returning waiting message",
            conversation_id,
        )
        return ChatResponse(
            status=conversation.status.value,
            conversation_id=conversation_id,
            message=_build_waiting_message(),
        )

    # Pausa de prueba desactivada (experimento temporal; bloqueaba la respuesta
    # 8s y excedía el presupuesto ~5s del front):
    # if (
    #     conversation.status == ConversationStatus.CLOSED
    #     and conversation.satisfaction_result is not None
    # ):
    #     await asyncio.sleep(8)

    return ChatResponse(
        status=conversation.status.value,
        conversation_id=conversation_id,
        message=_build_chat_response_message(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
    )


@router.post(
    "/end",
    status_code=status.HTTP_201_CREATED,
    summary="End a conversation",
    tags=["end"],
)
@log_execution
async def end_conversation(
    payload: EndRequest,
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
    workflow_engine: WorkflowEngine = Depends(get_workflow_engine),
) -> EndResponse:
    """
    Finaliza formalmente la conversación, cierra el flujo de trabajo activo
    y persiste el estado final.
    """

    logger.info("Received end request conversation_id=%s", payload.conversation_id)

    bind_correlation(
        conversation_id=str(payload.conversation_id),
        customer_id=_customer_id_from_conversation_id(str(payload.conversation_id)),
    )

    try:
        # Llamada al servicio de aplicación para manejar la lógica de cierre
        conversation = await process_end_conversation(
            conversation_id=str(payload.conversation_id),
            store=store,
        )
    except AgentepqrError as exc:
        logger.warning(
            "End request failed conversation_id=%s error_code=%s",
            payload.conversation_id,
            exc.error_code,
        )
        _raise_http_error(exc)

    logger.info(
        "Conversation finalized conversation_id=%s status=%s",
        conversation.conversation_id,
        conversation.status.value,
    )

    return EndResponse(
        status=conversation.status.value,
        conversation_id=payload.conversation_id,
        message=_build_chat_response_message(
            conversation=conversation,
            workflow_engine=workflow_engine,
        ),
    )
