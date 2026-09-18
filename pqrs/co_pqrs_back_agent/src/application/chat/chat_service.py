"""Application service for chat conversation updates."""

import asyncio
import json
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from application.chat.trx_state import (
    TRX_STATE_KEY,
    get_trx_state,
    reset_per_tx,
    trx_snapshot,
    update_trx_state,
)
from application.chat.workflow_actions import execute_workflow_action
from application.chat.workflow_hooks import get_prefetch_hook
import application.chat.workflows  # noqa: F401 (side-effect: registers per-workflow hooks)
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from domain.genai.llm.models import WorkflowRoutingDecision
from domain.workflow.general_messages import load_general_messages
from domain.workflow.group_prefilter import filter_catalog_by_groups
from domain.workflow.workflow_engine import (
    MULTI_SELECT_REFRESH_KEY,
    WorkflowEngine,
)
from guardrail import accepts_routing, screen_user_input
from guardrail.judge import has_banking_signals, judge_user_message
from infrastructure.core.config import (
    load_back_data_service_url,
    load_end_conversation_callback_url,
    load_env_constants,
    load_max_daily_category_interactions,
    load_max_daily_sessions,
    load_rabbitmq_settings,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import (
    ResourceNotFoundError,
)
from infrastructure.genai.llm.strands_workflow_agent import StrandsWorkflowAgent
from infrastructure.messaging.event_publisher import EventPublisher
from infrastructure.observability.benchmark_context import (
    is_active as _benchmark_context_active,
    mark_final_step,
    mark_routing_decision,
    mark_routing_done,
)
from infrastructure.observability.error_audit import schedule_error_report
from infrastructure.observability.trace_audit import schedule_trace_event
from infrastructure.persistence.back_data_client import (
    fetch_customer_given_name,
    trigger_centrales_no_autorizo,
    trigger_consultar,
    trigger_notificacion_centrales,
    trigger_notificacion_centrales_producto,
)
from infrastructure.core.config import (
    load_authorization_service_url,
)
from infrastructure.persistence.authorization_client import (
    consultar_autorizacion,
    registrar_autorizacion,
)
from infrastructure.persistence.trx_client import (
    consultar_productos_activos,
    consultar_trx,
    validar_recurrencia,
    obtener_card_id,
    movimientos_aso,
    movimientos_pagina,
    detalle_trx,
    bloqueo_trx,
    subida_nivel_estado_trx,
    subida_nivel_trx,
    fetch_trx_customer_address,
    fetch_trx_account_identity,
)
from application.chat.trx_state import (
    get_trx_state,
    update_trx_state,
    reset_per_tx,
    trx_snapshot,
)
from infrastructure.persistence.trx_case_store import TrxCaseStore
from infrastructure.persistence.control_table_store import ControlTableStore
from infrastructure.persistence.conversation_store import ConversationStore
from infrastructure.persistence.maintenance_client import trigger_archive_conversation
from infrastructure.persistence.trx_case_store import TrxCaseStore
from infrastructure.persistence.trx_client import (
    bloqueo_trx,
    consultar_productos_activos,
    detalle_trx,
    movimientos_aso,
    movimientos_pagina,
    obtener_card_id,
    validar_recurrencia,
)

logger = get_logger(__name__)

DEFAULT_USER_ID = "anonymous"
_START_ROUTING_STATE_KEY = "start_routing_state"
_START_ROUTING_WORKFLOW_KEY = "start_routing_workflow"
_START_ROUTING_CONFIDENCE_KEY = "start_routing_confidence"
_START_ROUTING_RATIONALE_KEY = "start_routing_rationale"
_START_ROUTING_ENTRY_HINT_KEY = "start_routing_entry_hint"
_START_ROUTING_PENDING_STATE = "pending_confirmation"
_WORKFLOW_ENTRY_HINT_KEY = "workflow_entry_hint"
_REPEAT_FLOW_WARNING_STATE_KEY = "repeat_flow_warning_state"
_REPEAT_FLOW_WORKFLOW_KEY = "repeat_flow_workflow"
_REPEAT_FLOW_LABEL_KEY = "repeat_flow_label"
_REPEAT_FLOW_PENDING_STATE = "pending_confirmation"
# Centrales de riesgo is the only case counted at SUB-FLOW granularity: its
# daily 3/day cap applies to each of its 3 situations (step 1.4.1) separately,
# NOT to the workflow as a whole. The per-subflow limit key is
# ``centrales_de_riesgo:<subflow_option_key>``; the generic start-time cap is
# SKIPPED for this workflow and handled at the 1.4.1 transition instead.
_CENTRALES_WORKFLOW = "centrales_de_riesgo"
_CENTRALES_SUBFLOW_STEP = "1.4.1"
# The answer key saved by step 1.4.1 that identifies the chosen sub-flow.
_CENTRALES_SUBFLOW_ANSWER = "tipo_inconveniente_centrales_de_riesgo"
# Natural labels for the centrales sub-flows, used in the repeat-flow warning
# ("...una consulta relacionada a {label}..."). Keys match the 1.4.1 options.
_CENTRALES_SUBFLOW_LABELS = {
    "reporte_no_reconocido_o_incorrecto": "tu reporte en centrales de riesgo",
    "embargo_o_desembargo": "tu embargo o desembargo",
    "cartera_vendida_o_cedida": "la venta o cesión de tu cartera",
    "consulta_sin_permiso": (
        "la consulta de tu información en centrales sin autorización"
    ),
    "reporte_negativo_sin_notificacion": (
        "tu reporte negativo sin notificación en centrales"
    ),
}
# Marks a conversation whose SESSION was terminated by a limit (daily session
# cap, exhausted repeat-flow rechecks, or an explicit decline). Unlike a normal
# consultation terminal — which Architecture A reopens to the start phase — a
# limit-terminated session stays CLOSED so the user cannot keep asking, and any
# further /chat is answered from cache WITHOUT invoking the LLM (no tokens).
_SESSION_LIMIT_CLOSED_KEY = "session_limit_closed"
_ASYNC_CHAT_TIMEOUT_SECONDS = 9.0
# Hard cap for a single background turn. If exceeded (e.g. a hung LLM call), the
# TimeoutError flows into the existing error handling: the turn is audited and
# the conversation is finalized as ERROR instead of staying RUNNING forever.
_TURN_HARD_CAP_SECONDS = 120.0
# Backstop: a conversation left in RUNNING longer than this (e.g. after a pod
# restart killed the in-memory task) is auto-recovered on the next load.
_RUNNING_WATCHDOG_SECONDS = 150.0
_END_CONVERSATION_CALLBACK_TIMEOUT_SECONDS = 5.0
_BACK_DATA_NOTIFIED_KEY = "back_data_notified"
_BACK_DATA_CONSULTAR_STEP = "1.4.1.0"
_BACK_DATA_CENTRALES_STEP = "1.4.1.2"
_BACK_DATA_NOTIFICACION_STEP = "1.4.1.3"
_BACK_DATA_NOTIFICACION_PRODUCTO_STEP = "1.4.1.3.1"
_TRX_DATA_NOTIFIED_KEY = "trx_data_notified"
_TRX_PRODUCTS_GATE_STEP = "2.4.0.1.4"
_TRX_PRODUCT_SELECTOR_STEP = "2.4.0.1.5"
_TRX_PRODUCTS_EXIT_STEP = "2.4.0.1.4.exit"
# Fail-closed: el ".exit" AFIRMA que el cliente no tiene productos, y eso solo
# vale si el servicio respondio. Si no respondio, se usa ".error".
_TRX_PRODUCTS_ERROR_STEP = "2.4.0.1.4.error"
_TRX_ASO_GATE_STEP = "2.4.0.1.8"
_TRX_MOVEMENTS_STEP = "2.4.0.1.9"
_TRX_MOVEMENTS_NAV_STEP = "2.4.0.1.9.nav"
# Tamano de pagina del selector de movimientos; el servicio pagina y el
# agente pinta lo que llega. Coincide con las 5 casillas del YAML 2.4.0.1.9.
_TRX_MOVS_POR_PAGINA = 5
_TRX_MOVEMENTS_RETURN_STEP = "2.4.0.1.8.return"
# Idem: ".return" afirma que no hay compras ese dia; ".error", que no pudimos
# consultarlas. Confundirlos es darle al cliente un dato falso sobre su tarjeta.
_TRX_MOVEMENTS_ERROR_STEP = "2.4.0.1.8.error"
_TRX_DATE_EXIT_STEP = "2.4.0.1.7.exit"
_TRX_DETALLE_GATE_STEP = "2.4.0.1.10"
_TRX_CONFIRM_STEP = "2.4.0.1.11"
_TRX_DETALLE_PQR_STEP = "2.4.0.1.10.pqr"
_TRX_PENDIENTE_GATE_STEP = "2.4.0.1.12"
_TRX_PENDIENTE_EXIT_STEP = "2.4.0.1.12.exit"
_TRX_INVESTIGAR_STEP = "2.4.0.1.13"
_TRX_BLOQUEO_TEMP_NOTIF_GATE = "2.4.0.1.16.1"
_TRX_BLOQUEO_TEMP_NOTIF_DENIED = "2.4.0.1.16.1.denied"
_TRX_BLOQUEO_TEMP_GATE = "2.4.0.1.16.2"
_TRX_BLOQUEO_TEMP_OK = "2.4.0.1.16.3"
_TRX_BLOQUEO_TEMP_PQR = "2.4.0.1.16.2.pqr"
_TRX_BLOQUEO_PERM_NOTIF_GATE = "2.4.0.1.17.1"
_TRX_BLOQUEO_PERM_NOTIF_DENIED = "2.4.0.1.17.1.denied"
_TRX_BLOQUEO_PERM_GATE = "2.4.0.1.17.2"
_TRX_BLOQUEO_ASK_STEP = "2.4.0.1.15"
_TRX_REVISION_STEP = "2.4.0.1.18"
# Productos ya bloqueados en ESTA conversacion. Sobrevive al reseteo por
# transaccion a proposito (ver _trx_reset_per_tx_state).
_TRX_BLOQUEADOS_KEY = "trx_productos_bloqueados"
_TRX_BLOQUEO_PERM_OK = "2.4.0.1.17.3"
_TRX_BLOQUEO_PERM_PQR = "2.4.0.1.17.2.pqr"
_TRX_VALIDACIONES_GATE = "2.4.0.1.19"
_TRX_VAL_PRESENCIAL = "2.4.0.1.19.1"
_TRX_VAL_REVERSADO = "2.4.0.1.19.2"
_TRX_VAL_PQR = "2.4.0.1.19.pqr"
_TRX_DEVOLUCION_STEP = "2.4.0.1.20"
_TRX_LOOP_CLOSE_GATE = "2.4.0.1.20.0"
_TRX_LOOP_STEP = "2.4.0.1.20.1"
_TRX_LOOP_DONE_STEP = "2.4.0.1.20.2"
_TRX_CONFIRM_DATA_STEP = "2.4.0.1.3"
# =============================================================================
# PORTON DE DESPLIEGUE TXNR (piloto en produccion)
# =============================================================================
# TRX_FLOW_ENABLED=false (default): los 4 sucesos del menu 2.4.0 terminan en el
# formulario PQR, como antes de la Fase 2. Un probador escribe TRX_CANARY_TOKEN en
# el chat y habilita el flujo completo SOLO para esa conversacion. Para salir a
# produccion: TRX_FLOW_ENABLED=true (sin tocar codigo).
# El flujo ejecuta acciones IRREVERSIBLES (apagar/cancelar tarjeta), por eso el
# porton cubre la entrada (op4) Y cualquier paso 2.4.0.1* (conversaciones
# restauradas del store, saltos inesperados y los pasos .error nuevos).
_TRX_CANARY_KEY = "trx_canary"
_TRX_GATED_KEY = "trx_gated"
_TRX_GATED_PQR_STEP = "2.4.0.4.pqr"
_TRX_FLOW_PREFIX = "2.4.0.1"
_TRX_CANARY_ACK_MESSAGE = "Listo, continuemos. Cuentame en que te puedo ayudar."


def _trx_flow_enabled() -> bool:
    """True cuando el flujo TXNR esta abierto a todos los clientes (kill switch)."""

    raw = (_env_const("TRX_FLOW_ENABLED") or "false").strip().casefold()
    return raw in {"1", "true", "yes", "on"}


def _llm_closure_enabled() -> bool:
    """Whether the closing message of guide flows may be written by the LLM.

    OFF por defecto (decision de negocio 2026-08-21): el cliente solo debe ver
    mensajes aprobados, no texto redactado por el modelo. Con el cierre por LLM
    encendido se observo que el modelo imitaba el estilo del cliente (respondio
    en dialecto paisa cuando el cliente lo pidio), porque recibe la conversacion
    completa como contexto.

    Apagado, se conserva el `default_message` deterministico que ya se venia
    calculando desde el YAML del flujo, asi que no hay hueco: el mensaje existe,
    solo deja de reescribirse.

    Se puede reactivar sin desplegar imagen: LLM_CLOSURE_ENABLED=true en el
    configmap.
    """

    raw = (_trx_env("LLM_CLOSURE_ENABLED", "false")).strip().casefold()
    return raw in {"1", "true", "yes", "on"}


def _trx_canary_token() -> str:
    """Token de piloto configurado (vacio = no hay habilitacion por token)."""

    return (_env_const("TRX_CANARY_TOKEN") or "").strip()


def _is_trx_canary_token(user_content: str) -> bool:
    """Whether the message IS exactly the pilot token.

    Comparacion en tiempo constante. Nunca se registra el valor en logs ni se
    envia al LLM.
    """

    token = _trx_canary_token()
    if not token:
        return False
    candidate = (user_content or "").strip()
    if not candidate or len(candidate) != len(token):
        return False
    import hmac

    return hmac.compare_digest(candidate, token)


def _trx_flow_allowed(conversation: Conversation) -> bool:
    """Permiso para recorrer el flujo real: kill switch global o token en la conversacion."""

    if _trx_flow_enabled():
        return True
    return str(conversation.captured_data.get(_TRX_CANARY_KEY) or "").strip().casefold() == "true"
_TRX_USER_LIST_KEY = "user_trx_list"
_TRX_WAITING_MORE_KEY = "trx_waiting_another"
_TRX_REDIRECT_PQR_STEP = "2.4.0.pqr_recurrencia"
# Back-data control-table polling budget. Defaults raised so the poll window
# (attempts * interval) covers the REAL back_data latency (Postgres embargo
# enrichment + ASO token + ASO overview ~= 4s) instead of the old ~3s that
# timed out. Both are overridable from the configmap via the env vars
# BACK_DATA_POLL_INTERVAL_SECONDS and BACK_DATA_MAX_POLL_ATTEMPTS.
# Keep attempts*interval BELOW _ASYNC_CHAT_TIMEOUT_SECONDS (9.0s) or the whole
# async turn will time out. Default = 24 * 0.25s = 6.0s window.
_BACK_DATA_POLL_INTERVAL_SECONDS = 0.25
_BACK_DATA_MAX_POLL_ATTEMPTS = 24


def _env_const(name: str) -> str | None:
    """Read a value from the merged .env constants (the configmap mounts .env as
    a file, so os.getenv alone would NOT see it), falling back to real env vars.
    """
    try:
        value = load_env_constants().get(name)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        value = os.getenv(name)
    return value


def _back_data_poll_interval_seconds() -> float:
    """Poll interval (seconds) between control-table reads; env-overridable."""
    raw = _env_const("BACK_DATA_POLL_INTERVAL_SECONDS")
    try:
        value = float(str(raw).strip()) if raw not in (None, "") else _BACK_DATA_POLL_INTERVAL_SECONDS
    except (TypeError, ValueError):
        value = _BACK_DATA_POLL_INTERVAL_SECONDS
    return value if value > 0 else _BACK_DATA_POLL_INTERVAL_SECONDS


def _back_data_max_poll_attempts() -> int:
    """Max control-table poll attempts before timeout; env-overridable."""
    raw = _env_const("BACK_DATA_MAX_POLL_ATTEMPTS")
    try:
        value = int(str(raw).strip()) if raw not in (None, "") else _BACK_DATA_MAX_POLL_ATTEMPTS
    except (TypeError, ValueError):
        value = _BACK_DATA_MAX_POLL_ATTEMPTS
    return value if value > 0 else _BACK_DATA_MAX_POLL_ATTEMPTS


def _local_contingency_enabled() -> bool:
    """Return True when local contingency mode is explicitly enabled."""

    raw = _env_const("LOCAL_CONTINGENCY_MODE")
    return str(raw or "").strip().casefold() in {"1", "true", "yes", "on"}


def _resolve_selected_trx_product_id(conversation: Conversation) -> str:
    """Map the selected `producto_N` option to the real trx product id."""

    raw = conversation.captured_data.get("trx_products_result")
    selected = conversation.flow_answers.get("producto_trx_no_reconocida")
    if not raw or not selected:
        return ""

    try:
        payload = json.loads(raw)
        products = (payload.get("data") or {}).get("products") or []
        index = int(str(selected).split("_")[-1]) - 1
        entry = products[index]
        return str(
            entry.get("product_id")
            or entry.get("key_id")
            or (entry.get("card_id") or entry.get("contract_id"))
            or ""
        ).strip()
    except Exception:
        logger.warning(
            (
                "Could not resolve selected trx product "
                "conversation_id=%s selected=%s"
            ),
            conversation.conversation_id,
            selected,
        )
        return ""


def _resolve_selected_trx_franchise(conversation: Conversation) -> str:
    """Resolve the card franchise (VISA/MASTER) of the selected trx product.

    Defaults to VISA when the product source does not expose the franchise.
    """

    raw = conversation.captured_data.get("trx_products_result")
    selected = conversation.flow_answers.get("producto_trx_no_reconocida")
    if raw and selected:
        try:
            payload = json.loads(raw)
            products = (payload.get("data") or {}).get("products") or []
            index = int(str(selected).split("_")[-1]) - 1
            entry = products[index]
            franchise = str(
                entry.get("card_franchise") or entry.get("franchise") or ""
            ).strip().upper()
            if franchise:
                return franchise
        except Exception:
            pass
    return "VISA"


def _products_from_back_data_payload(payload: dict[str, object]) -> list[dict[str, str]]:
    """Normalize back_data validaciones into a trx products list."""

    validaciones = ((payload.get("hallazgos") or {}).get("validaciones") or [])
    products: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in validaciones:
        if not isinstance(entry, dict):
            continue
        product_id = str(
            entry.get("key_id") or entry.get("product_id") or (entry.get("card_id") or entry.get("contract_id")) or ""
        ).strip()
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        products.append(
            {
                "product_id": product_id,
                "key_id": str(entry.get("key_id") or product_id).strip(),
                "contract_id": str((entry.get("card_id") or entry.get("contract_id")) or "").strip(),
                "commercial_product_desc": str(
                    entry.get("commercial_product_desc")
                    or entry.get("product_desc")
                    or "Producto financiero"
                ).strip()
                or "Producto financiero",
                "product_desc": str(entry.get("product_desc") or "").strip(),
                "account_status_type_desc": "ACTIVO",
                "last_four_pan_id": "",
            }
        )
    return products


@log_execution
async def _prefetch_trx_data_if_needed(
    conversation: Conversation,
    trx_service_url: str | None,
    back_data_service_url: str | None,
    control_store: ControlTableStore | None,
) -> None:
    """Prefetch/auto-route de los nodos ACTION del flujo TXNR (arbol Fase 2).

    Corre despues de que ``generate_response`` avanza ``current_step`` al nodo
    gate y ANTES de renderizar: consulta back_trx (ASO/Postgres) y reescribe
    ``current_step`` al branch/exit segun el resultado, de modo que el usuario
    nunca ve el nodo gate intermedio.
    """

    # Otros workflows con logica propia (ver application/chat/workflows/) se
    # despachan aqui, sin agregar mas ifs a este archivo.
    hook = get_prefetch_hook(conversation.workflow)
    if hook is not None:
        await hook(conversation, control_store=control_store)
        return

    if (conversation.workflow or "") != "trx_no_reconocida":
        return

    step = conversation.current_step

    # --- PORTON DE DESPLIEGUE: si el flujo no esta abierto y la conversacion no
    # tiene el token de piloto, NINGUN paso del flujo real se ejecuta (ni la
    # validacion silenciosa de recurrencia, ni ASOs, ni bloqueos). Se atiende como
    # antes de la Fase 2: formulario PQR. Va ANTES de cualquier gate a proposito.
    if step.startswith(_TRX_FLOW_PREFIX) and not _trx_flow_allowed(conversation):
        logger.info(
            "TXNR cerrado (TRX_FLOW_ENABLED=false y sin token): %s -> %s conversation_id=%s",
            step, _TRX_GATED_PQR_STEP, conversation.conversation_id,
        )
        conversation.current_step = _TRX_GATED_PQR_STEP
        conversation.captured_data[_TRX_GATED_KEY] = "true"
        return

    user_id = _trx_customer_id(conversation)

    # ---- 2.4.0.1: recurrencia salesforce + recurrencia-bot + hito entered_op4 ----
    if step == "2.4.0.1":
        marker = step
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            return
        conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker

        has_recurrence = False
        if trx_service_url:
            recurrence_response = await validar_recurrencia(base_url=trx_service_url, customer_id=user_id)
            if recurrence_response:
                has_recurrence = bool(recurrence_response.get("has_recurrence"))
                conversation.captured_data["trx_salesforce_status"] = (
                    "REDIRECT_PQR" if has_recurrence else "OK"
                )
                conversation.captured_data["trx_salesforce_detail"] = str(
                    recurrence_response.get("detail") or ""
                ).strip()
                conversation.captured_data["trx_salesforce_result"] = json.dumps(
                    recurrence_response, ensure_ascii=False
                )
            else:
                # Sin respuesta de back_trx NO se asume "sin recurrencia" con mocks.
                conversation.captured_data["trx_salesforce_status"] = "UNAVAILABLE"
                logger.error(
                    "Recurrencia TXNR no disponible (back_trx sin respuesta) conversation_id=%s",
                    conversation.conversation_id,
                )
        else:
            conversation.captured_data["trx_salesforce_status"] = "UNAVAILABLE"
            logger.error(
                "TRX_SERVICE_URL no configurado: no se puede validar recurrencia conversation_id=%s",
                conversation.conversation_id,
            )

        # Recurrencia-bot: mismo cliente ya paso por el flujo dentro de la
        # ventana. Se evalua ANTES de registrar el hito de esta visita: el
        # contador cuenta entradas en la ventana, y registrar primero hacia
        # que cada cliente disparara su propia recurrencia en la primera
        # entrada (count=1 >= MAX_TRX_BOT_RECURRENCE=1) y NADIE pasara de
        # la opcion 4.
        if not has_recurrence and await _trx_bot_recurrence_hit(conversation):
            has_recurrence = True
            conversation.captured_data["trx_salesforce_status"] = "REDIRECT_PQR"
            conversation.captured_data["trx_recurrence_source"] = "bot"

        # El hito de ESTA visita se registra SIEMPRE tras decidir, no solo en
        # modo contingencia. Registrarlo antes hacia que el contador contara
        # la entrada que acababa de escribir -- count=1 >= MAX(1) -- y todo
        # cliente se desviara a PQR en su PRIMERA entrada, sin que nadie
        # pasara de la opcion 4. Con la bandera sin definir, que es el caso
        # en local y en OKD, ese era el comportamiento por defecto.
        await _trx_record_milestone_async(
            conversation,
            "entered_op4",
            outcome="redirect_pqr" if has_recurrence else "continue",
        )

        if has_recurrence:
            conversation.current_step = _TRX_REDIRECT_PQR_STEP
            _trx_trace_step(
                conversation, "op4_recurrencia", outcome="redirect_pqr",
                source=conversation.captured_data.get("trx_recurrence_source") or "salesforce",
            )
        else:
            # Validacion silenciosa: la rama sin recurrencia salta directo a
            # la cantidad, igual que los gates .4 y .12 reescriben su paso.
            # Antes se quedaba en .1 y el cliente veia "Estoy validando tu
            # caso..." con un boton Continuar que no aportaba nada: la
            # validacion (Salesforce, bot, hito) ya habia ocurrido en este
            # mismo turno.
            conversation.current_step = "2.4.0.1.1"
            _trx_trace_step(conversation, "op4_recurrencia", outcome="continue")
        return

    # ---- 2.4.0.1.4: productos activos (gate) -> selector o exit ----
    if step == _TRX_PRODUCTS_GATE_STEP:
        marker = step
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            return
        conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker
        await _trx_fetch_products(
            conversation, trx_service_url, back_data_service_url, control_store, user_id
        )
        # La direccion se captura AQUI y no dentro del fetcher: aquel tiene
        # cuatro ramas y la captura vivia solo en la de contingencia, que esta
        # muerta porque la bandera no se define en ningun entorno. Resultado: el
        # mensaje de reexpedicion prometia "te la enviaremos a la direccion
        # registrada en nuestros sistemas" -el texto de respaldo- aunque ADA
        # trajera la direccion real. Puesto aqui cubre las cuatro ramas.
        _trx_capturar_direccion(conversation)
        products = _trx_products_list(conversation)
        # Los ultimos 4 que ve el cliente tienen que ser los del PAN de
        # financial-overview, no los de ADA ni los del contrato: son
        # identificadores distintos y en cartera real pueden divergir (en el
        # simulador coinciden por diseno de los fixtures). Se resuelve el PAN
        # AQUI -- antes de pintar el selector -- para que la lista, la
        # confirmacion y lo que se entrega al tramo siguiente muestren todos
        # el mismo dato. El last_four de ADA queda solo como llave de cruce
        # contra financial-overview, que es su funcion legitima.
        if trx_service_url and products:
            await _trx_resolver_pan_de_productos(
                conversation, trx_service_url, user_id, products
            )
        # Fail-closed (peticion de Fabian 20/08): antes que un dato erroneo,
        # un error visible. "No tienes productos activos" es una AFIRMACION
        # sobre el cliente y solo es legitima si el servicio contesto. Si no
        # contesto, decirla es mentir: el cliente puede concluir que no tiene
        # productos cuando lo unico cierto es que no pudimos preguntar.
        estado = str(conversation.captured_data.get("trx_products_status") or "")
        # "unavailable" = el agente no pudo hablar con back_trx.
        # "error"       = back_trx contesto pero LO DE DETRAS fallo (Postgres,
        #                 ASO): responde 200 con status=error. Antes ese caso
        #                 se colaba como "no tiene productos" -- la afirmacion
        #                 falsa que este gate existe para impedir.
        indisponible = estado in ("unavailable", "error")
        # Los ultimos 4 tienen que salir del PAN de financial-overview. Solo se
        # corta si FO NO CONTESTO ("fo_error"): ahi no sabemos si los digitos de
        # ADA son los correctos. Si FO contesto y no conoce el contrato
        # ("ada_fallback"), el dato de ADA es lo mejor que hay y negar el
        # servicio seria peor que darlo -- se traza y se sigue.
        sin_fo = bool(products) and all(
            str(x.get("last_four_origen") or "") == "fo_error" for x in products
        )
        degradados = [
            x for x in products
            if str(x.get("last_four_origen") or "") == "ada_fallback"
        ]
        if degradados and not sin_fo:
            logger.warning(
                "TRX %d producto(s) sin resolver en financial-overview "
                "conversation_id=%s (se muestran los ultimos 4 de ADA)",
                len(degradados), conversation.conversation_id,
            )
        if indisponible or sin_fo:
            conversation.current_step = _TRX_PRODUCTS_ERROR_STEP
            _trx_trace_step(
                conversation, "productos", outcome="error_servicio",
                error_type="products_unavailable" if indisponible else "fo_sin_resolver",
                count=len(products), next_step=conversation.current_step,
            )
            logger.warning(
                "TRX productos no consultables conversation_id=%s motivo=%s "
                "(fail-closed: se deriva a PQR en vez de afirmar que no tiene productos)",
                conversation.conversation_id,
                "unavailable" if indisponible else "fo_sin_resolver",
            )
            return
        conversation.current_step = (
            _TRX_PRODUCT_SELECTOR_STEP if products else _TRX_PRODUCTS_EXIT_STEP
        )
        _trx_trace_step(
            conversation, "productos", outcome="hay" if products else "none",
            count=len(products), next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.8: vigencia + ASOs (financial-overview + transactions) ----
    if step == _TRX_ASO_GATE_STEP:
        product = _resolve_selected_trx_product(conversation)
        fecha = str(
            conversation.flow_answers.get("trx_fecha")
            or conversation.captured_data.get("trx_fecha")
            or ""
        ).strip()
        card_brand = _trx_card_brand(product)
        # El dia va en el marcador: una conversacion retomada MANANA debe
        # reconsultar, no leer la foto de ayer -- una compra que paso de
        # pendiente a confirmada por la noche era irreportable, y una fecha
        # que cruzo el plazo de vigencia devolvia "no hay compras" en vez
        # del aviso de plazo.
        hoy = datetime.now(UTC).strftime("%Y%m%d")
        marker = f"{step}:{_trx_last_four(product)}:{fecha}:{hoy}"
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            # Ya se consulto esta combinacion producto+fecha. No se repite la
            # llamada, pero tampoco se puede dejar la conversacion parada en
            # el nodo gate: al volver por un reenganche con la MISMA fecha, el
            # cliente se quedaba viendo "Estoy consultando tus movimientos..."
            # con un boton Continuar y sin salida. Se reencamina al destino
            # que ya determino la consulta anterior.
            previos = _trx_movimientos_list(conversation)
            conversation.current_step = (
                _TRX_MOVEMENTS_STEP if previos else _TRX_MOVEMENTS_RETURN_STEP
            )
            _trx_trace_step(
                conversation, "movimientos", outcome="reenganche_cacheado",
                count=len(previos), next_step=conversation.current_step,
            )
            return
        conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker

        # Fecha ilegible: repreguntar, no consultar. La vigencia con fecha
        # imparseable devuelve "no vencida" (fail-open) y sin este corte el
        # gate consultaba igual: el simulador ignoraba la fecha cruda y el
        # cliente veia movimientos de un dia que no indico (hallazgo H-01).
        if not _trx_parse_date(fecha):
            conversation.flow_answers.pop("trx_fecha", None)
            conversation.captured_data.pop("trx_fecha", None)
            conversation.captured_data.pop(_TRX_DATA_NOTIFIED_KEY, None)
            conversation.current_step = "2.4.0.1.7"
            if _trx_fecha_futura(fecha):
                aviso = (
                    "Esa fecha todavia no ha ocurrido. Indicame la fecha en la "
                    "que ya se realizo la compra, en formato DD/MM/AAAA."
                )
            else:
                aviso = (
                    "No pude leer esa fecha. Escribela en formato DD/MM/AAAA, "
                    "por ejemplo 06/08/2026. Consulta la fecha en tu extracto o "
                    "en los movimientos de tu App BBVA."
                )
            conversation.captured_data["dynamic_prompt_2.4.0.1.7"] = aviso
            _trx_trace_step(
                conversation, "vigencia", outcome="fecha_ilegible", fecha=fecha,
            )
            return

        # La fecha ya es parseable: si quedo el aviso de fecha ilegible de un
        # intento anterior, se retira -- si no, reaparecia en cada re-pregunta
        # de fecha (reenganches, bucle multi-tx) como si el cliente hubiera
        # vuelto a fallar (H-07).
        conversation.captured_data.pop("dynamic_prompt_2.4.0.1.7", None)

        if _trx_vigencia_vencida(fecha, card_brand):
            conversation.captured_data["trx_vigencia"] = "vencida"
            conversation.current_step = _TRX_DATE_EXIT_STEP
            _trx_trace_step(
                conversation, "vigencia", outcome="vencida", fecha=fecha, card_brand=card_brand,
            )
            return
        conversation.captured_data["trx_vigencia"] = "vigente"

        movimientos: list = []
        # None = el servicio no contesto; [] = contesto y no hay compras. Antes
        # se colapsaban en lo mismo y el cliente leia "No encontramos compras
        # registradas en la fecha", que es falso cuando el ASO esta caido.
        fallo_aso = False
        # Sin servicio (local, tests) no hay consulta: `movs` tiene que existir
        # igual porque mas abajo se guarda la pagina (H-17).
        movs = None
        total_dia = 0
        if trx_service_url:
            # El PAN ya se resolvio al listar los productos (gate .4). Se
            # reutiliza en vez de volver a preguntar a financial-overview:
            # una llamada menos y, sobre todo, el mismo PAN que el cliente
            # vio en el selector. Solo se consulta si falta.
            card_id = str((product or {}).get("card_id") or "").strip()
            if not card_id:
                card = await obtener_card_id(
                    base_url=trx_service_url,
                    customer_id=user_id,
                    contract_id=str(((product or {}).get("card_id") or (product or {}).get("contract_id")) or "").strip(),
                    last_four=_trx_last_four(product),
                )
                card_id = str((card or {}).get("card_id") or "").strip()
            conversation.captured_data["trx_card_id"] = card_id
            if not card_id:
                # Sin PAN no hay forma de consultar: es un fallo de servicio,
                # no una tarjeta sin movimientos.
                fallo_aso = True
            if card_id:
                movs = await movimientos_pagina(
                    base_url=trx_service_url, card_id=card_id, fecha=fecha,
                    page=1, page_size=_TRX_MOVS_POR_PAGINA,
                )
                fallo_aso = movs is None or str((movs or {}).get("status")) == "error"
                movimientos = (movs or {}).get("movimientos") or []
                total_dia = int((movs or {}).get("total") or 0)
                # El servicio informa si el dia tenia movimientos que el
                # filtro de importe dejo fuera: se le dice al cliente en vez
                # de darle el mismo "no hay compras" que a quien no tiene
                # ninguna (H-14).
                if not movimientos and (movs or {}).get("fuera_de_rango"):
                    conversation.captured_data["dynamic_prompt_2.4.0.1.8.return"] = (
                        "Ese día sí tienes movimientos, pero por este canal solo "
                        "puedo gestionar compras entre "
                        f"{_trx_pesos((movs or {}).get('monto_min'))} y "
                        f"{_trx_pesos((movs or {}).get('monto_max'))}. "
                        "Si la compra que no reconoces está fuera de ese rango, "
                        "nuestro equipo especializado puede ayudarte."
                    )
        if fallo_aso:
            # Un fallo tecnico NO se memoriza. El marcador de idempotencia
            # existe para no repetir una consulta que ya respondio; si la
            # consulta FALLO, repetirla es justo lo que se quiere (el servicio
            # puede haber vuelto). Antes el marcador quedaba puesto y la lista
            # vacia persistida, y un reenganche con la misma fecha caia por la
            # re-ruta en .8.return: "No encontramos compras registradas" --
            # una afirmacion falsa nacida de un error tecnico de ayer.
            conversation.captured_data.pop(_TRX_DATA_NOTIFIED_KEY, None)
            conversation.captured_data.pop("trx_movimientos_result", None)
            conversation.current_step = _TRX_MOVEMENTS_ERROR_STEP
            _trx_trace_step(
                conversation, "movimientos", outcome="error_servicio",
                error_type="aso_sin_respuesta", card_last4=_trx_last_four(product),
                fecha=fecha, next_step=conversation.current_step,
            )
            logger.warning(
                "TRX movimientos no consultables conversation_id=%s fecha=%s "
                "(fail-closed: se deriva a PQR en vez de afirmar que no hay compras)",
                conversation.conversation_id, fecha,
            )
            return
        conversation.captured_data["trx_movimientos_result"] = json.dumps(
            {"movimientos": movimientos}, ensure_ascii=False
        )
        # Pagina 1 recien traida (otra fecha u otro producto): el servicio ya
        # rebano; se guarda la pagina + metadata y se limpia una respuesta de
        # navegacion rancia. El dia TIENE movimientos si total>0 (no basta con
        # que la pagina venga con items).
        _trx_store_movimientos_pagina(conversation, movs or {})
        for _rancio in ("mas_movimientos", "anterior_movimientos"):
            if conversation.flow_answers.get("trx_movimiento_seleccionado") == _rancio:
                conversation.flow_answers.pop("trx_movimiento_seleccionado", None)
        conversation.current_step = (
            _TRX_MOVEMENTS_STEP if total_dia else _TRX_MOVEMENTS_RETURN_STEP
        )
        _trx_trace_step(
            conversation, "movimientos", outcome="hay" if movimientos else "sin_movimientos",
            count=len(movimientos), card_last4=_trx_last_four(product), fecha=fecha,
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.9.nav: navegacion de paginas (pide la pagina al servicio) ----
    if step == _TRX_MOVEMENTS_NAV_STEP:
        # El boton pulsado (mas_/anterior_) llega en la respuesta; se consume
        # para que un re-render del turno no vuelva a navegar.
        direction = conversation.flow_answers.get("trx_movimiento_seleccionado")
        conversation.flow_answers.pop("trx_movimiento_seleccionado", None)
        try:
            actual = int(conversation.captured_data.get("trx_movs_pagina") or 1)
        except (TypeError, ValueError):
            actual = 1
        try:
            total_pages = int(conversation.captured_data.get("trx_movs_total_pages") or 1)
        except (TypeError, ValueError):
            total_pages = 1
        destino = actual + 1 if direction == "mas_movimientos" else actual - 1
        destino = max(1, min(destino, total_pages))
        product = _resolve_selected_trx_product(conversation)
        fecha = str(
            conversation.flow_answers.get("trx_fecha")
            or conversation.captured_data.get("trx_fecha")
            or ""
        ).strip()
        card_id = str(
            conversation.captured_data.get("trx_card_id")
            or (product or {}).get("card_id")
            or ""
        ).strip()
        movs = None
        if trx_service_url and card_id:
            movs = await movimientos_pagina(
                base_url=trx_service_url, card_id=card_id, fecha=fecha,
                page=destino, page_size=_TRX_MOVS_POR_PAGINA,
            )
        if movs is None or str((movs or {}).get("status")) == "error":
            # Fallo al navegar: se conserva la pagina actual y se vuelve al
            # selector sin afirmar nada falso (fail-closed).
            conversation.current_step = _TRX_MOVEMENTS_STEP
            _trx_trace_step(
                conversation, "movimientos", outcome="nav_error",
                next_step=conversation.current_step,
            )
            return
        _trx_store_movimientos_pagina(conversation, movs or {})
        conversation.current_step = _TRX_MOVEMENTS_STEP
        _trx_trace_step(
            conversation, "movimientos", outcome="nav", count=destino,
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.10: detalle de la operacion (operations) ----
    if step == _TRX_DETALLE_GATE_STEP:
        product = _resolve_selected_trx_product(conversation)
        fecha = str(
            conversation.flow_answers.get("trx_fecha")
            or conversation.captured_data.get("trx_fecha")
            or ""
        ).strip()
        card_id = str(conversation.captured_data.get("trx_card_id") or "").strip()
        tx_id = _resolve_selected_movimiento_id(conversation)
        marker = f"{step}:{tx_id}"
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            return
        conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker

        detalle = None
        if trx_service_url and card_id and tx_id:
            resp = await detalle_trx(
                base_url=trx_service_url,
                card_id=card_id,
                fecha=fecha,
                tx_id=tx_id,
                origin_flag=_trx_origin_flag(product),
            )
            if resp and str(resp.get("status")) == "ok":
                detalle = resp.get("detalle")
                conversation.captured_data["trx_detalle_result"] = json.dumps(
                    resp.get("detalle") or {}, ensure_ascii=False
                )
                conversation.captured_data["trx_clasificacion"] = json.dumps(
                    resp.get("clasificacion") or {}, ensure_ascii=False
                )
        conversation.current_step = _TRX_CONFIRM_STEP if detalle else _TRX_DETALLE_PQR_STEP
        _trx_trace_step(
            conversation, "detalle", outcome="ok" if detalle else "none",
            tx_id=tx_id, next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.12: pendiente-TDC (offline sobre clasificacion) ----
    if step == _TRX_PENDIENTE_GATE_STEP:
        clasif = _trx_clasificacion(conversation)
        conversation.current_step = (
            _TRX_PENDIENTE_EXIT_STEP if clasif.get("pendiente_tdc") else _TRX_INVESTIGAR_STEP
        )
        _trx_trace_step(
            conversation, "pendiente_tdc",
            outcome="pendiente" if clasif.get("pendiente_tdc") else "no_pendiente",
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.16.1 / 2.4.0.1.17.1: SUBIDA DE NIVEL (push de autorizacion) ----
    #
    # Aqui solo se ENVIA la notificacion y se guarda el reto. La autorizacion la
    # da el cliente en su App; el flujo la comprueba en el paso siguiente, cuando
    # pulsa "Continuar". El mensaje del nodo ya dice "Revisala y regresa aqui".

    logger.warning(
        "TXNR DEBUG CONTINUAR "
        "step=%r "
        "current_step=%r "
        "conversation_id=%s "
        "captured_data_keys=%s",
        step,
        conversation.current_step,
        conversation.conversation_id,
        list(conversation.captured_data.keys()),
    )

    if step in {_TRX_BLOQUEO_TEMP_NOTIF_GATE, _TRX_BLOQUEO_PERM_NOTIF_GATE}:
      
        logger.warning(
            "TXNR DEBUG ENTRE EN BLOQUE AUTORIZACION "
            "step=%r "
            "TEMP_GATE=%r "
            "PERM_GATE=%r",
            step,
            _TRX_BLOQUEO_TEMP_GATE,
            _TRX_BLOQUEO_PERM_GATE,
        )

        es_temporal = step == _TRX_BLOQUEO_TEMP_NOTIF_GATE
        denied = (
            _TRX_BLOQUEO_TEMP_NOTIF_DENIED if es_temporal else _TRX_BLOQUEO_PERM_NOTIF_DENIED
        )
        etiqueta = "temporal" if es_temporal else "permanente"
        marker = step
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            # El push ya salio en este mismo paso: no se reenvia al volver.
            return

        outcome = await _trx_enviar_push_bloqueo(
                    conversation,
                    trx_service_url,
                    back_data_service_url,
                    user_id,
                )
        if outcome == "enviado":
            conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker
        else:
            # Sin dispositivo activo o fallo del ASO: no hay forma de autorizar.
            conversation.current_step = denied
            _trx_auth_limpiar(conversation)
        _trx_trace_step(
            conversation,
            f"subida_nivel_{etiqueta}",
            outcome=outcome,
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.16.2 / 2.4.0.1.17.2: bloqueos (temporal / permanente) ----
    #
    # Antes de ejecutar se comprueba que el cliente AUTORIZO en su dispositivo.
    # Si sigue pendiente se vuelve al paso del push para que pueda reintentar sin
    # perder el reto; si se agoto la ventana de 3 minutos, se cierra por rechazo.
    if step in {_TRX_BLOQUEO_TEMP_GATE, _TRX_BLOQUEO_PERM_GATE}:
        es_temporal = step == _TRX_BLOQUEO_TEMP_GATE
        etiqueta = "temporal" if es_temporal else "permanente"
        paso_push = (
            _TRX_BLOQUEO_TEMP_NOTIF_GATE if es_temporal else _TRX_BLOQUEO_PERM_NOTIF_GATE
        )
        paso_denied = (
            _TRX_BLOQUEO_TEMP_NOTIF_DENIED if es_temporal else _TRX_BLOQUEO_PERM_NOTIF_DENIED
        )
        paso_ok = _TRX_BLOQUEO_TEMP_OK if es_temporal else _TRX_BLOQUEO_PERM_OK
        paso_pqr = _TRX_BLOQUEO_TEMP_PQR if es_temporal else _TRX_BLOQUEO_PERM_PQR

        hito = (
            f"bloqueo_ejecutado:{etiqueta}:"
            f"{conversation.conversation_id}:{_trx_clave_producto(conversation)}"
        )
        ya_hecho = await _trx_bloqueo_ya_ejecutado(conversation, hito)

        if not ya_hecho:
            autorizacion = await _trx_estado_push_bloqueo(
                conversation,
                trx_service_url,
            )

            logger.warning(
                "TXNR DEBUG AUTH FINAL "
                "challenge=%s autorizacion=%r step=%s",
                _trx_auth_state(conversation).get("challenge"),
                autorizacion,
                conversation.current_step,
            )

            if autorizacion == "pendiente":
                
                logger.info(
                    "TXNR BLOQUEO %s AUTORIZACION PENDIENTE "
                    "regresando al paso de notificacion",
                    etiqueta,
                )

                conversation.captured_data.pop(_TRX_DATA_NOTIFIED_KEY, None)
                conversation.current_step = paso_push

                _trx_trace_step(
                    conversation,
                    f"bloqueo_{etiqueta}",
                    outcome="autorizacion_pendiente",
                    next_step=conversation.current_step,
                )
                return

            if autorizacion != "aceptado":
                logger.warning(
                    "TXNR BLOQUEO %s AUTORIZACION RECHAZADA "
                    "autorizacion=%r esperado='aceptado'",
                    etiqueta,
                    autorizacion,
                )

                conversation.current_step = paso_denied
                _trx_auth_limpiar(conversation)

                _trx_trace_step(
                    conversation,
                    f"bloqueo_{etiqueta}",
                    outcome=f"autorizacion_{autorizacion}",
                    next_step=conversation.current_step,
                )
                return

            logger.info(
                "TXNR BLOQUEO %s AUTORIZACION ACEPTADA "
                "continuando con ejecucion del bloqueo",
                etiqueta,
            )

        if ya_hecho:
            # El POST ya ocurrio en un intento anterior de ESTA conversacion (el
            # turno fallo despues del bloqueo y el snapshot se revirtio). No se
            # repite: repetirlo emitia una SEGUNDA tarjeta.
            ok = True
            _trx_trace_step(conversation, f"bloqueo_{etiqueta}", outcome="ya_ejecutado")
        else:
            ok = await _trx_bloqueo(conversation, trx_service_url, user_id, etiqueta)
            if ok:
                # AWAITED antes de seguir: si el turno muere despues de aqui, el
                # candado ya es durable.
                await _trx_record_milestone_async(conversation, hito)
        if ok:
            _trx_registrar_bloqueo(conversation, etiqueta)
            _trx_auth_limpiar(conversation)
        await _trx_record_milestone_async(
            conversation, "reached_block", outcome=f"bloqueo_{etiqueta}"
        )
        conversation.current_step = paso_ok if ok else paso_pqr
        _trx_trace_step(
            conversation, f"bloqueo_{etiqueta}", outcome="ok" if ok else "error",
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.19: validaciones ECI/eCard/reverso (offline sobre clasificacion) ----
    if step == _TRX_VALIDACIONES_GATE:
        resultado = str(_trx_clasificacion(conversation).get("resultado") or "").strip().lower()
        conversation.current_step = {
            "presencial": _TRX_VAL_PRESENCIAL,
            "reversado": _TRX_VAL_REVERSADO,
            "pqr": _TRX_VAL_PQR,
        }.get(resultado, _TRX_DEVOLUCION_STEP)
        _trx_trace_step(
            conversation, "validacion", outcome=resultado or "devolucion",
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.20: devolucion automatica + registro durable (Excel F5) ----
    if step == _TRX_DEVOLUCION_STEP:
        marker = step
        if conversation.captured_data.get(_TRX_DATA_NOTIFIED_KEY) == marker:
            return
        conversation.captured_data[_TRX_DATA_NOTIFIED_KEY] = marker
        # Enriquece el trx_case_state con el payload Tantia para que el snapshot
        # durable (que consume el cronjob del CSV) contenga los datos del caso.
        # `tantia` guarda la ULTIMA transaccion (compatibilidad) y `tantia_items`
        # ACUMULA una entrada por cada transaccion que llego al abono, que es lo
        # que el CSV convierte en filas.
        _tantia_payload = _trx_build_tantia_payload(conversation)
        update_trx_state(conversation, tantia=_tantia_payload)
        _tantia_total = _trx_append_tantia_item(conversation, _tantia_payload)
        logger.info(
            "TXNR transaccion acumulada para el CSV Tantia conversation_id=%s total=%s",
            conversation.conversation_id,
            _tantia_total,
        )
        await _trx_record_milestone_async(conversation, "completed_report", outcome="devolucion")
        _trx_trace_step(conversation, "devolucion", outcome="registrada")
        # Prompt dinámico con días configurables via DIAS_HABILES_DEVOLUCION.
        try:
            dias_dev = int(_trx_env("DIAS_HABILES_DEVOLUCION", "10"))
        except (ValueError, TypeError):
            dias_dev = 10
        logger.info(
            "Building dynamic_prompt_2.4.0.1.20 conversation_id=%s dias_dev=%s "
            "dias_env=%s from_env_const=%s from_os_environ=%s",
            conversation.conversation_id,
            dias_dev,
            _trx_env("DIAS_HABILES_DEVOLUCION", "NOT_FOUND"),
            _env_const("DIAS_HABILES_DEVOLUCION"),
            os.getenv("DIAS_HABILES_DEVOLUCION"),
        )
        conversation.captured_data["dynamic_prompt_2.4.0.1.20"] = (
            "Validamos la información de tu solicitud y tu caso aplica "
            "para la devolución automática.\n\n"
            "Gestionaremos el abono de tu dinero y te enviaremos la confirmación "
            "a tu correo electrónico en un máximo de "
            f"{dias_dev} días hábiles. "
            "No necesitas realizar ningún trámite adicional."
        )
        return

    # ---- 2.4.0.1.20.0: cierre del bucle (offline) ----
    # Punto UNICO al que llegan los cuatro desenlaces. Antes solo la devolucion
    # ofrecia reportar la siguiente: quien declaraba 2 o 3 y caia en PQR,
    # presencial o reversada perdia las demas sin que nadie se lo dijera.
    if step == _TRX_LOOP_CLOSE_GATE:
        total = _trx_get_n(conversation)
        quedan = _trx_get_index(conversation) < total
        if quedan:
            conversation.current_step = _TRX_LOOP_STEP
            outcome = "siguiente_disponible"
        elif total > 1:
            conversation.current_step = _TRX_LOOP_DONE_STEP
            outcome = "cierre"
        else:
            # Quien declaro UNA sola transaccion no necesita que le digan que
            # "ya reporto todas": suena raro para una. El mensaje de cierre es
            # para quien declaro 2 o 3 (decision de Pablo, 21/08).
            conversation.current_step = "satisfaction_check"
            outcome = "cierre_directo"
        _trx_trace_step(
            conversation, "loop", outcome=outcome,
            indice=_trx_get_index(conversation), total=total,
            next_step=conversation.current_step,
        )
        return

    # ---- 2.4.0.1.20.1: bucle multi-transaccion (offline) ----
    if step == _TRX_LOOP_STEP:
        if _trx_get_index(conversation) >= _trx_get_n(conversation):
            # Ya no quedan: se lo DECIMOS en vez de saltar a satisfaccion en
            # silencio (peticion de Fabian 20/08), pero solo si declaro mas de
            # una transaccion.
            if _trx_get_n(conversation) > 1:
                conversation.current_step = _TRX_LOOP_DONE_STEP
                _trx_trace_step(conversation, "loop", outcome="cierre")
            else:
                conversation.current_step = "satisfaction_check"
                _trx_trace_step(conversation, "loop", outcome="cierre_directo")
        else:
            _trx_trace_step(conversation, "loop", outcome="siguiente_disponible")
        return

    # ---- 2.4.0.1.15: no volver a pedir el bloqueo del MISMO producto ----
    # Si el cliente ya bloqueo esta tarjeta en una transaccion anterior de la
    # misma conversacion, preguntarselo otra vez no tiene sentido: la tarjeta ya
    # esta bloqueada. Se salta a la revision (peticion de Fabian 20/08).
    if step == _TRX_BLOQUEO_ASK_STEP:
        clave = _trx_clave_producto(conversation)
        ya = _trx_producto_bloqueado(conversation, clave)
        if ya:
            ultimos = _trx_last_four(_resolve_selected_trx_product(conversation))
            conversation.captured_data["dynamic_prompt_2.4.0.1.18"] = (
                f"Tu tarjeta terminada en \u2022{ultimos} ya qued\u00f3 "
                f"bloqueada en el reporte anterior, as\u00ed que seguimos con la revisi\u00f3n "
                f"de esta transacci\u00f3n."
                if ultimos else
                "Tu producto ya qued\u00f3 bloqueado en el reporte anterior, as\u00ed que "
                "seguimos con la revisi\u00f3n de esta transacci\u00f3n."
            )
            conversation.current_step = _TRX_REVISION_STEP
            _trx_trace_step(
                conversation, "bloqueo_ya_hecho", outcome=str(ya),
                producto=clave[-4:] if clave else "", next_step=conversation.current_step,
            )
            return
        return


# ---------------------------------------------------------------------------
# Helpers TXNR Fase 2 (usados por prefetch / handler / loaders)
# ---------------------------------------------------------------------------
def _trx_customer_id(conversation: Conversation) -> str:
    return conversation.user_id or _extract_customer_id(conversation.conversation_id)


async def _load_trx_customer_address_if_needed(
    conversation: Conversation,
    trx_service_url: str | None,
) -> None:
    """Load address only for the permanent TXNR block message."""

    if conversation.current_step != "2.4.0.1.17.3":
        return

    if not trx_service_url:
        return

    customer_id = _trx_customer_id(conversation)

    if not customer_id:
        return

    address = await fetch_trx_customer_address(
        base_url=trx_service_url,
        customer_id=customer_id,
    )

    if address:
        conversation.captured_data["trx_customer_address"] = address

        logger.info(
            "TXNR customer address loaded conversation_id=%s customer_id=%s",
            conversation.conversation_id,
            customer_id,
        )


def _trx_trace_turn_transition(
    conversation: Conversation, *, step_before: str | None
) -> None:
    """Una linea de journey por turno del flujo trx: de donde a donde.

    Complementa las trazas de gate: con esto, cualquier caso se puede
    reconstruir desde logs paso a paso (peticion de Fabian 13/08). El
    valor respondido va enmascarado: nunca texto libre ni identificadores
    completos.
    """

    if not str(conversation.workflow or "").startswith("trx"):
        return
    despues = conversation.current_step
    if step_before == despues:
        return
    ultima = ""
    if conversation.flow_answers:
        clave = list(conversation.flow_answers)[-1]
        crudo = str(conversation.flow_answers[clave])
        # enmascarado: keys de opcion (cortas, controladas) pasan; lo demas
        # se reduce a longitud para no volcar texto libre del cliente
        ultima = f"{clave}={crudo if len(crudo) <= 32 else f'<{len(crudo)} chars>'}"
    # Ademas del evento (error_handler -> MinIO, que en local no corre),
    # una linea INFO en el propio log del agente: "track with logs every
    # step" tiene que funcionar tambien con docker logs a secas.
    logger.info(
        "TXNR paso %s -> %s [%s] %s conversation_id=%s",
        step_before,
        despues,
        conversation.status.value,
        ultima or "-",
        conversation.conversation_id,
    )
    _trx_trace_step(
        conversation,
        "paso",
        outcome="transicion",
        desde=step_before,
        hasta=despues,
        respuesta=ultima or None,
        status=conversation.status.value,
    )


def _trx_trace_step(
    conversation: Conversation, operation: str, outcome: str = "ok", **extra: Any
) -> None:
    """Traza un paso del flujo TXNR (journey) hacia MinIO audit-logs/clients.

    Deja registro de 'hasta donde llego el cliente' y la decision de cada gate.
    Fail-open: nunca rompe el flujo.
    """
    try:
        from infrastructure.observability.trace_audit import schedule_trace_event

        schedule_trace_event(
            event_type="flow",
            operation=operation,
            outcome=outcome,
            conversation_id=conversation.conversation_id,
            customer_id=_trx_customer_id(conversation),
            request_summary={"step": conversation.current_step},
            response_summary={k: v for k, v in extra.items() if v is not None},
            tags=["trx", "flow", operation],
        )
    except Exception:
        logger.debug("trx flow trace fallo op=%s (fail-open)", operation)


def _trx_env(name: str, default: str) -> str:
    """Lee una variable priorizando el .env montado por el configmap (_env_const),
    luego os.environ, y por ultimo el default. El agente no hace load_dotenv, por eso
    _env_const es la fuente principal."""
    val = _env_const(name)
    if val in (None, ""):
        val = os.getenv(name)
    return val if val not in (None, "") else default


def _resolve_selected_trx_product(conversation: Conversation) -> dict:
    """Producto seleccionado (dict crudo) desde trx_products_result por producto_N."""

    raw = conversation.captured_data.get("trx_products_result")
    selected = conversation.flow_answers.get("producto_trx_no_reconocida")
    if not raw or not selected:
        return {}
    try:
        payload = json.loads(raw)
        products = (payload.get("data") or {}).get("products") or []
        idx = int(str(selected).split("_")[-1]) - 1
        return products[idx] if 0 <= idx < len(products) else {}
    except Exception:
        return {}


def _trx_last_four(product: dict) -> str:
    return str(product.get("last_four_pan_id") or product.get("last_four") or "").strip()


def _trx_card_brand(product: dict) -> str:
    return str(
        product.get("card_brand") or product.get("card_franchise") or product.get("franchise") or ""
    ).strip().upper()


def _trx_origin_flag(product: dict) -> str:
    # v4 solo-FO: el array ya no lleva origin_flag -- todo lo que entra por el
    # financial-overview es tarjeta, asi que TDC es un hecho, no un defecto.
    # (La deteccion de compras pendientes llega por otro servicio ASO -- Luis.)
    return str(product.get("origin_flag") or "TDC").strip()


def _trx_fecha_futura(fecha: str) -> bool:
    """La fecha se entiende pero aun no ha ocurrido.

    Se separa de "no se entiende" porque el aviso al cliente es distinto:
    decirle que no se pudo leer 31/12/2099 seria falso y confuso.
    """

    from datetime import datetime

    crudo = (fecha or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(crudo, fmt)
        except ValueError:
            continue
        return parsed.date() > datetime.now().date()
    return False


def _trx_parse_date(fecha: str):
    """Fecha tecleada por el cliente -> datetime, o None si no se entiende.

    Tolerante al recibir y estricto al pedir: el bot siempre solicita
    DD/MM/AAAA, pero acepta el guion como separador y los dias/meses sin
    cero delante, que es como mucha gente los escribe. El dia va primero
    en todos los formatos aceptados: no hay ambiguedad posible entre
    03/04/2026 y 04/03/2026.

    Una fecha FUTURA no es interpretable como una compra ya realizada, asi
    que se rechaza: antes se aceptaba y el cliente recibia un "no
    encontramos compras" que no explicaba nada.
    """

    from datetime import datetime

    crudo = (fecha or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(crudo, fmt)
        except ValueError:
            continue
        return None if parsed.date() > datetime.now().date() else parsed
    return None


def _trx_pesos(valor) -> str:
    """Importe en el formato que ve el cliente: $35.000."""

    try:
        return "$" + f"{float(valor):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def _trx_vigencia_vencida(fecha: str, card_brand: str) -> bool:
    """True si la fecha supera el plazo de la franquicia (VISA 180 / MASTER 120 dias)."""

    from datetime import datetime

    parsed = _trx_parse_date(fecha)
    if not parsed:
        return False
    dias = (datetime.now() - parsed).days
    if "MASTER" in (card_brand or "").upper():
        limite = int(_trx_env("VIGENCIA_MASTER_DIAS", "120"))
    else:
        limite = int(_trx_env("VIGENCIA_VISA_DIAS", "180"))
    return dias > limite


def _trx_capturar_direccion(conversation: Conversation) -> None:
    """Guarda la direccion del cliente desde el payload de productos ya cargado.

    Se lee del sobre (data.customer_address) y, si no viene ahi, del primer
    producto: segun la rama que haya respondido, ADA la publica en uno u otro
    sitio.
    """

    crudo = conversation.captured_data.get("trx_products_result")
    if not crudo:
        return
    try:
        datos = (json.loads(crudo) or {}).get("data") or {}
    except Exception:
        return
    direccion = str(datos.get("customer_address") or "").strip()
    if not direccion:
        for producto in datos.get("products") or []:
            direccion = str((producto or {}).get("customer_address") or "").strip()
            if direccion:
                break
    if direccion:
        conversation.captured_data["trx_customer_address"] = direccion


def _trx_products_list(conversation: Conversation) -> list[dict]:
    raw = conversation.captured_data.get("trx_products_result")
    if not raw:
        return []
    try:
        payload = json.loads(raw)
        return (payload.get("data") or {}).get("products") or []
    except Exception:
        return []


def _trx_store_movimientos_pagina(conversation: Conversation, movs: dict) -> None:
    """Guarda la pagina devuelta por movimientos-pagina y su metadata.

    El agente ya no rebana: persiste SOLO la pagina actual en
    ``trx_movimientos_result`` (para que la seleccion por posicion 1..5 mapee
    al id del movimiento visible) y la metadata de paginacion que el selector
    pinta sin recalcular (page/total/total_pages/has_prev/has_next).
    """
    movimientos = (movs or {}).get("movimientos") or []
    conversation.captured_data["trx_movimientos_result"] = json.dumps(
        {"movimientos": movimientos}, ensure_ascii=False
    )
    conversation.captured_data["trx_movs_pagina"] = str(int((movs or {}).get("page") or 1))
    conversation.captured_data["trx_movs_total"] = str(int((movs or {}).get("total") or 0))
    conversation.captured_data["trx_movs_total_pages"] = str(int((movs or {}).get("total_pages") or 1))
    conversation.captured_data["trx_movs_has_prev"] = "1" if (movs or {}).get("has_prev") else "0"
    conversation.captured_data["trx_movs_has_next"] = "1" if (movs or {}).get("has_next") else "0"


def _trx_movimientos_list(conversation: Conversation) -> list[dict]:
    raw = conversation.captured_data.get("trx_movimientos_result")
    if not raw:
        return []
    try:
        return (json.loads(raw) or {}).get("movimientos") or []
    except Exception:
        return []


def _resolve_selected_movimiento_id(conversation: Conversation) -> str:
    """Mapea movimiento_N -> id de la transaccion en trx_movimientos_result."""

    selected = conversation.flow_answers.get("trx_movimiento_seleccionado")
    movimientos = _trx_movimientos_list(conversation)
    if not selected or not movimientos:
        return ""
    try:
        idx = int(str(selected).split("_")[-1]) - 1
        if 0 <= idx < len(movimientos):
            return str(movimientos[idx].get("id") or "").strip()
    except Exception:
        pass
    return ""


def _trx_clasificacion(conversation: Conversation) -> dict:
    raw = conversation.captured_data.get("trx_clasificacion")
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def _trx_build_tantia_payload(conversation: Conversation) -> dict:
    """Arma el payload del caso para el Excel/RPA Tantia (consumido por el cronjob F5)."""

    from datetime import datetime

    product = _resolve_selected_trx_product(conversation)
    detalle: dict = {}
    raw = conversation.captured_data.get("trx_detalle_result")
    if raw:
        try:
            detalle = json.loads(raw) or {}
        except Exception:
            detalle = {}

    mov: dict = {}
    movimientos = _trx_movimientos_list(conversation)
    sel = conversation.flow_answers.get("trx_movimiento_seleccionado")
    if sel and movimientos:
        try:
            idx = int(str(sel).split("_")[-1]) - 1
            if 0 <= idx < len(movimientos):
                mov = movimientos[idx]
        except Exception:
            mov = {}

    return {
        "fecha_recepcion": datetime.now().strftime("%Y-%m-%d"),
        "customer_id": _trx_customer_id(conversation),
        "customer_name": str(
            product.get("customer_name")
            or product.get("personal_name")
            or product.get("client_name")
            or product.get("nombre_titular")
            or ""
        ).strip(),
        "customer_mail": str(
            product.get("customer_mail")
            or product.get("email")
            or product.get("mail")
            or product.get("correo")
            or ""
        ).strip(),
        # Documento del titular (columna personal_id de ada_info_detail). El CSV
        # de Tantia lo exige sin los ceros de relleno a la izquierda.
        "personal_id": str(product.get("personal_id") or "").strip(),
        "evento": str(conversation.flow_answers.get("evento_trx_no_reconocida") or "").strip(),
        "contrato": str(
            (product.get("card_id") or product.get("contract_id"))
            or product.get("contract_number")
            or product.get("account_id")
            or ""
        ).strip(),
        "numero_tarjeta": str(conversation.captured_data.get("trx_card_id") or "").strip(),
        "tipo_producto": str(
            product.get("commercial_product_desc") or product.get("product_desc") or ""
        ).strip(),
        "origin_flag": _trx_origin_flag(product),
        "card_brand": _trx_card_brand(product),
        "last_four": _trx_last_four(product),
        "fecha_trx": str(conversation.flow_answers.get("trx_fecha") or "").strip(),
        "rango_valor": str(conversation.flow_answers.get("trx_rango_valor") or "").strip(),
        "movimiento_descripcion": str(mov.get("descripcion") or mov.get("description") or "").strip(),
        "movimiento_valor": mov.get("valor") if mov.get("valor") is not None else mov.get("amount"),
        "tx_id": _resolve_selected_movimiento_id(conversation),
        "clasificacion": _trx_clasificacion(conversation),
        "detalle": detalle,
    }


# --- Acumulacion de transacciones reportadas (CSV Tantia) --------------------
#
# El CSV de Tantia lleva UNA FILA POR TRANSACCION que llego al abono automatico:
# si el cliente reporto 3 transacciones y las 3 llegaron, salen 3 filas.
#
# Antes esto era imposible: `update_trx_state(tantia=...)` SOBREESCRIBIA el
# payload en cada vuelta del bucle y `reset_per_tx` borraba `detalle`, asi que el
# registro durable conservaba solo la ULTIMA transaccion. Por eso se acumula en
# una lista antes de que el reset limpie los datos de la transaccion.
_TANTIA_ITEMS_KEY = "tantia_items"


def _trx_item_fingerprint(payload: dict) -> str:
    """Identidad de una transaccion reportada, para no duplicar filas.

    Se usa extracto+movimiento del ASO (`statementDetail`), que es la identidad
    real de la operacion. Si el ASO no los trajo, se cae al id del movimiento
    seleccionado y, en ultimo caso, a fecha+valor.
    """

    detalle = payload.get("detalle") or {}
    statement = detalle.get("statementDetail") or {}
    statement_id = str(statement.get("statementId") or "").strip()
    movement_id = str(statement.get("movementId") or "").strip()
    if statement_id or movement_id:
        return f"{statement_id}|{movement_id}"
    tx_id = str(payload.get("tx_id") or "").strip()
    if tx_id:
        return f"tx:{tx_id}"
    return f"{payload.get('fecha_trx')}|{payload.get('movimiento_valor')}"


def _trx_append_tantia_item(conversation: Conversation, payload: dict) -> int:
    """Anade la transaccion al acumulado del caso y devuelve el total.

    Idempotente: si la misma transaccion vuelve a pasar por el paso de abono (por
    un reintento o un refresco del turno), NO se duplica la fila.
    """

    state = get_trx_state(conversation)
    items = state.get(_TANTIA_ITEMS_KEY)
    if not isinstance(items, list):
        items = []
    fingerprint = _trx_item_fingerprint(payload)
    existentes = {_trx_item_fingerprint(item) for item in items if isinstance(item, dict)}
    if fingerprint not in existentes:
        items.append(payload)
    update_trx_state(conversation, **{_TANTIA_ITEMS_KEY: items})
    return len(items)


async def _trx_resolver_pan_de_productos(
    conversation: Conversation,
    trx_service_url: str,
    user_id: str,
    products: list[dict],
) -> None:
    """Pone en cada producto el PAN de financial-overview y sus ultimos 4.

    Fail-open: si financial-overview no responde para un producto, se deja
    el dato de ADA y se marca el origen, en vez de dejar al cliente sin
    selector. El origen viaja en la traza para poder auditarlo.
    """

    resueltos = 0
    for producto in products:
        llave = str(
            producto.get("last_four") or producto.get("last_four_pan_id") or ""
        ).strip()
        if not llave:
            producto["last_four_origen"] = "sin_llave"
            continue
        respuesta = await obtener_card_id(
            base_url=trx_service_url,
            customer_id=user_id,
            contract_id=str((producto.get("card_id") or producto.get("contract_id")) or "").strip(),
            last_four=llave,
        )
        pan = str((respuesta or {}).get("card_id") or "").strip()
        if pan:
            producto["card_id"] = pan
            producto["last_four"] = pan[-4:]
            producto["last_four_origen"] = "financial_overview"
            resueltos += 1
        elif respuesta is None or str(respuesta.get("status")) == "error":
            # None: back_trx no contesto. status=error: back_trx contesto pero
            # el financial-overview de detras fallo. Ambos son fallo de
            # SERVICIO, no "el contrato no esta en FO" (eso es not_found y va
            # por la rama de abajo con el dato de ADA).
            # El servicio NO contesto. No es lo mismo que contestar "no lo
            # conozco": en un caso no sabemos nada, en el otro sabemos que no
            # esta. Solo el primero justifica cortar el flujo.
            producto["last_four_origen"] = "fo_error"
        else:
            producto["last_four_origen"] = "ada_fallback"
    _trx_guardar_products_result(conversation, products)
    _trx_trace_step(
        conversation, "pan_productos", outcome="ok" if resueltos else "fallback",
        resueltos=resueltos, total=len(products),
    )


def _trx_guardar_products_result(
    conversation: Conversation, products: list[dict]
) -> None:
    """Reescribe products_result conservando el resto del sobre."""

    crudo = conversation.captured_data.get("trx_products_result")
    try:
        sobre = json.loads(crudo) if crudo else {}
    except Exception:
        sobre = {}
    datos = sobre.get("data") if isinstance(sobre.get("data"), dict) else {}
    datos["products"] = products
    sobre["data"] = datos
    conversation.captured_data["trx_products_result"] = json.dumps(
        sobre, ensure_ascii=False
    )


async def _trx_fetch_products(
    conversation: Conversation,
    trx_service_url: str | None,
    back_data_service_url: str | None,
    control_store: ControlTableStore | None,
    user_id: str,
) -> None:
    """Carga productos activos EXCLUSIVAMENTE desde back_trx (Postgres ADA).

    NO hay fallback a back_data ni a mocks in-process: el flujo TXNR exige el filtro
    de Postgres (VIGENTE/ACTIVO + origin_flag + card_flag). back_data usa otra fuente
    (hallazgos.validaciones) que NO aplica ese filtro, y por eso mostraba productos
    ajenos o incompletos. Si back_trx no responde se marca ``unavailable`` y el flujo
    sale por su off-ramp (nunca datos inventados).

    Nota de merge (costuras): se conserva la captura de la direccion del cliente
    (``customer_address``), que el flujo usa en el copy de confirmacion.
    """

    if trx_service_url:
        products_response = await consultar_productos_activos(
            base_url=trx_service_url, customer_id=user_id
        )
        if products_response:
            status = str(products_response.get("status") or "ok")
            conversation.captured_data["trx_products_status"] = status
            conversation.captured_data["trx_products_result"] = json.dumps(
                products_response, ensure_ascii=False
            )
            direccion = str(
                (products_response.get("data") or {}).get("customer_address") or ""
            ).strip()
            if direccion:
                conversation.captured_data["trx_customer_address"] = direccion
            if status == "error":
                logger.error(
                    "back_trx reporto error de productos (sin fallback) conversation_id=%s detail=%s",
                    conversation.conversation_id,
                    (products_response.get("data") or {}).get("error"),
                )
            return

    logger.error(
        "Productos TXNR no disponibles (back_trx sin respuesta) conversation_id=%s user_id=%s",
        conversation.conversation_id,
        user_id,
    )
    conversation.captured_data["trx_products_status"] = "unavailable"
    conversation.captured_data["trx_products_result"] = json.dumps(
        {"status": "unavailable", "data": {"products": []}}, ensure_ascii=False
    )


async def _trx_bloqueo(
    conversation: Conversation, trx_service_url: str | None, user_id: str, tipo: str
) -> bool:
    """Ejecuta el bloqueo (temporal|permanente) via back_trx. Fail-safe -> False.

    En el bloqueo PERMANENTE se envian los datos del reto: ese camino ejecuta el
    tercer POST de /cards/v2/operations, que cancela la tarjeta y pide
    reexpedicion, y el back_trx lo rechaza sin autorizacion.

    En el TEMPORAL no se envian: ese camino solo hace el PATCH de apagado y nunca
    toca el endpoint de cancelacion.
    """

    card_id = str(conversation.captured_data.get("trx_card_id") or "").strip()
    if not trx_service_url or not card_id:
        return False
    autorizacion = None
    if str(tipo).strip().casefold() == "permanente":
        auth = _trx_auth_state(conversation)
        autorizacion = {
            "challenge": auth.get("challenge", ""),
            "authentication_state": auth.get("authentication_state", ""),
            "device_id": auth.get("device_id", ""),
            "profile_id": auth.get("profile_id", ""),
            "account_last_four": auth.get("account_last_four", ""),
        }
    resp = await bloqueo_trx(
        base_url=trx_service_url, card_id=card_id, tipo=tipo, autorizacion=autorizacion
    )
    return bool(resp and resp.get("ok"))


# --- Subida de nivel: autorizacion por notificacion push -------------------
#
# La ventana de negocio es de 3 MINUTOS, pero un sondeo continuo de ese tiempo no
# cabe en un turno: el agente abandona la llamada al back a los 10 s y el turno
# muere a los 120 s. Se reparte entre turnos: el push se envia una vez, el estado
# se consulta cada vez que el cliente pulsa "Continuar", y el plazo se controla
# con un deadline guardado en el estado del caso.
_TRX_AUTH_KEY = "subida_nivel"
_TRX_AUTH_VENTANA_SEGUNDOS = 180.0


def _trx_auth_state(conversation: Conversation) -> dict:
    """Datos del reto guardados para esta conversacion (nunca en memoria de proceso)."""

    datos = get_trx_state(conversation).get(_TRX_AUTH_KEY)
    return dict(datos) if isinstance(datos, dict) else {}


def _trx_auth_guardar(conversation: Conversation, datos: dict) -> None:
    """Guarda challenge/state/device/profile y abre la ventana de 3 minutos."""

    import time as _t

    update_trx_state(
        conversation,
        **{
            _TRX_AUTH_KEY: {
                "challenge": str(datos.get("challenge") or ""),
                "authentication_state": str(datos.get("authentication_state") or ""),
                "device_id": str(datos.get("device_id") or ""),
                "profile_id": str(datos.get("profile_id") or ""),
                "last_four": str(datos.get("last_four") or ""),
                "account_last_four": str(
                    datos.get("account_last_four") or ""
                ),
                "deadline": _t.time() + _TRX_AUTH_VENTANA_SEGUNDOS,
            }
        },
    )

    logger.info(
        "TXNR SUBIDA NIVEL 08 "
        "reto guardado "
        "challenge=%s authentication_state=%s "
        "device_id=%s profile_id=%s "
        "last_four=%s account_last_four=%s",
        bool(datos.get("challenge")),
        bool(datos.get("authentication_state")),
        bool(datos.get("device_id")),
        bool(datos.get("profile_id")),
        datos.get("last_four"),
        datos.get("account_last_four"),
    )


def _trx_auth_vencida(conversation: Conversation) -> bool:
    """True cuando pasaron los 3 minutos sin que el cliente autorizara."""

    import time as _t

    deadline = _trx_auth_state(conversation).get("deadline")
    try:
        return bool(deadline) and _t.time() > float(deadline)
    except (TypeError, ValueError):
        return False


def _trx_auth_limpiar(conversation: Conversation) -> None:
    """Descarta el reto: se usa al cerrar el bloqueo o al agotarse el plazo."""

    import json as _json

    estado = get_trx_state(conversation)
    estado.pop(_TRX_AUTH_KEY, None)
    # como STRING JSON: un dict en crudo revienta el guardado en OpenSearch
    # (mapper_parsing_exception) -- ver trx_state._serializar.
    conversation.captured_data[TRX_STATE_KEY] = _json.dumps(estado, ensure_ascii=False)


async def _trx_enviar_push_bloqueo(
    conversation: Conversation,
    trx_service_url: str | None,
    back_data_service_url: str | None,
    user_id: str,
) -> str:
    """Pasos 1-3: dispositivo, reto y envio del push.

    Returns: "enviado" | "sin_dispositivo" | "error"
    """

    card_id = str(conversation.captured_data.get("trx_card_id") or "").strip()
    producto = _resolve_selected_trx_product(conversation)
    last_four = _trx_last_four(producto)

    account_id = ""
    account_last_four = ""
    personal_id = ""

    logger.info(
        "TXNR SUBIDA NIVEL START "
        "conversation_id=%s user_id=%s card_id=%s "
        "last_four=%s personal_id=%s product=%s",
        conversation.conversation_id,
        user_id,
        card_id,
        last_four,
        bool(personal_id),
        producto,
    )

    if trx_service_url and last_four:

        logger.info(
            "TXNR SUBIDA NIVEL 01 "
            "consultando account_id "
            "customer_id=%s last_four=%s",
            user_id,
            last_four,
        )

        identity = await fetch_trx_account_identity(
            base_url=trx_service_url,
            customer_id=user_id,
            last_four=last_four,
        )

        account_id = str(identity.get("account_id") or "").strip()

        logger.info(
            "TXNR SUBIDA NIVEL 02 "
            "account_id lookup terminado "
            "found=%s account_length=%s",
            bool(account_id),
            len(account_id),
        )

        personal_id = str(identity.get("personal_id") or "").strip()
        if len(account_id) < 4:
            account_last_four = ""
        else:
            account_last_four = account_id[-4:]

        logger.info(
            "TXNR SUBIDA NIVEL 03 "
            "account_last_four calculado "
            "found=%s",
            bool(account_last_four),
        )

    logger.info(
        "TXNR SUBIDA NIVEL 04 "
        "validando prerrequisitos "
        "trx_service_url=%s card_id=%s personal_id=%s "
        "last_four=%s account_last_four=%s",
        bool(trx_service_url),
        bool(card_id),
        bool(personal_id),
        last_four,
        bool(account_last_four),
    )

    if (
        not trx_service_url
        or not card_id
        or not personal_id
        or not account_last_four
    ):
        missing = []

        if not trx_service_url:
            missing.append("trx_service_url")

        if not card_id:
            missing.append("card_id")

        if not personal_id:
            missing.append("personal_id")

        if not account_last_four:
            missing.append("account_last_four")

        if missing:
            logger.error(
                "TXNR SUBIDA NIVEL 05 "
                "NO SE EJECUTA subida_nivel_trx "
                "faltantes=%s",
                ",".join(missing),
            )

            return "error"
    
    logger.info(
        "TXNR SUBIDA NIVEL 06 "
        "EJECUTANDO subida_nivel_trx "
        "card_id=%s last_four=%s account_last_four=%s",
        card_id,
        last_four,
        account_last_four,
    )

    resp = await subida_nivel_trx(
        base_url=trx_service_url,
        card_id=card_id,
        personal_id=personal_id,
        last_four=last_four,
        account_last_four=account_last_four,
    )

    logger.info(
        "TXNR SUBIDA NIVEL 07 "
        "respuesta ASO recibida "
        "response_type=%s response=%s",
        type(resp).__name__,
        resp,
    )

    if not resp:
        return "error"
    if resp.get("status") == "sin_dispositivo":
        return "sin_dispositivo"
    if resp.get("status") != "ok" or not resp.get("challenge"):
        return "error"

    _trx_auth_guardar(
        conversation,
        {
            **resp,
            "last_four": last_four,
            "account_last_four": account_last_four,
        },
    )
    # Fase 4 (03/09): el ciclo de vida del reto pasa a co_pqrs_authorization.
    # El registro es FAIL-OPEN: sin servicio (o sin URL configurada) el flujo
    # sigue con la consulta directa de siempre -- rollout gradual por entorno.
    autorizacion_url = load_authorization_service_url()
    if autorizacion_url:
        registro = await registrar_autorizacion(
            base_url=autorizacion_url,
            conversation_id=conversation.conversation_id,
            workflow=conversation.workflow or "trx_no_reconocida",
            step=conversation.current_step,
            challenge=str(resp.get("challenge") or ""),
        )
        if registro and registro.get("authorization_id"):
            estado_auth = _trx_auth_state(conversation)
            estado_auth["authorization_id"] = str(registro["authorization_id"])
            update_trx_state(conversation, **{_TRX_AUTH_KEY: estado_auth})
            logger.info(
                "TXNR AUTH REGISTRADA authorization_id=%s conversation_id=%s",
                registro["authorization_id"],
                conversation.conversation_id,
            )

    logger.warning(
        "TXNR DEBUG AUTH GUARDADO "
        "trx_state=%r "
        "auth_state=%r",
        get_trx_state(conversation),
        _trx_auth_state(conversation),
    )

    return "enviado"


async def _trx_estado_push_bloqueo(
    conversation: Conversation,
    trx_service_url: str | None,
) -> str:
    """
    Consulta UNA sola vez el estado actual del reto.

    IMPORTANTE:
    - No hace polling.
    - No hace sleep.
    - No mantiene abierto el request.
    - La consulta ocurre únicamente cuando el usuario
      pulsa "Continuar".
    - subida_nivel_estado_trx() ya devuelve una respuesta normalizada.

    Estados internos:
        aceptado
        pendiente
        vencido
        rechazado
        error
    """

    # =========================================================
    # 1. Recuperar reto guardado
    # =========================================================

    auth = _trx_auth_state(conversation)

    logger.warning(
        "TXNR DEBUG AUTH ANTES CHECK "
        "trx_state=%r "
        "auth_state=%r",
        get_trx_state(conversation),
        auth,
    )


    challenge = str(
        auth.get("challenge") or ""
    ).strip()

    logger.info(
        "TXNR AUTH CHECK 01 "
        "challenge=%r auth_keys=%s",
        challenge,
        list(auth.keys()),
    )

    if not trx_service_url:
        logger.error(
            "TXNR AUTH CHECK 02 ERROR "
            "trx_service_url vacío"
        )
        return "error"

    if not challenge:
        logger.error(
            "TXNR AUTH CHECK 03 ERROR "
            "challenge vacío auth=%r",
            auth,
        )
        return "error"

    # =========================================================
    # 1b. FASE 4: el estado lo resuelve co_pqrs_authorization
    # =========================================================
    # El worker del servicio consulta el ASO y cumple el deadline aunque el
    # cliente no vuelva: aqui solo se LEE el resultado. Si el servicio no
    # esta configurado/disponible o el reto no quedo registrado, se degrada
    # a la consulta directa de siempre (fallback, comportamiento identico).

    authorization_id = str(auth.get("authorization_id") or "").strip()
    autorizacion_url = load_authorization_service_url()
    if authorization_id and autorizacion_url:
        resultado = await consultar_autorizacion(
            base_url=autorizacion_url,
            authorization_id=authorization_id,
        )
        if resultado is not None:
            estado_negocio = str(resultado.get("status") or "").strip().upper()
            logger.info(
                "TXNR AUTH CHECK A1 AUTHORIZATION "
                "authorization_id=%s status=%s technical=%s",
                authorization_id,
                estado_negocio,
                resultado.get("technical_status"),
            )
            if estado_negocio == "ACCEPTED":
                return "aceptado"
            if estado_negocio == "REJECTED":
                return "rechazado"
            if estado_negocio == "EXPIRED":
                return "vencido"
            if estado_negocio == "PENDING":
                # respaldo local del plazo, como siempre
                if _trx_auth_vencida(conversation):
                    return "vencido"
                return "pendiente"
            # estado no reconocible -> se degrada a la via directa
        logger.warning(
            "TXNR AUTH CHECK A2 FALLBACK a consulta directa "
            "authorization_id=%s",
            authorization_id,
        )

    # =========================================================
    # 2. CONSULTAR ASO UNA SOLA VEZ (via directa / fallback)
    # =========================================================

    logger.info(
        "TXNR AUTH CHECK 04 REQUEST "
        "challenge=%s",
        challenge,
    )

    try:
        resp = await subida_nivel_estado_trx(
            base_url=trx_service_url,
            challenge=challenge,
        )

    except Exception:
        logger.exception(
            "TXNR AUTH CHECK 05 EXCEPTION "
            "challenge=%s",
            challenge,
        )
        return "error"

    if resp is None:
        logger.warning(
            "TXNR AUTH CHECK 06 EMPTY RESPONSE "
            "challenge=%s",
            challenge,
        )
        return "error"

    logger.info(
        "TXNR AUTH CHECK 07 NORMALIZED RESPONSE "
        "challenge=%s response=%r",
        challenge,
        resp,
    )

    # =========================================================
    # 3. RESPUESTA YA NORMALIZADA
    # =========================================================

    status = str(
        resp.get("status") or ""
    ).strip().lower()

    aceptado = bool(
        resp.get("aceptado")
    )

    logger.info(
        "TXNR AUTH CHECK 08 "
        "challenge=%s status=%r aceptado=%r",
        challenge,
        status,
        aceptado,
    )

    # =========================================================
    # 4. AUTORIZADO
    # =========================================================

    if aceptado or status == "accepted":

        logger.info(
            "TXNR AUTH CHECK 09 AUTORIZADO "
            "challenge=%s",
            challenge,
        )

        return "aceptado"

    # =========================================================
    # 5. PENDIENTE
    # =========================================================

    if status == "pending":

        logger.info(
            "TXNR AUTH CHECK 10 PENDIENTE "
            "challenge=%s",
            challenge,
        )

        # El ASO todavía dice pending.
        # Solo aquí aplicamos nuestro vencimiento local
        # como respaldo.

        if _trx_auth_vencida(conversation):

            logger.warning(
                "TXNR AUTH CHECK 11 VENCIDO LOCALMENTE "
                "challenge=%s",
                challenge,
            )

            return "vencido"

        return "pendiente"

    # =========================================================
    # 6. VENCIDO
    # =========================================================

    if status == "expired":

        logger.warning(
            "TXNR AUTH CHECK 12 VENCIDO ASO "
            "challenge=%s",
            challenge,
        )

        return "vencido"

    # =========================================================
    # 7. RECHAZADO
    # =========================================================

    if status == "rejected":

        logger.warning(
            "TXNR AUTH CHECK 13 RECHAZADO "
            "challenge=%s",
            challenge,
        )

        return "rechazado"

    # =========================================================
    # 8. ESTADO DESCONOCIDO
    # =========================================================

    logger.warning(
        "TXNR AUTH CHECK 14 UNKNOWN STATUS "
        "challenge=%s status=%r response=%r",
        challenge,
        status,
        resp,
    )

    return "error"


async def _trx_bloqueo_ya_ejecutado(conversation: Conversation, hito: str) -> bool:
    """True si ESTE bloqueo (tipo+conversacion+producto) ya se ejecuto.

    Candado contra la doble reexpedicion: los gates de bloqueo hacen un POST
    real y eran los unicos sin proteccion de reejecucion. Si el turno fallaba
    DESPUES del POST, _finalize_background_chat_error recargaba el snapshot
    previo de la conversacion -descartando marcador y registro en memoria- y el
    reintento del cliente volvia a ejecutar el bloqueo: segunda tarjeta.

    El candado vive en el indice DURABLE (trx-no-reconocida-cases), que no se
    revierte con el snapshot. Se acota a la conversacion: no impide bloquear la
    misma tarjeta en una conversacion futura (un bloqueo temporal puede haberse
    reactivado entre medias).
    """

    try:
        store = TrxCaseStore()
        record = await store.get_case(_trx_customer_id(conversation))
        return bool(record) and hito in (record.get("milestones") or [])
    except Exception:
        # Fail-open: sin lectura no se bloquea el flujo; se pierde el candado.
        return False


async def _trx_record_milestone_async(
    conversation: Conversation, milestone: str, outcome: str | None = None
) -> None:
    """Registra un hito en el indice durable (fail-safe: no rompe el flujo)."""

    try:
        store = TrxCaseStore()
        await store.record_milestone(
            client_id=_trx_customer_id(conversation),
            conversation_id=conversation.conversation_id,
            milestone=milestone,
            snapshot=trx_snapshot(conversation),
            outcome=outcome,
        )
        _trx_trace_step(
            conversation, f"trx_case.{milestone}", outcome=outcome or "recorded", store="durable",
        )
    except Exception:
        logger.warning("trx milestone '%s' fallo (fail-open)", milestone)


async def _trx_bot_recurrence_hit(conversation: Conversation) -> bool:
    """True si el cliente ya paso por el flujo dentro de la ventana (MAX_TRX_BOT_RECURRENCE)."""

    try:
        store = TrxCaseStore()
        record = await store.get_case(_trx_customer_id(conversation))
        if not record:
            return False
        # Politica IT4.6: maximo 3 solicitudes por tipologia en 6 meses. Ambos valores
        # son parametros; los mismos que usa el servicio del tramite frente a Salesforce.
        meses = int(_trx_env("TRX_RECURRENCIA_MESES", "6"))
        count = store.get_bot_recurrence_count(record, months=meses)
        max_rec = int(_trx_env("MAX_TRX_BOT_RECURRENCE", "3"))
        _trx_trace_step(
            conversation, "trx_case.recurrence_bot",
            outcome="hit" if count >= max_rec else "ok", count=count, max=max_rec,
        )
        return count >= max_rec
    except Exception:
        return False


def _parse_transaction_amount(user_content: str) -> float | None:
    """Parse amounts like 50000, 50.000 or $50,000 into float."""

    cleaned = re.sub(r"[^\d,.-]", "", user_content or "")
    if not cleaned:
        return None

    normalized = cleaned.replace(".", "").replace(",", "")
    try:
        value = float(normalized)
    except ValueError:
        return None
    return value if value > 0 else None


def _get_user_trx_list(conversation: Conversation) -> list[dict[str, Any]]:
    """Return normalized list stored in captured_data[user_trx_list]."""

    raw = conversation.captured_data.get(_TRX_USER_LIST_KEY)
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _trx_clave_producto(conversation: Conversation) -> str:
    """Identificador estable del producto seleccionado, para el registro de bloqueos."""

    producto = _resolve_selected_trx_product(conversation) or {}
    # contract_id PRIMERO: es la unica llave presente e identica en las dos
    # ramas de fetch. Con product_id primero, la misma tarjeta producia dos
    # llaves distintas -- back_data mapea product_id=key_id ("KTRXC1") y la
    # rama HTTP acaba con product_id=contract_id -- y el salto del gate .15 no
    # disparaba: se volvia a bloquear una tarjeta ya bloqueada.
    return str(
        (producto.get("card_id") or producto.get("contract_id"))
        or producto.get("product_id")
        or producto.get("key_id")
        or _trx_last_four(producto)
        or ""
    ).strip()


def _trx_productos_bloqueados(conversation: Conversation) -> dict:
    raw = conversation.captured_data.get(_TRX_BLOQUEADOS_KEY)
    if not raw:
        return {}
    try:
        datos = json.loads(raw)
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def _trx_producto_bloqueado(conversation: Conversation, clave: str) -> str:
    """Devuelve el tipo de bloqueo ya aplicado a ese producto, o "" si ninguno."""

    if not clave:
        return ""
    return str(_trx_productos_bloqueados(conversation).get(clave) or "")


def _trx_registrar_bloqueo(conversation: Conversation, tipo: str) -> None:
    """Anota que el producto seleccionado quedo bloqueado en esta conversacion.

    Se guarda por producto y no por transaccion: es la tarjeta la que queda
    bloqueada, y volver a preguntarlo en la siguiente transaccion del bucle no
    tiene sentido.
    """

    clave = _trx_clave_producto(conversation)
    if not clave:
        return
    datos = _trx_productos_bloqueados(conversation)
    datos[clave] = tipo
    conversation.captured_data[_TRX_BLOQUEADOS_KEY] = json.dumps(datos, ensure_ascii=False)


def _trx_get_n(conversation: Conversation) -> int:
    """Número de transacciones a reportar (1..3) capturado en 2.4.0.1.2."""

    raw = str(conversation.flow_answers.get("trx_cantidad") or "").strip().lower()
    return int(raw) if raw in {"1", "2", "3"} else 1


def _trx_get_index(conversation: Conversation) -> int:
    """Índice (1-based) de la transacción que se está procesando en el bucle."""

    try:
        return int(conversation.captured_data.get("trx_index") or 1)
    except (TypeError, ValueError):
        return 1


def _trx_reset_per_tx_state(conversation: Conversation) -> None:
    """Limpia el estado por-transacción para arrancar limpia la siguiente."""

    for key in (
        "trx_products_result",
        "trx_products_status",
        "trx_products_map",
        "trx_movimientos_result",
        "trx_card_id",
        "trx_detalle_result",
        "trx_clasificacion",
        "trx_vigencia",
        _TRX_DATA_NOTIFIED_KEY,
    ):
        conversation.captured_data.pop(key, None)
    # TODO el contenido dinamico de los pasos TXNR se limpia por PREFIJO, no
    # por lista. La lista explicita cubria 4 claves y el flujo escribe 11 por
    # transaccion (.7, .8.return, .11, .16.2, .17.2, .18, .19.1, .19.2, .20...).
    # Las que quedaban fuera cruzaban a la siguiente transaccion del bucle: el
    # aviso de "fuera de rango" aparecia en un dia sin movimientos, y el "tu
    # tarjeta ya quedo bloqueada" salia con la tarjeta ANTERIOR tras bloquear
    # otra distinta. El prefijo tambien cubre los dinamicos que se anadan
    # manana sin depender de que alguien se acuerde de esta lista.
    for key in [
        k for k in list(conversation.captured_data)
        if k.startswith(("dynamic_prompt_2.4.0.1", "dynamic_option_labels_2.4.0.1",
                         "dynamic_option_keys_2.4.0.1"))
    ]:
        conversation.captured_data.pop(key, None)
    # OJO: _TRX_BLOQUEADOS_KEY NO se limpia a proposito, al contrario que todo
    # lo demas de esta funcion. El bloqueo es de la TARJETA, no de la
    # transaccion: si se borrara, la siguiente vuelta del bucle volveria a
    # ofrecer bloquear un producto que ya esta bloqueado.
    for key in (
        "producto_trx_no_reconocida",
        "trx_fecha",
        "trx_rango_valor",
        "trx_movimiento_seleccionado",
        "trx_confirmacion_movimiento",
    ):
        conversation.flow_answers.pop(key, None)
    try:
        reset_per_tx(conversation)
    except Exception:
        pass


async def _handle_trx_interactive_capture_step(
    *,
    conversation: Conversation,
    user_content: str,
    workflow_engine: WorkflowEngine,
    trx_service_url: str | None,
    back_data_service_url: str | None,
    control_store: ControlTableStore | None,
) -> str | None:
    """Orquesta el bucle "una transacción a la vez" del flujo TXNR (arbol Fase 2).

    Corre ANTES de ``generate_response``: ``current_step`` es el paso que el
    usuario acaba de contestar y ``user_content`` es la key de la opción elegida.
    """

    if (conversation.workflow or "") != "trx_no_reconocida":
        return None

    step = conversation.current_step
    key = _normalize_text(user_content)

    # Inicializa el índice al arrancar la primera transacción; setdefault para no
    # pisar el contador cuando el bucle vuelve a 2.4.0.1.3 en la 2a/3a tx.
    if step == _TRX_CONFIRM_DATA_STEP:
        conversation.captured_data.setdefault("trx_index", "1")
        return None

    def _advance_next_tx() -> str:
        # Este handler produce la respuesta del turno SIN pasar por
        # generate_response (que es quien marca ACTIVE). Si no lo marcamos aqui,
        # la conversacion queda en RUNNING y el front se cuelga en polling.
        conversation.status = ConversationStatus.ACTIVE
        conversation.running_since = None
        total = _trx_get_n(conversation)
        next_i = _trx_get_index(conversation) + 1
        _trx_reset_per_tx_state(conversation)
        conversation.captured_data["trx_index"] = str(next_i)
        conversation.current_step = _TRX_CONFIRM_DATA_STEP
        prompt = workflow_engine.render_current_step_prompt(conversation) or ""
        header = f"Continuemos con la transacci\u00f3n {next_i} de {total}.\n\n"
        return f"{header}{prompt}".strip()

    # Bucle multi-transaccion: 2.4.0.1.20.1 "Si, reportar la siguiente".
    if step == _TRX_LOOP_STEP and key in {"si_siguiente", "si", "continuar"}:
        if _trx_get_index(conversation) < _trx_get_n(conversation):
            return _advance_next_tx()
        return None

    return None


# Keys stored for internal bookkeeping/metadata that do NOT represent resolved
# business data. Excluded from _has_resolved_guide_data to prevent false positives.
_INTERNAL_CAPTURED_DATA_KEYS: frozenset[str] = frozenset(
    {
        _START_ROUTING_STATE_KEY,
        _START_ROUTING_WORKFLOW_KEY,
        _START_ROUTING_CONFIDENCE_KEY,
        _START_ROUTING_RATIONALE_KEY,
        _START_ROUTING_ENTRY_HINT_KEY,
        _WORKFLOW_ENTRY_HINT_KEY,
        _REPEAT_FLOW_WARNING_STATE_KEY,
        _REPEAT_FLOW_WORKFLOW_KEY,
        _REPEAT_FLOW_LABEL_KEY,
        _BACK_DATA_NOTIFIED_KEY,
        # Marca de origen para la analitica (_EVENT_SOURCE_KEY, "benchmark"):
        # metadato, nunca un dato de negocio resuelto.
        "source",
        "control_interaction_recorded",
        "preserve_terminal_response",
        "guide_closure_mode",
        "llm_response_source",
        "llm_usage_status",
        "llm_input_tokens",
        "llm_output_tokens",
        "llm_total_tokens",
        "llm_fallback_reason",
    }
)
_ASYNC_CHAT_ERROR_MESSAGE = (
    "Tuvimos un inconveniente mientras procesabamos tu solicitud. "
    "Por favor intenta de nuevo."
)
_EMBARGO_PRODUCTS_CSV_PATH = (
    Path(__file__).resolve().parents[2]
    / "domain"
    / "workflow"
    / "guia_rapida"
    / "Muestra_tabla_embargos.csv"
)
_CUSTOMER_NAME_COLUMNS = (
    "customer_name",
    "client_name",
    "nombre_cliente",
    "nombre",
    "customer_full_name",
    "full_name",
    "name",
)
_DEFAULT_CUSTOMER_NAME = "cliente"
_GENERAL_MESSAGES = load_general_messages()

_CONVERSATION_LOCKS: dict[str, asyncio.Lock] = {}
_CONVERSATION_LOCKS_GUARD = asyncio.Lock()
_BACKGROUND_CHAT_TASKS: dict[str, asyncio.Task[Conversation]] = {}
_BACKGROUND_CHAT_TASKS_GUARD = asyncio.Lock()


def _schedule_error_report(*, conversation_id: str, error: BaseException) -> None:
    """Audit a failed background chat turn (fire-and-forget, never raises)."""

    schedule_error_report(
        conversation_id=conversation_id,
        error=error,
        source="background_chat_turn",
    )


# --- RabbitMQ event publishing (real-time analytics) -------------------------
# Detached fire-and-forget event tasks; strong refs prevent GC before they run.
_EVENT_TASKS: set[asyncio.Task[None]] = set()
_EVENT_PUBLISHER: EventPublisher | None = None
_EVENT_PUBLISHER_RESOLVED = False


def _get_event_publisher() -> EventPublisher | None:
    """Return a cached EventPublisher, or None when publishing is disabled.

    Settings are read once per process. When RabbitMQ is disabled this is a
    permanent no-op, so the hot path pays almost nothing.
    """

    global _EVENT_PUBLISHER, _EVENT_PUBLISHER_RESOLVED
    if _EVENT_PUBLISHER_RESOLVED:
        return _EVENT_PUBLISHER

    try:
        settings = load_rabbitmq_settings()
    except Exception:
        logger.exception("Could not load RabbitMQ settings; event publishing disabled")
        _EVENT_PUBLISHER_RESOLVED = True
        _EVENT_PUBLISHER = None
        return None

    _EVENT_PUBLISHER = EventPublisher(settings) if settings.enabled else None
    _EVENT_PUBLISHER_RESOLVED = True
    if _EVENT_PUBLISHER is None:
        logger.info("RabbitMQ event publishing is disabled")
    else:
        logger.info("RabbitMQ event publishing is enabled exchange=%s", settings.exchange)
    return _EVENT_PUBLISHER


def _emit_event(routing_key: str, payload: dict[str, object]) -> None:
    """Schedule a non-blocking event publish. Never raises, never blocks.

    No-op when RabbitMQ is disabled. Fire-and-forget so it cannot add latency to
    the conversation or change its outcome.
    """

    publisher = _get_event_publisher()
    if publisher is None:
        return

    try:
        task = asyncio.create_task(publisher.publish(routing_key, payload))
        _EVENT_TASKS.add(task)
        task.add_done_callback(_EVENT_TASKS.discard)
    except Exception:
        logger.exception("Failed to schedule event routing_key=%s", routing_key)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _conversation_duration_ms(conversation: Conversation) -> int | None:
    """Total session duration from first to last message, in milliseconds."""

    if conversation.first_msg_date is None or conversation.last_msg_date is None:
        return None
    delta = conversation.last_msg_date - conversation.first_msg_date
    return max(int(delta.total_seconds() * 1000), 0)


# Origen de la conversacion para la analitica. Se PERSISTE en captured_data al
# abrir la sesion (POST /start con la cabecera X-Benchmark-Mode) para que TODOS
# los eventos conversation.* de esa conversacion (incluido un cierre posterior
# sin cabecera, p.ej. por mantenimiento) salgan con el mismo ``source``.
# Logstash desvia los eventos con source == "benchmark" a indices propios.
_EVENT_SOURCE_KEY = "source"
_EVENT_SOURCE_BENCHMARK = "benchmark"
_EVENT_SOURCE_LIVE = "live"


def _mark_benchmark_conversation(conversation: Conversation) -> bool:
    """Persist the benchmark mark on the conversation. Returns True if changed."""

    if conversation.captured_data.get(_EVENT_SOURCE_KEY) == _EVENT_SOURCE_BENCHMARK:
        return False
    conversation.captured_data[_EVENT_SOURCE_KEY] = _EVENT_SOURCE_BENCHMARK
    return True


def _event_source(conversation: Conversation | None) -> str:
    """Decide the ``source`` of an analytics event: ``benchmark`` or ``live``.

    The persisted mark wins; as a fallback, an active benchmark context (the
    request carried ``X-Benchmark-Mode``) also counts as benchmark. Never raises.
    """

    try:
        if conversation is not None:
            captured = conversation.captured_data or {}
            if captured.get(_EVENT_SOURCE_KEY) == _EVENT_SOURCE_BENCHMARK:
                return _EVENT_SOURCE_BENCHMARK
        if _benchmark_context_active():
            return _EVENT_SOURCE_BENCHMARK
    except Exception:  # noqa: BLE001 - analytics never break the turn
        logger.debug("Could not resolve event source; defaulting to live")
    return _EVENT_SOURCE_LIVE


def _build_started_event(conversation: Conversation) -> dict[str, object]:
    return {
        "event": "conversation.started",
        "source": _event_source(conversation),
        "conversation_id": conversation.conversation_id,
        "user_id": conversation.user_id,
        "ts": _now_iso(),
    }


def _build_turn_event(
    conversation: Conversation,
    *,
    turn_usage: TokenUsage,
    duration_ms: int,
) -> dict[str, object]:
    captured = conversation.captured_data
    return {
        "event": "conversation.turn",
        "source": _event_source(conversation),
        "conversation_id": conversation.conversation_id,
        "user_id": conversation.user_id,
        "general_workflow": conversation.general_workflow,
        "workflow": conversation.workflow,
        "current_step": conversation.current_step,
        "status": conversation.status.value,
        "message_count": len(conversation.messages),
        "tokens": {
            "input_tokens": turn_usage.input_tokens,
            "output_tokens": turn_usage.output_tokens,
            "total_tokens": turn_usage.total_tokens,
        },
        "duration_ms": duration_ms,
        "satisfaction_status": conversation.satisfaction_status,
        "satisfaction_result": conversation.satisfaction_result,
        "llm_usage_status": captured.get("llm_usage_status"),
        "llm_fallback_reason": captured.get("llm_fallback_reason"),
        # LLM realmente consumido en el turno (proxy de costo): hubo tokens.
        "llm_used": turn_usage.total_tokens > 0,
        # El guardrail bloqueó la entrada del usuario en este turno.
        "guardrail_blocked": captured.get("_last_guardrail_blocked") == "true",
        # Porton de despliegue TXNR: cuantos clientes pidieron el flujo mientras
        # estaba cerrado (trx_gated) y cuantos turnos fueron de un probador.
        "trx_gated": captured.get(_TRX_GATED_KEY) == "true",
        "trx_canary": captured.get(_TRX_CANARY_KEY) == "true",
        # Resultado del ruteo del turno: matched / confirmation / no_match /
        # in_flow / guardrail_blocked / other.
        "routing_outcome": captured.get("routing_outcome"),
        # Subflujo elegido (solo centrales de riesgo), para legibilidad del step.
        "subflow_key": (
            conversation.flow_answers.get(_CENTRALES_SUBFLOW_ANSWER)
            if conversation.workflow == _CENTRALES_WORKFLOW
            else None
        ),
        "ts": _now_iso(),
    }


def _build_trace_event(
    conversation: Conversation,
    *,
    turn_usage: TokenUsage,
    duration_ms: int,
) -> dict[str, object]:
    """Evento de TRAZA de conversacion para el tablero de analitica.

    Incluye el contenido del ultimo par pregunta/respuesta del turno
    (``user_content`` + ``assistant_content``) para poder ver, por conversacion,
    qué preguntó el usuario y qué respondió el bot. Va al indice
    ``pqr-conversations-*`` (routing key ``conversation.trace``).
    """

    user_content = ""
    assistant_content = ""
    for message in reversed(conversation.messages):
        if not assistant_content and message.role == MessageRole.ASSISTANT:
            assistant_content = message.content
        elif not user_content and message.role == MessageRole.USER:
            user_content = message.content
        if user_content and assistant_content:
            break

    return {
        "event": "conversation.trace",
        "source": _event_source(conversation),
        "conversation_id": conversation.conversation_id,
        "user_id": conversation.user_id,
        "general_workflow": conversation.general_workflow,
        "workflow": conversation.workflow,
        "current_step": conversation.current_step,
        "status": conversation.status.value,
        "satisfaction_status": conversation.satisfaction_status,
        "satisfaction_result": conversation.satisfaction_result,
        "user_content": user_content,
        "assistant_content": assistant_content,
        "message_count": len(conversation.messages),
        "tokens": {
            "input_tokens": turn_usage.input_tokens,
            "output_tokens": turn_usage.output_tokens,
            "total_tokens": turn_usage.total_tokens,
        },
        "duration_ms": duration_ms,
        "ts": _now_iso(),
    }


def _classify_resolution(conversation: Conversation) -> str:
    """Clasifica CÓMO cerró la conversación, para medir contención/resolución.

    Valores: ``limit_closed`` (cerrada por un tope), ``abandoned`` (abandonó la
    encuesta de satisfacción), ``resolved`` (dijo que sí se resolvió),
    ``not_resolved`` (dijo que no) o ``closed`` (cierre sin señal de satisfacción).
    """

    captured = conversation.captured_data
    if captured.get(_SESSION_LIMIT_CLOSED_KEY) == "true":
        return "limit_closed"
    status = (conversation.satisfaction_status or "").upper()
    if status == "ABANDONED":
        return "abandoned"
    if conversation.satisfaction_result is True:
        return "resolved"
    if conversation.satisfaction_result is False:
        return "not_resolved"
    return "closed"


def _build_closed_event(conversation: Conversation) -> dict[str, object]:
    return {
        "event": "conversation.closed",
        "source": _event_source(conversation),
        "conversation_id": conversation.conversation_id,
        "user_id": conversation.user_id,
        "general_workflow": conversation.general_workflow,
        "workflow": conversation.workflow,
        "current_step": conversation.current_step,
        "status": conversation.status.value,
        "satisfaction_status": conversation.satisfaction_status,
        "satisfaction_result": conversation.satisfaction_result,
        "message_count": len(conversation.messages),
        "duration_total_ms": _conversation_duration_ms(conversation),
        "resolution": _classify_resolution(conversation),
        "ts": _now_iso(),
    }


def _build_cap_reached_event(
    conversation: Conversation,
    *,
    limit_key: str,
    limit_label: str,
    limit_scope: str,
) -> dict[str, object]:
    """Evento emitido cuando un usuario alcanza el tope diario de un caso.

    ``limit_scope`` = ``"case"`` (uno de los 20 casos) o ``"centrales_subflow"``
    (uno de los 3 subflujos de centrales). Permite medir cuántos usuarios topan
    cada casuística por día (índice ``pqr-metrics-*``).
    """

    return {
        "event": "conversation.cap_reached",
        "source": _event_source(conversation),
        "conversation_id": conversation.conversation_id,
        "user_id": conversation.user_id,
        "workflow": conversation.workflow,
        "limit_key": limit_key,
        "limit_label": limit_label,
        "limit_scope": limit_scope,
        "ts": _now_iso(),
    }


def _build_error_event(
    conversation_id: str,
    error: BaseException,
    conversation: Conversation | None = None,
) -> dict[str, object]:
    return {
        "event": "conversation.error",
        "source": _event_source(conversation),
        "conversation_id": conversation_id,
        "error_type": type(error).__name__,
        "error_message": str(error) or repr(error),
        "ts": _now_iso(),
    }


@log_execution
async def _load_back_data_from_control_table(
    *,
    conversation: Conversation,
    control_store: ControlTableStore,
    user_id: str,
    workflow_id: str,
    expected_run_id: str | None = None,
) -> tuple[str, dict[str, object] | None]:
    """Poll the control table for a FRESH back-data envelope.

    Returns ``(status, data)``:
      - ``("ok", data)``    only when ``status == "ok"`` AND the envelope
        ``run_id`` matches the run that triggered this request (freshness).
      - ``("error", None)`` when back_data recorded an error for this run
        (e.g. the ASO returned 409): the caller must NOT serve "no reports".
      - ``("timeout", None)`` when nothing fresh appeared within the budget.
    """

    max_attempts = _back_data_max_poll_attempts()
    poll_interval = _back_data_poll_interval_seconds()
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            await asyncio.sleep(poll_interval)

        record = await control_store.get_record(user_id)
        envelope = control_store.get_workflow_back_data_envelope(
            record, workflow_id, expected_run_id=expected_run_id
        )
        status = envelope.get("status")
        run_id = envelope.get("run_id")
        run_matches = expected_run_id is None or run_id == expected_run_id

        if status == "ok" and run_matches and isinstance(envelope.get("data"), dict):
            logger.info(
                "Fresh back-data OK conversation_id=%s user_id=%s attempt=%s run_id=%s",
                conversation.conversation_id,
                user_id,
                attempt,
                run_id,
            )
            schedule_trace_event(
                event_type="polling",
                operation="back_data_control_table",
                outcome="hit",
                conversation_id=conversation.conversation_id,
                customer_id=user_id,
                request_summary={"attempt": attempt, "workflow": workflow_id, "run_id": run_id},
                tags=["polling", "back_data"],
            )
            return "ok", envelope["data"]

        if status == "error" and run_matches:
            logger.warning(
                "Back-data ERROR envelope conversation_id=%s user_id=%s attempt=%s run_id=%s error=%s",
                conversation.conversation_id,
                user_id,
                attempt,
                run_id,
                envelope.get("error"),
            )
            schedule_trace_event(
                event_type="polling",
                operation="back_data_control_table",
                outcome="hit_error",
                conversation_id=conversation.conversation_id,
                customer_id=user_id,
                request_summary={"attempt": attempt, "workflow": workflow_id, "run_id": run_id},
                response_summary={"error": envelope.get("error")},
                tags=["polling", "back_data"],
            )
            return "error", None

    # Fase 0 (02/09): la traza de timeout llevaba solo "attempts". Sin ver el
    # documento no se podia distinguir entre "back_data no escribio", "escribio en
    # otro mes", "el sobre quedo en pending" y "el documento no existe". Se emite
    # un resumen SIN datos de negocio para que el proximo caso se diagnostique
    # leyendo el bucket de trazas, que es lo que si esta accesible.
    diagnostico: dict[str, object] = {}
    try:
        record = await control_store.get_record(user_id)
        diagnostico = control_store.describe_back_data_envelopes(record, workflow_id)
    except Exception:  # pragma: no cover - la traza nunca rompe el turno
        logger.exception(
            "No se pudo construir el diagnostico del timeout conversation_id=%s",
            conversation.conversation_id,
        )
    logger.info(
        "No FRESH back-data after polling conversation_id=%s user_id=%s attempts=%s "
        "expected_run_id=%s diagnostico=%s",
        conversation.conversation_id,
        user_id,
        max_attempts,
        expected_run_id,
        diagnostico,
    )
    schedule_trace_event(
        event_type="polling",
        operation="back_data_control_table",
        outcome="timeout",
        conversation_id=conversation.conversation_id,
        customer_id=user_id,
        request_summary={
            "attempts": max_attempts,
            "workflow": workflow_id,
            "expected_run_id": expected_run_id,
        },
        response_summary=diagnostico,
        tags=["polling", "back_data"],
    )
    return "timeout", None


def _resolve_selected_notif_key_id(conversation: Conversation) -> str:
    """Resolve the key_id of the product selected in the notificacion listing.

    Phase 1 stores the reported products in ``centrales_riesgo_notif_map`` and the
    selection step saves the chosen option (``producto_N``) under
    ``producto_notificacion_centrales``. This maps that choice back to its key_id.
    """
    raw = conversation.captured_data.get("centrales_riesgo_notif_map")
    selected = conversation.flow_answers.get("producto_notificacion_centrales")
    if not raw or not selected:
        return ""
    try:
        products = json.loads(raw)
        index = int(str(selected).split("_")[-1]) - 1
        entry = products[index]
        return str(entry.get("key_id") or entry.get("product_id") or "").strip()
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not resolve selected notif key_id conversation_id=%s selected=%s",
            conversation.conversation_id,
            selected,
        )
        return ""


@log_execution
async def _prefetch_back_data_if_needed(
    conversation: Conversation,
    back_data_service_url: str,
    control_store: ControlTableStore | None,
) -> None:
    """
    When the conversation enters a back-data step, call the back-data
    service, poll the control table until the payload appears, then cache
    the result in captured_data so the workflow action can use it directly.

    A flag prevents a second round-trip for the same conversation.
    """

    step = conversation.current_step
    if step not in {
        _BACK_DATA_CONSULTAR_STEP,
        _BACK_DATA_CENTRALES_STEP,
        _BACK_DATA_NOTIFICACION_STEP,
        _BACK_DATA_NOTIFICACION_PRODUCTO_STEP,
    }:
        return

    # Guard por-paso: evita re-disparar el MISMO paso, pero permite una segunda
    # llamada a back_data cuando el flujo entra a un paso distinto (fase 2 del
    # flujo 3: analizar el producto elegido).
    if conversation.captured_data.get(_BACK_DATA_NOTIFIED_KEY) == step:
        return

    user_id = conversation.user_id or _extract_customer_id(conversation.conversation_id)
    workflow_id = conversation.workflow or ""
    conversation.captured_data[_BACK_DATA_NOTIFIED_KEY] = step
    # Freshness token: back_data echoes it into the control-table envelope and
    # the poll only accepts a result whose run_id matches (no stale/false data).
    run_id = str(uuid4())
    conversation.captured_data["back_data_run_id"] = run_id
    conversation.captured_data.pop("back_data_result", None)
    conversation.captured_data.pop("back_data_status", None)

    if control_store is not None and workflow_id:
        try:
            await control_store.clear_workflow_back_data(
                client_id=user_id,
                workflow_id=workflow_id,
            )
            logger.info(
                "Cleared stale workflow back-data before pre-fetch conversation_id=%s user_id=%s workflow_id=%s",
                conversation.conversation_id,
                user_id,
                workflow_id,
            )
        except Exception:
            logger.exception(
                "Failed to clear stale workflow back-data before pre-fetch conversation_id=%s user_id=%s workflow_id=%s",
                conversation.conversation_id,
                user_id,
                workflow_id,
            )

    if step == _BACK_DATA_CONSULTAR_STEP:
        logger.info(
            "Pre-fetching consultar data conversation_id=%s user_id=%s workflow_id=%s",
            conversation.conversation_id,
            user_id,
            workflow_id,
        )
        await trigger_consultar(
            base_url=back_data_service_url,
            customer_id=user_id,
            workflow=workflow_id,
            run_id=run_id,
        )
    elif step == _BACK_DATA_CENTRALES_STEP:
        logger.info(
            "Pre-fetching centrales_no_autorizo data conversation_id=%s user_id=%s workflow_id=%s",
            conversation.conversation_id,
            user_id,
            workflow_id,
        )
        await trigger_centrales_no_autorizo(
            base_url=back_data_service_url,
            customer_id=user_id,
            workflow=workflow_id,
            run_id=run_id,
        )
    else:
        logger.info(
            "Pre-fetching notificacion_centrales data conversation_id=%s user_id=%s workflow_id=%s",
            conversation.conversation_id,
            user_id,
            workflow_id,
        )
        if step == _BACK_DATA_NOTIFICACION_PRODUCTO_STEP:
            selected_key_id = _resolve_selected_notif_key_id(conversation)
            logger.info(
                "Pre-fetching notificacion_centrales_producto (fase 2) conversation_id=%s user_id=%s key_id=%s",
                conversation.conversation_id,
                user_id,
                selected_key_id,
            )
            await trigger_notificacion_centrales_producto(
                base_url=back_data_service_url,
                customer_id=user_id,
                workflow=workflow_id,
                key_id=selected_key_id,
                run_id=run_id,
            )
        else:
            await trigger_notificacion_centrales(
                base_url=back_data_service_url,
                customer_id=user_id,
                workflow=workflow_id,
                run_id=run_id,
            )

    if control_store is None:
        return

    try:
        logger.info(
            "Polling control table for back-data conversation_id=%s user_id=%s workflow_id=%s",
            conversation.conversation_id,
            user_id,
            workflow_id,
        )
        status, back_data = await _load_back_data_from_control_table(
            conversation=conversation,
            control_store=control_store,
            user_id=user_id,
            workflow_id=workflow_id,
            expected_run_id=run_id,
        )
        if status == "ok" and back_data:
            conversation.captured_data["back_data_result"] = json.dumps(
                back_data, ensure_ascii=False
            )
            conversation.captured_data["back_data_status"] = "ok"
            try:
                _validaciones = (back_data.get("hallazgos", {}) or {}).get(
                    "validaciones", []
                )
                _id_msgs = [
                    (v.get("key_id"), h.get("id_msg"))
                    for v in _validaciones
                    for h in (v.get("hallazgos") or [])
                ]
            except Exception:
                _id_msgs = []
            logger.info(
                "BACK-DATA recibido conversation_id=%s step=%s id_msgs=%s",
                conversation.conversation_id,
                step,
                _id_msgs,
            )
            logger.info(
                "Back-data result cached in conversation conversation_id=%s user_id=%s",
                conversation.conversation_id,
                user_id,
            )
        else:
            # error/timeout: NEVER serve stale data. Record the status so the
            # terminal action shows a "no pude verificar" message instead of a
            # false "no tienes reportes negativos".
            conversation.captured_data["back_data_status"] = status
            conversation.captured_data.pop("back_data_result", None)
            if status == "timeout":
                # Allow a fresh attempt on a later turn (error is definitive).
                conversation.captured_data.pop(_BACK_DATA_NOTIFIED_KEY, None)
            logger.warning(
                "Back-data NOT verified conversation_id=%s status=%s run_id=%s",
                conversation.conversation_id,
                status,
                run_id,
            )
    except Exception:
        logger.exception(
            "Failed to read control table after back-data pre-fetch conversation_id=%s",
            conversation.conversation_id,
        )


@log_execution
async def _get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    """
    Return a per-conversation lock to avoid concurrent updates clobbering the
    same conversation within a worker.
    """

    logger.info("Resolving conversation lock conversation_id=%s", conversation_id)
    async with _CONVERSATION_LOCKS_GUARD:
        if conversation_id not in _CONVERSATION_LOCKS:
            _CONVERSATION_LOCKS[conversation_id] = asyncio.Lock()

        return _CONVERSATION_LOCKS[conversation_id]


@log_execution
async def _release_conversation_lock(conversation_id: str) -> None:
    """
    Remove the per-conversation lock once the conversation reaches a terminal
    state (CLOSED or ERROR) so the dict does not grow unbounded.
    """

    logger.info("Releasing conversation lock conversation_id=%s", conversation_id)
    async with _CONVERSATION_LOCKS_GUARD:
        _CONVERSATION_LOCKS.pop(conversation_id, None)


def _is_running_stuck(
    conversation: Conversation, *, now: datetime | None = None
) -> bool:
    """Whether a RUNNING conversation has been stuck past the watchdog threshold.

    Guards against a turn left in RUNNING with no live background task (e.g. a
    pod restart killed the in-memory task). The 120s turn hard cap normally
    finalizes turns well before this 150s backstop fires.
    """

    if conversation.status != ConversationStatus.RUNNING:
        return False
    if conversation.running_since is None:
        return False

    reference = now or datetime.now(UTC)
    started = conversation.running_since
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return (reference - started).total_seconds() > _RUNNING_WATCHDOG_SECONDS


@log_execution
async def _recover_stuck_running(
    conversation: Conversation,
    store: ConversationStore,
    *,
    release_lock: bool = True,
) -> None:
    """Auto-recover a conversation stuck in RUNNING so it can be used again."""

    logger.warning(
        "Recovering stuck RUNNING conversation conversation_id=%s running_since=%s",
        conversation.conversation_id,
        conversation.running_since,
    )
    conversation.status = ConversationStatus.ACTIVE
    conversation.running_since = None
    await store.save_conversation_reference(conversation)
    await store.refresh()
    if release_lock:
        await _release_conversation_lock(conversation.conversation_id)


@log_execution
async def _register_background_chat_task(
    conversation_id: str,
    task: asyncio.Task[Conversation],
) -> None:
    """Register the in-flight async task associated with a conversation."""

    async with _BACKGROUND_CHAT_TASKS_GUARD:
        _BACKGROUND_CHAT_TASKS[conversation_id] = task

    task.add_done_callback(
        lambda completed_task: asyncio.create_task(
            _unregister_background_chat_task(conversation_id, completed_task)
        )
    )


@log_execution
async def _unregister_background_chat_task(
    conversation_id: str,
    task: asyncio.Task[Conversation],
) -> None:
    """Remove a completed async task from the in-memory registry."""

    async with _BACKGROUND_CHAT_TASKS_GUARD:
        stored_task = _BACKGROUND_CHAT_TASKS.get(conversation_id)
        if stored_task is task:
            _BACKGROUND_CHAT_TASKS.pop(conversation_id, None)


@log_execution
def _build_user_message(content: str) -> Message:
    """
    Build a user message from the minimal public API payload.

    Args:
        content: Raw message content sent by the user.

    Returns:
        A fully initialized runtime Message object.
    """

    logger.info("Building user message content_length=%s", len(content))
    return Message(
        id=str(uuid4()),
        role=MessageRole.USER,
        content=content,
        tokens=TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        ),
        timing=MessageTiming(received_at=datetime.now(UTC)),
    )


@log_execution
def _build_assistant_message(
    content: str,
    *,
    received_at: datetime,
    responded_at: datetime,
) -> Message:
    """
    Build an assistant message from the workflow engine response.

    Args:
        content: Assistant content returned by the workflow engine.
        received_at: Timestamp when assistant processing started.
        responded_at: Timestamp when assistant processing finished.

    Returns:
        An assistant message ready to be appended to the conversation.
    """

    logger.info(
        "Building assistant message content_length=%s received_at=%s responded_at=%s",
        len(content),
        received_at.isoformat(),
        responded_at.isoformat(),
    )
    assistant_message = Message(
        id=str(uuid4()),
        role=MessageRole.ASSISTANT,
        content=content,
        tokens=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        timing=MessageTiming(received_at=received_at),
    )
    assistant_message.set_response_time(responded_at)
    return assistant_message


@log_execution
def _finalize_user_message_timing(
    user_message: Message,
    responded_at: datetime,
) -> None:
    """
    Close the user message timing once the assistant response is ready.

    Args:
        user_message: User message whose response timing should be completed.
        responded_at: Timestamp when the assistant response was completed.
    """

    logger.info(
        "Finalizing user message timing user_message_id=%s responded_at=%s",
        user_message.id,
        responded_at.isoformat(),
    )
    user_message.set_response_time(responded_at)


@log_execution
def _extract_customer_id(conversation_id: str) -> str:
    """
    Extract the customer identifier from a partitioned conversation id.

    Args:
        conversation_id: Value formatted as `customer_id_yyyymmdd`.

    Returns:
        Customer identifier prefix.
    """

    customer_id, _ = conversation_id.rsplit("_", maxsplit=1)
    return customer_id


@log_execution
def _build_conversation_id(
    user_id: str,
    *,
    current_time: datetime | None = None,
) -> str:
    """
    Build the public conversation identifier using the local calendar date.

    Args:
        user_id: User identifier received by `POST /start`.
        current_time: Optional timestamp override mainly used for tests.

    Returns:
        Conversation identifier formatted as `user_id_yyyymmdd`.
    """

    resolved_time = current_time or datetime.now(UTC).astimezone()

    if resolved_time.tzinfo is None:
        resolved_time = resolved_time.replace(tzinfo=UTC).astimezone()
    else:
        resolved_time = resolved_time.astimezone()

    return f"{user_id}_{resolved_time.strftime('%Y%m%d')}"


@log_execution
def _build_new_conversation(conversation_id: str, customer_id: str) -> Conversation:
    """
    Build a new runtime conversation with default internal values.

    Args:
        conversation_id: Conversation identifier received by the API.
        customer_id: Customer identifier extracted from the conversation id.

    Returns:
        A newly initialized Conversation object.
    """

    logger.info(
        "Building new conversation conversation_id=%s customer_id=%s",
        conversation_id,
        customer_id,
    )
    return Conversation(
        conversation_id=conversation_id,
        status=ConversationStatus.ACTIVE,
        current_step="start",
        general_workflow=None,
        workflow=None,
        flow_version=None,
        flow_answers={},
        captured_data={},
        user_id=customer_id or DEFAULT_USER_ID,
    )


@log_execution
def _extract_given_names(
    customer_name: str,
    first_last_name: str,
    second_last_name: str,
) -> str:
    """Return only the given names (nombres de pila) in Title Case.

    Removes the trailing surname tokens (``first_last_name`` and
    ``second_last_name``) from ``customer_name``. Example:
    "NELSON DE JESUS GONZALEZ HOYOS" - {GONZALEZ, HOYOS} -> "Nelson De Jesus".
    Returns "" when no given names can be isolated (e.g. legal entities).
    """

    full_name = (customer_name or "").strip()
    if not full_name:
        return ""

    surname_tokens = {
        token.upper()
        for surname in (first_last_name, second_last_name)
        for token in (surname or "").split()
    }

    tokens = full_name.split()
    end = len(tokens)
    while end > 0 and tokens[end - 1].upper() in surname_tokens:
        end -= 1

    given_tokens = tokens[:end]
    if not given_tokens:
        return ""

    return " ".join(token.capitalize() for token in given_tokens)


@log_execution
async def _resolve_customer_given_name(customer_id: str) -> str:
    """Resolve the customer given names from PostgreSQL via co_pqrs_back_data.

    Reads the real source (``ada_info_detail``), never a CSV. Best-effort and
    low-latency: returns "" when back_data is not configured or unreachable so
    the greeting falls back to the no-name template without blocking /start.
    """

    base_url = load_back_data_service_url()
    if not base_url:
        return ""

    return await fetch_customer_given_name(
        base_url=base_url,
        customer_id=customer_id,
    )


@log_execution
async def _build_start_greeting(customer_id: str) -> str:
    """Build the greeting for POST /start using the customer name from Postgres."""

    given_name = await _resolve_customer_given_name(customer_id)
    if given_name:
        return _GENERAL_MESSAGES.start_greeting_template.format(
            customer_name=given_name,
        )
    return _GENERAL_MESSAGES.start_greeting_template_no_name


@log_execution
def _accumulate_token_usage(target: TokenUsage, source: TokenUsage) -> None:
    """
    Add token usage from one model invocation into the current turn aggregate.

    Args:
        target: Aggregate usage object for the current turn.
        source: Usage reported by a single model invocation.
    """

    logger.info(
        "Accumulating token usage input=%s output=%s total=%s",
        source.input_tokens,
        source.output_tokens,
        source.total_tokens,
    )
    target.input_tokens += source.input_tokens
    target.output_tokens += source.output_tokens
    target.total_tokens += source.total_tokens


# Frases de CASO sobre centrales de riesgo. Se usan como red de seguridad
# determinística: si el LLM no rutea (no-match) pero el mensaje es claramente un
# caso de centrales, se rescata al workflow centrales_de_riesgo (que muestra el
# menú de 3 opciones). Se comparan sobre texto normalizado (sin acentos, minúsculas).
#
# ACOTE MINIMO (2026-08): el gate SOLO dispara cuando el mensaje menciona
# explicitamente "centrales" o una central de riesgo por nombre (datacredito,
# transunion, cifin). Se quitaron términos genéricos como "reportado",
# "me reportaron" o "reporte negativo" porque sobre-capturaban casos que NO son
# centrales (p.ej. "me reportaron los movimientos de mi compra como fraudulentos",
# bloqueo/congelamiento de cuenta). Esos casos ya los rutea bien el LLM; si el LLM
# no matchea, es preferible que vayan al formulario/aclaracion que forzarlos a
# centrales por una palabra suelta.
_CENTRALES_CASE_KEYWORDS: tuple[str, ...] = (
    "centrales",   # cubre "centrales de riesgo", "reporte/embargo en centrales", "reportado en centrales"
    "datacredito",
    "transunion",
    "cifin",
)


def _looks_like_centrales_case(value: str | None) -> bool:
    """Whether the message looks like a centrales-de-riesgo CASE (not conceptual).

    Used only as a fallback when the LLM router returns no confident match, to
    steer the user to the centrales menu instead of the generic no-match reply.
    """

    normalized = _normalize_text(value)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _CENTRALES_CASE_KEYWORDS)


@log_execution
def _normalize_text(value: str | None) -> str:
    """
    Normalize text values used to compare workflow groups safely.

    Args:
        value: Raw text value that may contain casing differences or accents.

    Returns:
        A normalized lowercase string without diacritics.
    """

    if not value:
        return ""

    normalized_value = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(
        character
        for character in normalized_value
        if not unicodedata.combining(character)
    )


@log_execution
def _has_pending_workflow_suggestion(conversation: Conversation) -> bool:
    """Return whether the conversation is awaiting start-phase confirmation."""

    return conversation.captured_data.get(
        _START_ROUTING_STATE_KEY
    ) == _START_ROUTING_PENDING_STATE and bool(
        conversation.captured_data.get(_START_ROUTING_WORKFLOW_KEY)
    )


@log_execution
def _has_pending_repeat_flow_warning(conversation: Conversation) -> bool:
    """Return whether the conversation is awaiting a repeat-flow decision."""

    return conversation.captured_data.get(
        _REPEAT_FLOW_WARNING_STATE_KEY
    ) == _REPEAT_FLOW_PENDING_STATE and bool(
        conversation.captured_data.get(_REPEAT_FLOW_WORKFLOW_KEY)
    )


@log_execution
def _get_pending_workflow_suggestion(
    conversation: Conversation,
) -> tuple[str | None, str, str, str | None]:
    """Return the pending workflow suggestion stored during the start phase."""

    return (
        conversation.captured_data.get(_START_ROUTING_WORKFLOW_KEY),
        conversation.captured_data.get(_START_ROUTING_CONFIDENCE_KEY, "medium"),
        conversation.captured_data.get(_START_ROUTING_RATIONALE_KEY, ""),
        conversation.captured_data.get(_START_ROUTING_ENTRY_HINT_KEY) or None,
    )


@log_execution
def _get_pending_repeat_flow_warning(
    conversation: Conversation,
) -> tuple[str | None, str | None]:
    """Return the flow identifier and label stored for the repeat-flow warning."""

    return (
        conversation.captured_data.get(_REPEAT_FLOW_WORKFLOW_KEY),
        conversation.captured_data.get(_REPEAT_FLOW_LABEL_KEY),
    )


@log_execution
def _set_pending_workflow_suggestion(
    conversation: Conversation,
    *,
    workflow: str,
    confidence: str,
    rationale: str,
    entry_hint: str | None = None,
) -> None:
    """Persist the pending workflow suggestion until the user confirms it."""

    conversation.captured_data[_START_ROUTING_STATE_KEY] = _START_ROUTING_PENDING_STATE
    conversation.captured_data[_START_ROUTING_WORKFLOW_KEY] = workflow
    conversation.captured_data[_START_ROUTING_CONFIDENCE_KEY] = confidence
    conversation.captured_data[_START_ROUTING_RATIONALE_KEY] = rationale
    if entry_hint:
        conversation.captured_data[_START_ROUTING_ENTRY_HINT_KEY] = entry_hint
    conversation.current_step = "start.confirmation"
    conversation.status = ConversationStatus.ACTIVE


@log_execution
def _set_pending_repeat_flow_warning(
    conversation: Conversation,
    *,
    workflow: str,
    last_flow_label: str,
) -> None:
    """Persist the repeat-flow warning until the user chooses a different request."""

    conversation.captured_data[_REPEAT_FLOW_WARNING_STATE_KEY] = (
        _REPEAT_FLOW_PENDING_STATE
    )
    conversation.captured_data[_REPEAT_FLOW_WORKFLOW_KEY] = workflow
    conversation.captured_data[_REPEAT_FLOW_LABEL_KEY] = last_flow_label
    conversation.current_step = "start.confirmation"
    conversation.status = ConversationStatus.ACTIVE


@log_execution
def _clear_pending_workflow_suggestion(conversation: Conversation) -> None:
    """Remove any pending workflow-routing suggestion from the conversation."""

    for key in (
        _START_ROUTING_STATE_KEY,
        _START_ROUTING_WORKFLOW_KEY,
        _START_ROUTING_CONFIDENCE_KEY,
        _START_ROUTING_RATIONALE_KEY,
        _START_ROUTING_ENTRY_HINT_KEY,
    ):
        conversation.captured_data.pop(key, None)


@log_execution
def _clear_pending_repeat_flow_warning(conversation: Conversation) -> None:
    """Remove any repeat-flow warning state from the conversation."""

    for key in (
        _REPEAT_FLOW_WARNING_STATE_KEY,
        _REPEAT_FLOW_WORKFLOW_KEY,
        _REPEAT_FLOW_LABEL_KEY,
    ):
        conversation.captured_data.pop(key, None)


@log_execution
async def _handle_capped_category(
    *,
    conversation: Conversation,
    control_store: ControlTableStore,
    workflow_engine: WorkflowEngine,
    client_id: str,
    record: dict | None,
    category: str,
    workflow: str,
    fallback_label: str,
) -> str:
    """Handle a hit on the per-category daily cap.

    Layer B: if the daily re-check budget is exhausted, return the formal
    message and close the conversation; otherwise increment the re-check
    counter and show the repeat-flow warning referencing the last consulta
    of that category.
    """

    # UX: al superar el cap por categoria se MUESTRA el warning (SI/NO) y se
    # repite indefinidamente hasta que el usuario responda "No, es todo".
    # No hay tope de rechecks ni bloqueo del dia.
    try:
        await control_store.record_recheck(client_id, category)
    except Exception:
        logger.exception(
            "Failed to record repeat-flow recheck conversation_id=%s client_id=%s",
            conversation.conversation_id,
            client_id,
        )

    last_label = (
        control_store.get_category_last_flow_label(record, category) or fallback_label
    )
    _set_pending_repeat_flow_warning(
        conversation,
        workflow=workflow,
        last_flow_label=last_label,
    )
    logger.info(
        "Category cap reached; showing repeat-flow warning conversation_id=%s client_id=%s category=%s last_label=%s",
        conversation.conversation_id,
        client_id,
        category,
        last_label,
    )
    _emit_event(
        "conversation.cap_reached",
        _build_cap_reached_event(
            conversation,
            limit_key=category,
            limit_label=last_label,
            limit_scope="case",
        ),
    )
    return _GENERAL_MESSAGES.repeated_flow_warning_template.format(
        last_flow_label=last_label,
    )


@log_execution
async def _maybe_handle_category_cap(
    *,
    conversation: Conversation,
    control_store: ControlTableStore | None,
    workflow_engine: WorkflowEngine,
    workflow: str,
) -> str | None:
    """Return a cap message when the per-category daily limit is reached.

    Returns ``None`` (proceed to start the workflow) when there is no control
    store, the cap is not reached, or the control table is unavailable
    (fail-open so a transient issue never blocks a legitimate customer).
    """

    if control_store is None:
        return None

    # Centrales de riesgo is capped per SUB-FLOW at step 1.4.1 (its 3 situations
    # each get their own 3/day), so its generic start-time cap is skipped here.
    if workflow == _CENTRALES_WORKFLOW:
        return None

    client_id = conversation.user_id or _extract_customer_id(
        conversation.conversation_id
    )

    try:
        record = await control_store.get_record(client_id)
        category = workflow_engine.get_limit_key(workflow)
        count = control_store.get_category_day_count(record, category)
        max_category = load_max_daily_category_interactions()
        logger.info(
            "Category cap check conversation_id=%s client_id=%s category=%s count=%s max=%s",
            conversation.conversation_id,
            client_id,
            category,
            count,
            max_category,
        )

        if count < max_category:
            return None

        _, selector_option = workflow_engine._find_workflow_selector_option(workflow)
        return await _handle_capped_category(
            conversation=conversation,
            control_store=control_store,
            workflow_engine=workflow_engine,
            client_id=client_id,
            record=record,
            category=category,
            workflow=workflow,
            fallback_label=selector_option.label,
        )
    except Exception:
        logger.exception(
            "Category cap check failed; allowing start conversation_id=%s workflow=%s",
            conversation.conversation_id,
            workflow,
        )
        return None


@log_execution
async def _maybe_handle_centrales_subflow_cap(
    *,
    conversation: Conversation,
    control_store: ControlTableStore | None,
    subflow_key: str,
) -> str | None:
    """Apply the per-SUB-FLOW daily cap for centrales de riesgo.

    Called right after step 1.4.1 resolves one of the 3 situations. Counts
    with the key ``centrales_de_riesgo:<subflow_key>`` so each situation has
    its own 3/day budget (there is NO global cap for centrales as a whole).

    - Below the cap: records the interaction and returns ``None`` (proceed).
    - At/over the cap: resets the conversation to the start phase and arms the
      existing repeat-flow warning (Sí/No), returning its message. Only THIS
      sub-flow is blocked; the other two remain available.

    Fail-open: any control-table error allows the interaction.
    """

    if control_store is None or not subflow_key:
        return None

    client_id = conversation.user_id or _extract_customer_id(
        conversation.conversation_id
    )
    subflow_label = _CENTRALES_SUBFLOW_LABELS.get(
        subflow_key, "un tema de centrales de riesgo"
    )
    limit_key = f"{_CENTRALES_WORKFLOW}:{subflow_key}"

    try:
        record = await control_store.get_record(client_id)
        count = control_store.get_category_day_count(record, limit_key)
        max_category = load_max_daily_category_interactions()
        logger.info(
            "Centrales subflow cap check conversation_id=%s client_id=%s key=%s count=%s max=%s",
            conversation.conversation_id,
            client_id,
            limit_key,
            count,
            max_category,
        )

        if count < max_category:
            await _record_category_interaction_safely(
                control_store=control_store,
                client_id=client_id,
                category=limit_key,
                workflow_label=subflow_label,
                conversation_id=conversation.conversation_id,
            )
            return None

        # Capped: reset to the start phase and reuse the repeat-flow warning
        # Sí/No machinery (handled in _resolve_start_phase on the next turn).
        _emit_event(
            "conversation.cap_reached",
            _build_cap_reached_event(
                conversation,
                limit_key=limit_key,
                limit_label=subflow_label,
                limit_scope="centrales_subflow",
            ),
        )
        _reset_conversation_for_reroute(conversation)
        _set_pending_repeat_flow_warning(
            conversation,
            workflow=_CENTRALES_WORKFLOW,
            last_flow_label=subflow_label,
        )
        logger.info(
            "Centrales subflow cap reached; showing repeat-flow warning "
            "conversation_id=%s client_id=%s key=%s",
            conversation.conversation_id,
            client_id,
            limit_key,
        )
        return _GENERAL_MESSAGES.repeated_flow_warning_template.format(
            last_flow_label=subflow_label,
        )
    except Exception:
        logger.exception(
            "Centrales subflow cap check failed; allowing conversation_id=%s key=%s",
            conversation.conversation_id,
            limit_key,
        )
        return None


@log_execution
def _trace_control_table_write_failure(
    *,
    conversation_id: str,
    client_id: str,
    momento: str,
    error: BaseException,
    workflow_id: str | None = None,
    category: str | None = None,
) -> None:
    """Emite traza cuando FALLA una escritura del agente en la control-table.

    Por que existe (03/09/2026): estas escrituras se capturan con
    ``logger.exception`` y el rastro quedaba SOLO en el log del contenedor. El
    1 de septiembre OpenSearch empezo a rechazarlas con

        400 illegal_argument_exception: Limit of total fields [1000] has been exceeded

    porque el indice se quedo sin sitio en su esquema (la tabla usa fechas como
    nombre de campo, asi que cada dia anade rutas nuevas). El agente no pudo
    crear el bucket del mes en curso, el sondeo no encontraba nada y el cliente
    recibia "En este momento no puedo validar el estado de tus productos".

    Tardo DOS DIAS en verse justamente porque no habia traza: solo se veia el
    sintoma final. Con esto el motivo llega al bucket de auditoria.

    Sigue siendo fail-open: se traza y el turno continua. Un fallo del contador
    de control no puede tumbar la conversacion del cliente.
    """

    detalle: dict[str, Any] = {"momento": momento}
    if workflow_id:
        detalle["workflow_id"] = workflow_id
    if category:
        detalle["category"] = category

    # Si es un error HTTP, el CUERPO dice el motivo real. Sin el hay que
    # deducirlo, que es exactamente lo que salio mal esta semana.
    respuesta = getattr(error, "response", None)
    if respuesta is not None:
        try:
            detalle["status_code"] = respuesta.status_code
            detalle["body"] = str(respuesta.text)[:600]
        except Exception:  # pragma: no cover - la traza nunca rompe el turno
            pass

    try:
        schedule_trace_event(
            event_type="opensearch",
            operation="control_table_write",
            outcome="error",
            conversation_id=conversation_id,
            customer_id=client_id,
            target="client-control-table",
            status_code=detalle.get("status_code"),
            request_summary=detalle,
            error_type=type(error).__name__,
            error_message=str(error)[:300],
            tags=["opensearch", "control_table"],
        )
    except Exception:  # pragma: no cover - la traza nunca rompe el turno
        logger.exception(
            "No se pudo emitir la traza del fallo de control-table conversation_id=%s",
            conversation_id,
        )


async def _record_category_interaction_safely(
    *,
    control_store: ControlTableStore,
    client_id: str,
    category: str,
    workflow_label: str,
    conversation_id: str,
) -> None:
    """Increment the per-category daily counter, swallowing persistence errors."""

    try:
        await control_store.record_category_interaction(
            client_id=client_id,
            category=category,
            workflow_label=workflow_label,
        )
    except Exception as exc:
        logger.exception(
            "Failed to record category interaction conversation_id=%s client_id=%s category=%s",
            conversation_id,
            client_id,
            category,
        )
        _trace_control_table_write_failure(
            conversation_id=conversation_id,
            client_id=client_id,
            momento="record_category_interaction",
            error=exc,
            category=category,
        )


@log_execution
def _is_affirmative(value: str) -> bool:
    """Return whether a normalized user input confirms the pending workflow."""

    normalized_value = _normalize_text(value)
    return (
        normalized_value
        in {
            "si",
            "s",
            "1",
            "continuar",
            "continua",
            "continue",
            "correcto",
            "de acuerdo",
            "dale",
            "ok",
            "okay",
            "yes",
        }
        or normalized_value.startswith("si ")
        or normalized_value.startswith("continuar ")
    )


@log_execution
def _is_negative(value: str) -> bool:
    """Return whether a normalized user input rejects the pending workflow."""

    normalized_value = _normalize_text(value)
    return (
        normalized_value
        in {
            "no",
            "2",
            "salir",
            "cancelar",
            "incorrecto",
        }
        or normalized_value.startswith("no ")
        or normalized_value.startswith("salir ")
    )


@log_execution
def _extract_rejection_reformulation(value: str) -> str | None:
    """
    Extract a reformulated request when the user rejects the suggestion and
    immediately provides a new description.

    Examples:
        - "no, necesito extractos" -> "necesito extractos"
        - "incorrecto, quiero 4x1000" -> "quiero 4x1000"
    """

    normalized_value = _normalize_text(value)

    if normalized_value in {"no", "2", "incorrecto", "salir", "cancelar"}:
        return None

    for pattern in (
        r"^\s*no\b[\s,.:;!?\-]*(?P<rest>.+)$",
        r"^\s*incorrecto\b[\s,.:;!?\-]*(?P<rest>.+)$",
        r"^\s*salir\b[\s,.:;!?\-]*(?P<rest>.+)$",
    ):
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if not match:
            continue

        reformulated_request = match.group("rest").strip()
        if reformulated_request:
            return reformulated_request

    return None


@log_execution
def _build_rejected_workflow_message(workflow_engine: WorkflowEngine) -> str:
    """Build the message shown when the user rejects the routed workflow."""

    return (
        "Entendido. Salimos de ese flujo por ahora.\n\n"
        f"{workflow_engine.build_routing_clarification_message()}"
    )


@log_execution
def _resolve_routing_entry_hint(
    *,
    workflow: str,
    user_content: str,
    rationale: str = "",
) -> str | None:
    """Resolve a safe shortcut hint for workflows with known direct-entry branches.

    IMPORTANTE: `rationale` se usa solo como SENAL para decidir el sub-flujo, no
    se muestra al cliente. Usar la salida del LLM para decidir es distinto de
    mostrar su texto: lo primero esta bien, lo segundo no.
    """

    normalized_workflow = _normalize_text(workflow)
    normalized_signal_context = " ".join(
        fragment
        for fragment in (
            _normalize_text(user_content),
            _normalize_text(rationale),
        )
        if fragment
    )

    if normalized_workflow == "centrales_de_riesgo":
        # ACOTE MINIMO (2026-08): solo auto-entrar al sub-flujo de centrales cuando
        # el mensaje/rationale menciona EXPLICITAMENTE "centrales" o una central por
        # nombre (datacredito/transunion/cifin). Cubre "reporte en centrales",
        # "embargo en centrales", "aparezco reportado en datacredito". Terminos
        # sueltos como "embargo" o "reporte" NO auto-entran: se muestra el menu de
        # centrales para que el usuario elija y no capturar mal el sub-flujo.
        centrales_anchors = ("centrales", "datacredito", "transunion", "cifin")
        if any(anchor in normalized_signal_context for anchor in centrales_anchors):
            return "centrales_de_riesgo"

    return None


@log_execution
def _apply_current_step_action_if_needed(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
    assistant_content: str,
) -> str:
    """Execute and render any technical action attached to the current step."""

    current_step_data = workflow_engine.get_current_step(conversation)

    if current_step_data is None:
        return assistant_content

    _, current_step = current_step_data
    execute_workflow_action(
        conversation=conversation,
        step=current_step,
    )

    if current_step.action:
        rendered_prompt = workflow_engine.render_current_step_prompt(conversation)
        if rendered_prompt:
            return rendered_prompt

    return assistant_content


@log_execution
async def _apply_smart_route_if_needed(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    assistant_content: str,
    turn_usage: TokenUsage,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
    control_store: ControlTableStore | None = None,
) -> str:
    """
    Auto-advance a smart-route step when the conversation entry hint provides
    enough context to determine the correct option without asking the user.
    Falls back to showing the menu when the classification is uncertain.
    """

    current_step_data = workflow_engine.get_current_step(conversation)
    if current_step_data is None:
        return assistant_content

    step_id, step = current_step_data
    if not step.smart_route or step.input_type != "choice" or not step.options:
        return assistant_content

    entry_hint = conversation.captured_data.get(_WORKFLOW_ENTRY_HINT_KEY)
    if not entry_hint:
        return assistant_content

    logger.info(
        "Attempting smart route conversation_id=%s step_id=%s entry_hint_length=%s",
        conversation.conversation_id,
        step_id,
        len(entry_hint),
    )
    try:
        (
            classification,
            classification_usage,
        ) = await strands_agent.classify_step_option_with_usage(
            conversation=conversation,
            step_id=step_id,
            step=step,
            entry_hint=entry_hint,
        )
        _accumulate_token_usage(turn_usage, classification_usage)

        if (
            classification.is_match
            and classification.option_key
            and classification.confidence in {"high", "medium"}
        ):
            logger.info(
                "Smart route matched conversation_id=%s step_id=%s option_key=%s confidence=%s",
                conversation.conversation_id,
                step_id,
                classification.option_key,
                classification.confidence,
            )
            auto_content = workflow_engine.generate_response(
                conversation, classification.option_key
            )
            if back_data_service_url:
                await _prefetch_back_data_if_needed(
                    conversation=conversation,
                    back_data_service_url=back_data_service_url,
                    control_store=control_store,
                )
            if trx_service_url or back_data_service_url:
                await _prefetch_trx_data_if_needed(
                    conversation=conversation,
                    trx_service_url=trx_service_url,
                    back_data_service_url=back_data_service_url,
                    control_store=control_store,
                )
            return _apply_current_step_action_if_needed(
                conversation=conversation,
                workflow_engine=workflow_engine,
                assistant_content=auto_content,
            )

        logger.info(
            "Smart route no confident match conversation_id=%s step_id=%s is_match=%s confidence=%s",
            conversation.conversation_id,
            step_id,
            classification.is_match,
            classification.confidence,
        )
    except Exception:
        logger.exception(
            "Smart route classification failed conversation_id=%s step_id=%s falling back to menu",
            conversation.conversation_id,
            step_id,
        )

    return assistant_content


@log_execution
def _matches_current_choice_option(
    *,
    workflow_engine: WorkflowEngine,
    conversation: Conversation,
    user_content: str,
) -> bool:
    """Return whether the user content matches one option of the current choice step."""

    current_step_data = workflow_engine.get_current_step(conversation)

    if current_step_data is None:
        return False

    _, current_step = current_step_data

    if current_step.input_type != "choice" or not current_step.options:
        return False

    normalized_input = _normalize_text(user_content)

    for index, option in enumerate(current_step.options, start=1):
        candidates = {
            _normalize_text(option.key),
            _normalize_text(option.label),
            str(index),
        }

        if normalized_input in candidates:
            return True

    return False


@log_execution
def _looks_like_new_workflow_request(user_content: str) -> bool:
    """
    Heuristically detect whether a message looks like a fresh natural-language
    request instead of a workflow option selection.
    """

    normalized_input = _normalize_text(user_content)

    if not normalized_input or normalized_input.isdigit():
        return False

    if normalized_input in {
        "si",
        "s",
        "no",
        "ok",
        "okay",
        "yes",
        "continuar",
        "salir",
    }:
        return False

    if " " not in normalized_input:
        return False

    return len(normalized_input) >= 12 and any(
        character.isalpha() for character in normalized_input
    )


@log_execution
def _should_reroute_from_active_workflow(
    *,
    conversation: Conversation,
    workflow_engine: WorkflowEngine,
    user_content: str,
) -> bool:
    """
    Detect when a user sends a new free-text request while the conversation is
    still parked at the first choice step of another workflow.
    """

    if conversation.workflow is None or conversation.flow_answers:
        return False

    workflow_definition = workflow_engine.catalog.flows.get(conversation.workflow)

    if workflow_definition is None:
        return False

    if conversation.current_step != workflow_definition.start_step:
        return False

    current_step_data = workflow_engine.get_current_step(conversation)

    if current_step_data is None:
        return False

    _, current_step = current_step_data

    if current_step.input_type != "choice" or not current_step.options:
        return False

    if _matches_current_choice_option(
        workflow_engine=workflow_engine,
        conversation=conversation,
        user_content=user_content,
    ):
        return False

    return _looks_like_new_workflow_request(user_content)


@log_execution
def _reset_conversation_for_reroute(conversation: Conversation) -> None:
    """Clear workflow state so the conversation can be classified again."""

    conversation.general_workflow = None
    conversation.workflow = None
    conversation.flow_version = None
    conversation.current_step = "start"
    conversation.status = ConversationStatus.ACTIVE
    conversation.flow_answers.clear()
    # The analytics source mark outlives every reroute: the conversation was
    # opened by the benchmark and stays a benchmark conversation until closed.
    event_source = conversation.captured_data.get(_EVENT_SOURCE_KEY)
    conversation.captured_data.clear()
    if event_source is not None:
        conversation.captured_data[_EVENT_SOURCE_KEY] = event_source


# Vocabulario de saludo y cortesia (normalizado: minusculas, sin acentos) usado por
# el guard deterministico para re-saludar sin gastar una llamada al LLM de routing.
_GREETING_WORDS: frozenset[str] = frozenset(
    {
        "hola",
        "holaa",
        "holaaa",
        "ola",
        "hello",
        "hi",
        "hey",
        "ey",
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
        "va",
        "todo",
        "bien",
        "gracias",
        "muchas",
        "mil",
        "blue",
        "asistente",
        "bot",
        # Cortesia/saludos adicionales. OJO: el texto se normaliza sin acentos,
        # por eso las enes van sin tilde (senor, senora) y se cubren conjugaciones
        # y elongaciones frecuentes ("buena tarde", "como vas", "holaaa").
        "buena",
        "vas",
        "andas",
        "andan",
        "estes",
        "estan",
        "estamos",
        "pases",
        "senor",
        "senora",
        "senores",
        "senorita",
        "estimado",
        "estimada",
        "estimados",
        "cordialmente",
        "Holi",
        "Holiwis",
    }
)

# Colapsa repeticiones de un mismo caracter para tolerar elongaciones
# ("holaaaa" -> "hola", "vasss" -> "vas", "buenass" -> "buenas"). Solo se usa
# para COMPARAR contra el vocabulario de saludo; no altera el texto del usuario.
_GREETING_ELONGATION = re.compile(r"(.)\1+")
# Relleno de cortesia: solo habilita el saludo cuando TODOS los tokens son de
# saludo, asi que no captura mensajes con contenido real.
_GREETING_WORDS = _GREETING_WORDS | frozenset({"mas", "muy", "tan", "pues", "hoka"})


def _collapse_repeats(token: str) -> str:
    return _GREETING_ELONGATION.sub(r"\1", token)


# Pasos "neutros" donde un saludo puro nunca es una respuesta valida del flujo
# (inicio, confirmacion de propuesta o encuesta de satisfaccion). En estos puntos
# un saludo debe re-saludar, no caer al formulario ni consumirse como respuesta.
# NO se incluyen pasos de captura de datos/opciones del workflow.
_NEUTRAL_GREETING_STEPS: frozenset[str] = frozenset(
    {
        "start",
        "start.confirmation",
        "satisfaction_check",
        "satisfaction_check_faq",
    }
)


def _is_greeting_safe_point(conversation: Conversation) -> bool:
    """Whether a pure greeting can be safely intercepted at the current step."""

    return (
        conversation.workflow is None
        or conversation.current_step in _NEUTRAL_GREETING_STEPS
    )


# --- Tolerancia de la captacion de intencion (fix de ruteo, ago-2026) ---------
# Era vocabulario CERRADO: un typo al saludar ("Buneas tardes") terminaba en el
# formulario de PQR, y frases equivalentes recibian trato distinto ("radicar una
# pqr" pedia el motivo; "realizar una pqr" no). Esta capa es la RED DE SEGURIDAD
# del router LLM; el objetivo es que no falle por ortografia.
_GREETING_ABBREVIATIONS: dict[str, str] = {
    "bns": "buenas", "bnas": "buenas", "bnos": "buenos",
    "bn": "buen", "bss": "buenas", "hla": "hola", "qtal": "que",
    # Typos observados en QA. Lista EXPLICITA a proposito: es preferible a bajar
    # el umbral de similitud, que convertia contenido en saludo (ver abajo).
    "hoka": "hola", "hoal": "hola", "holq": "hola", "ola": "hola",
    "bule": "blue", "bule": "blue", "blu": "blue", "bleu": "blue", "bluee": "blue",
}
_FUZZY_MIN_LEN = 4
_FUZZY_CUTOFF = 0.82


def _is_content_token(token: str) -> bool:
    """Whether the token is a content word that must never be fuzzy-matched.

    Sin esta guarda, la similitud convertia palabras reales en saludo/relleno:
    "queja"~"que" (0.75), "saldo"~"saludo" (0.91), "cuenta"~"buena" (0.73),
    "estafa"~"esta" (0.80). Un cliente que escribia "saldo" recibia un saludo.
    """

    return has_banking_signals(token) or token in _PQRS_OBJECT_WORDS


def _token_in_vocab(
    token: str, vocab: frozenset[str], *, cutoff: float = _FUZZY_CUTOFF
) -> bool:
    """Pertenencia a un vocabulario tolerando typos y abreviaturas.

    Orden: exacto -> repeticiones colapsadas -> abreviatura -> similitud alta.
    El umbral es alto y solo aplica a tokens de >= 4 letras para no convertir
    palabras de contenido en saludos/relleno ("fraude", "manejo" NO pasan).
    """

    if token in vocab:
        return True
    collapsed = _collapse_repeats(token)
    if collapsed in vocab:
        return True
    expanded = _GREETING_ABBREVIATIONS.get(token) or _GREETING_ABBREVIATIONS.get(collapsed)
    if expanded and expanded in vocab:
        return True
    # La similitud NUNCA se aplica a palabras de contenido: "saldo" no es
    # "saludo" y "queja" no es "que".
    if len(token) >= _FUZZY_MIN_LEN and not _is_content_token(token):
        import difflib

        candidates = [w for w in vocab if abs(len(w) - len(token)) <= 2]
        if difflib.get_close_matches(token, candidates, n=1, cutoff=cutoff):
            return True
    return False


@log_execution
def _is_unintelligible(value: str) -> bool:
    """Whether the message carries no interpretable content at all.

    Criterio deliberadamente ESTRECHO: el mensaje no tiene NI UNA letra ("9+",
    "...", "??", ":)"). Si hay aunque sea una letra, se deja pasar al router:
    "4x1" es una abreviatura real del 4x1000 y "cdt" es un producto.

    La longitud NO se usa como criterio de contenido (mensajes cortos si
    significan: "cdt", "pqr", "no", "1"). Solo se usa para ser mas conservador:
    una entrada de un solo caracter nunca se atrapa aqui.
    """

    normalized_value = _normalize_text(value)
    if not normalized_value or len(normalized_value.strip()) < 2:
        # La entrada vacia la maneja el guardrail de input, no este gate.
        return False
    compact = normalized_value.replace(" ", "")
    # Terminos reales que se escriben con cifras y casi no tienen letras.
    if compact in _ALPHANUM_KNOWN_TERMS:
        return False
    # Cualquier senal bancaria (producto, monto, PQRS) descarta el gate.
    if has_banking_signals(normalized_value):
        return False
    return not re.search(r"[a-z]", normalized_value)


# Terminos del negocio que se escriben con cifras (el flujo del impuesto).
_ALPHANUM_KNOWN_TERMS: frozenset[str] = frozenset(
    {"4x1000", "4x100", "4xmil", "4por1000", "2x1000"}
)


@log_execution
def _is_pure_greeting(value: str) -> bool:
    """
    Return whether the message is only a greeting/courtesy with no concrete request.

    The check is deterministic (no LLM): it normalizes the text, extracts word
    tokens and returns True only when every token belongs to the greeting
    vocabulary. A message like "hola necesito mi paz y salvo" is NOT a pure
    greeting because it carries workflow intent.
    """

    normalized_value = _normalize_text(value)
    if not normalized_value:
        return False

    tokens = re.findall(r"[a-z]+", normalized_value)
    if not tokens:
        return False

    return all(_token_in_vocab(token, _GREETING_WORDS) for token in tokens)


@log_execution
def _build_greeting_response(workflow_engine: WorkflowEngine) -> str:
    """Build a warm welcome that re-presents the available categories (no LLM)."""

    welcome = workflow_engine.catalog.welcome
    categories = ", ".join(group.label for group in welcome.groups)
    base_message = welcome.message.strip()

    return (
        f"{base_message}\n\n"
        f"Puedo ayudarte con temas de: {categories}.\n"
        "Cuentame que necesitas. Por ejemplo: \"necesito mi paz y salvo\", "
        "\"por que me cobran cuota de manejo\" o "
        "\"no reconozco un reporte en centrales de riesgo\"."
    )


# --- Desambiguacion de meta-peticiones "peladas" de PQR -----------------------
# Cuando el usuario solo pide "radicar/poner/montar una PQR" o "formulario PQR"
# SIN dar el motivo, el router no puede mapear a un flujo especifico y cae al
# formulario generico. En vez de eso pedimos el causal de forma profesional
# (dos pasos: mensaje + boton Continuar, luego captura del motivo) y re-ruteamos.
#
# IMPORTANTE (evita el bug de centrales): este detector NO redirige a ningun
# workflow ni corre antes del router. Solo actua sobre el fallback no-match y
# SOLO si el mensaje esta "pelado" (no queda ningun token con contenido tras
# quitar la frase de radicacion + saludos/relleno). Ante cualquier duda -> False
# -> ruteo normal (fail-safe: nunca secuestra la intencion del cliente).

# Sustantivos que senalan una PQR/queja/formulario. NO se incluye "solicitud"
# (demasiado generico: "solicitud de extractos", "solicitud de celular", etc.).
_PQRS_OBJECT_WORDS: frozenset[str] = frozenset(
    {
        "pqr",
        "pqrs",
        "pqrsf",
        "queja",
        "quejas",
        "reclamo",
        "reclamos",
        "reclamacion",
        "reclamaciones",
        "formulario",
        "formularios",
        "peticion",
        "peticiones",
    }
)

# Verbos de radicacion frecuentes (conjugaciones y typos observados en trazas).
_PQRS_FILING_VERBS: frozenset[str] = frozenset(
    {
        "radicar",
        "radico",
        "radicas",
        "radica",
        "radique",
        "radicarla",
        "radicarlo",
        "poner",
        "pon",
        "ponerla",
        "ponerlo",
        "montar",
        "monta",
        "momar",  # typo observado ("momar una PQR")
        "colocar",
        "coloco",
        "hacer",
        "hago",
        "haga",
        "elevar",
        "presentar",
        "presento",
        "interponer",
        "instaurar",
        "diligenciar",
        "llenar",
        "subir",
        "subo",
        "generar",
        "crear",
        "formular",
        "tramitar",
        "abrir",
    }
)

# Relleno permitido: determinantes, conectores, verbos de intencion y palabras
# de cortesia/pregunta. Si tras quitar estos (mas saludos y objeto/verbo) queda
# algun token con contenido, hay causal -> NO es pelado. Se excluyen a proposito
# verbos de "el formulario no abre/aparece/sirve" (bucket aparte, no es radicar).
_PQRS_FILLER_WORDS: frozenset[str] = frozenset(
    {
        "un",
        "una",
        "unos",
        "unas",
        "el",
        "la",
        "los",
        "las",
        "lo",
        "mi",
        "mis",
        "tu",
        "tus",
        "su",
        "sus",
        "de",
        "del",
        "al",
        "a",
        "en",
        "para",
        "por",
        "con",
        "y",
        "o",
        "u",
        "que",
        "se",
        "me",
        "te",
        "nos",
        "le",
        "quiero",
        "deseo",
        "necesito",
        "necesita",
        "necesitas",
        "nesecito",  # typo observado
        "requiero",
        "quisiera",
        "gustaria",
        "puedo",
        "puede",
        "podria",
        "ayuda",
        "ayudar",
        "ayudame",
        "ayudas",
        "favor",
        "porfavor",
        "donde",
        "como",
        "cual",
        "cuales",
        "nueva",
        "nuevo",
        "otra",
        "otro",
        "aqui",
        "aca",
        "usted",
        "ustedes",
        "ya",
        "solo",
    }
)

# Estado de la maquina de dos pasos (persistido en captured_data).
_PQRS_CLARIFY_STATE_KEY = "pqrs_clarify_state"
_PQRS_CLARIFY_AWAIT_CONTINUE = "await_continue"

# Reintento de aclaracion ante no-match.
#
# Antes, CUALQUIER mensaje que el router no mapeara caia directo al formulario
# PQRS. QA lo reporto 8 veces el mismo mes ("Bule", "9+", "Quitar bloqueo",
# "hola, puedes escribirme en paisa", ...): el cliente nunca tuvo una segunda
# oportunidad de explicarse. El router YA redacta un clarification_message para
# ese caso (ver routing_scope_prompt_suffix y WorkflowRoutingDecision) y el
# codigo lo descartaba.
#
# Las entradas sin palabras interpretables todavía reciben un único mensaje de
# aclaración. Si el router sí procesa el texto pero no encuentra un workflow
# independiente o una FAQ aplicable, se muestra el selector de Centrales.
_NO_MATCH_STREAK_KEY = "routing_no_match_streak"
_NO_MATCH_MAX_RETRIES = 1


def _reset_no_match_streak(conversation: Conversation) -> None:
    """Clear the consecutive no-match counter (per conversation, no global state)."""

    conversation.captured_data.pop(_NO_MATCH_STREAK_KEY, None)


def _no_match_streak(conversation: Conversation) -> int:
    """Consecutive no-match count for this conversation."""

    try:
        return int(conversation.captured_data.get(_NO_MATCH_STREAK_KEY) or 0)
    except (TypeError, ValueError):
        return 0


def _routing_retry_message(workflow_engine: WorkflowEngine) -> str:
    """Fixed message asking the customer to rewrite their request.

    DETERMINISTA A PROPOSITO. El LLM NO redacta este mensaje: el router entrega
    un `clarification_message` pero NO se usa, porque el agente no debe tener la
    potestad de inventar el texto que ve el cliente (se observo que respondia
    imitando el dialecto del cliente). El texto se edita en general_messages.yml
    sin necesidad de tocar codigo.
    """

    return workflow_engine.build_routing_retry_message()

_PQRS_CLARIFY_AWAIT_REASON = "await_reason"
_PQRS_REASON_KEY = "pqrs_reason"

# Mensajes (tono BBVA). El paso 1 se acompana de un boton "Continuar" (chat_router).
_PQRS_CLARIFY_INTRO_MESSAGE = (
    "En BBVA estamos para ayudarte. Para radicar tu PQR y asignarla al area que "
    "corresponde, primero necesitamos conocer el motivo de tu solicitud. Cuando "
    "estes listo, presiona Continuar para contarnoslo."
)
_PQRS_CLARIFY_REASON_MESSAGE = (
    "Por favor, describe el motivo de tu PQR con tus palabras. Con esa "
    "informacion la gestionaremos por el canal adecuado."
)


# --- Ampliacion del vocabulario de meta-peticiones (evidencia de produccion) ---
# "radicar una pqr" pedia el motivo, pero "realizar una pqr", "registrar una
# queja", "radicar un derecho de peticion" o "enviar una solicitud" caian directo
# al formulario. Es la MISMA intencion y debe recibir el mismo trato.
_PQRS_FILING_VERBS = _PQRS_FILING_VERBS | frozenset(
    {
        "registrar", "registro", "registra",
        "realizar", "realizo", "realiza",
        "enviar", "envio", "envia", "envie",
        "colocar", "coloco", "coloca",
        "instaurar", "instauro", "interponer", "interpongo",
        "elevar", "elevo", "tramitar", "tramito",
        "generar", "genero", "crear", "creo",
        "diligenciar", "diligencio", "formular", "formulo",
        # Patron POSESIVO: el cliente no dice "radicar una queja" sino que la
        # "tiene". Caso real 98909004_20260820 ("tengo una queja") que caia al
        # formulario generico en vez de preguntar el motivo.
        "tengo", "tener", "tienes", "tiene", "tenemos", "tengos",
        "hay", "existe", "seria", "es",
    }
)
_PQRS_OBJECT_WORDS = _PQRS_OBJECT_WORDS | frozenset(
    {
        "derecho", "derechos", "solicitud", "solicitudes", "radicado", "radicacion",
        "tutela", "inconformidad", "inconformidades", "molestia", "insatisfaccion",
    }
)
_PQRS_FILLER_WORDS = _PQRS_FILLER_WORDS | frozenset(
    {
        "voy", "vamos", "va", "ir", "a", "aca", "alla", "favor",
        # Adjetivos que califican la queja pero NO aportan causal: "tengo una
        # queja formal" sigue siendo una meta-peticion pelada.
        "formal", "urgente", "importante", "grave", "seria", "nueva", "nuevo",
        "otra", "otro",
    }
)


@log_execution
def _is_bare_pqrs_request(value: str) -> bool:
    """
    Return whether the message is ONLY a meta-request to file a PQR, with no
    concrete reason (e.g. "formulario pqr", "quiero radicar una pqr", "poner una
    queja").

    Deterministic and fail-safe: it references a PQR/queja/formulario object AND
    every token belongs to the filing/greeting/filler vocabulary. If ANY content
    token remains (a causal such as "por fraude", "por el bloqueo", "de mi
    cuenta"), it returns False so normal routing proceeds untouched. Elongations
    are tolerated by matching both the raw and the repeat-collapsed token.
    """

    normalized_value = _normalize_text(value)
    if not normalized_value:
        return False

    tokens = re.findall(r"[a-z]+", normalized_value)
    if not tokens:
        return False

    allowed = (
        _PQRS_OBJECT_WORDS
        | _PQRS_FILING_VERBS
        | _PQRS_FILLER_WORDS
        | _GREETING_WORDS
    )

    def _known(token: str) -> bool:
        return _token_in_vocab(token, allowed)

    # Debe referirse explicitamente a una PQR/queja/formulario.
    if not any(
        token in _PQRS_OBJECT_WORDS or _collapse_repeats(token) in _PQRS_OBJECT_WORDS
        for token in tokens
    ):
        return False

    # Pelado solo si TODOS los tokens son objeto/verbo/relleno/saludo.
    return all(_known(token) for token in tokens)


@log_execution
async def _resolve_start_phase(
    *,
    conversation: Conversation,
    user_content: str,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    control_store: ControlTableStore | None,
    turn_usage: TokenUsage,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
) -> str:
    """Route the initial user request to a workflow and handle confirmation."""

    logger.info(
        "Resolving start phase conversation_id=%s current_step=%s has_pending_suggestion=%s",
        conversation.conversation_id,
        conversation.current_step,
        _has_pending_workflow_suggestion(conversation),
    )
    conversation.general_workflow = None
    conversation.flow_version = None
    # Desenlace del ruteo del turno; se sobreescribe abajo (matched / confirmation
    # / no_match). Queda "other" en caminos de saludo o de respuesta Sí/No.
    conversation.captured_data["routing_outcome"] = "other"

    # --- Maquina de dos pasos de aclaracion de PQR "pelada" -------------------
    # Se activa SOLO por el flag en captured_data (ver el hook post-router mas
    # abajo). No llama al router para "Continuar" ni para re-preguntar el causal.
    _clarify_state = conversation.captured_data.get(_PQRS_CLARIFY_STATE_KEY)
    if _clarify_state == _PQRS_CLARIFY_AWAIT_CONTINUE:
        if _is_affirmative(user_content):
            # Oprimio "Continuar" -> pedir el causal en texto libre.
            conversation.captured_data[_PQRS_CLARIFY_STATE_KEY] = (
                _PQRS_CLARIFY_AWAIT_REASON
            )
            conversation.current_step = "start"
            conversation.status = ConversationStatus.ACTIVE
            conversation.captured_data["routing_outcome"] = "pqrs_clarify"
            return _PQRS_CLARIFY_REASON_MESSAGE
        if _is_bare_pqrs_request(user_content):
            # Sigue pelado (ni Continuar ni causal) -> volver a invitar (indefinido).
            conversation.captured_data["routing_outcome"] = "pqrs_clarify"
            return _PQRS_CLARIFY_INTRO_MESSAGE
        # Escribio el causal directamente en vez de oprimir Continuar: capturarlo
        # y dejar que el ruteo normal (mas abajo) lo procese.
        conversation.captured_data.pop(_PQRS_CLARIFY_STATE_KEY, None)
        conversation.captured_data[_PQRS_REASON_KEY] = user_content
    elif _clarify_state == _PQRS_CLARIFY_AWAIT_REASON:
        if _is_bare_pqrs_request(user_content):
            # Todavia sin causal -> volver a pedirlo (indefinido, sin rendirse).
            conversation.captured_data["routing_outcome"] = "pqrs_clarify"
            return _PQRS_CLARIFY_REASON_MESSAGE
        # Es el causal: capturarlo, limpiar el estado y re-rutear con normalidad.
        conversation.captured_data.pop(_PQRS_CLARIFY_STATE_KEY, None)
        conversation.captured_data[_PQRS_REASON_KEY] = user_content

    if _has_pending_repeat_flow_warning(conversation):
        pending_workflow, pending_flow_label = _get_pending_repeat_flow_warning(
            conversation
        )

        if pending_workflow and _is_affirmative(user_content):
            _clear_pending_repeat_flow_warning(conversation)
            # UX: "Si" siempre permite volver a escribir y re-rutear (loop
            # indefinido); solo "No, es todo" cierra la sesion.
            conversation.current_step = "start"
            conversation.status = ConversationStatus.ACTIVE
            return _GENERAL_MESSAGES.repeated_flow_continue_message

        if _is_negative(user_content):
            _clear_pending_repeat_flow_warning(conversation)
            conversation.current_step = "start"
            # The user declined -> end THIS session with the goodbye. It is not a
            # full-day block (they may come back later); the session stays CLOSED
            # so the guard answers any further message without invoking the LLM.
            conversation.status = ConversationStatus.CLOSED
            conversation.captured_data[_SESSION_LIMIT_CLOSED_KEY] = "true"
            return _GENERAL_MESSAGES.repeated_flow_decline_message

        return _GENERAL_MESSAGES.repeated_flow_warning_template.format(
            last_flow_label=pending_flow_label or pending_workflow or "ese flujo",
        )

    if _has_pending_workflow_suggestion(conversation):
        pending_workflow, _, _, pending_entry_hint = _get_pending_workflow_suggestion(
            conversation
        )

        if pending_workflow and _is_affirmative(user_content):
            _clear_pending_workflow_suggestion(conversation)

            cap_message = await _maybe_handle_category_cap(
                conversation=conversation,
                control_store=control_store,
                workflow_engine=workflow_engine,
                workflow=pending_workflow,
            )
            if cap_message is not None:
                return cap_message

            started_prompt = workflow_engine.start_workflow(
                conversation,
                pending_workflow,
                entry_hint=pending_entry_hint,
            )

            if control_store is not None:
                _entry_client_id = conversation.user_id or _extract_customer_id(
                    conversation.conversation_id
                )
                try:
                    _, _selector_option = (
                        workflow_engine._find_workflow_selector_option(pending_workflow)
                    )
                    await control_store.record_workflow_completion(
                        client_id=_entry_client_id,
                        workflow_id=pending_workflow,
                        workflow_label=_selector_option.label,
                    )
                    # Centrales de riesgo is counted per sub-flow at step 1.4.1,
                    # so it is NOT counted here at start.
                    if pending_workflow != _CENTRALES_WORKFLOW:
                        await _record_category_interaction_safely(
                            control_store=control_store,
                            client_id=_entry_client_id,
                            category=workflow_engine.get_limit_key(pending_workflow),
                            workflow_label=_selector_option.label,
                            conversation_id=conversation.conversation_id,
                        )
                    conversation.captured_data["control_interaction_recorded"] = "true"
                    logger.info(
                        "Control-table entry recorded conversation_id=%s client_id=%s workflow_id=%s",
                        conversation.conversation_id,
                        _entry_client_id,
                        pending_workflow,
                    )
                except Exception as _exc_ct:
                    logger.exception(
                        "Control-table write failed on workflow entry conversation_id=%s workflow=%s client_id=%s",
                        conversation.conversation_id,
                        pending_workflow,
                        _entry_client_id,
                    )
                    _trace_control_table_write_failure(
                        conversation_id=conversation.conversation_id,
                        client_id=_entry_client_id,
                        momento="workflow_entry",
                        error=_exc_ct,
                        workflow_id=pending_workflow,
                    )

            original_user_query = next(
                (
                    msg.content
                    for msg in conversation.messages
                    if msg.role == MessageRole.USER
                ),
                None,
            )
            if original_user_query:
                conversation.captured_data[_WORKFLOW_ENTRY_HINT_KEY] = (
                    original_user_query
                )
            elif pending_entry_hint:
                conversation.captured_data[_WORKFLOW_ENTRY_HINT_KEY] = (
                    pending_entry_hint
                )

            action_content = _apply_current_step_action_if_needed(
                conversation=conversation,
                workflow_engine=workflow_engine,
                assistant_content=started_prompt,
            )
            return await _apply_smart_route_if_needed(
                conversation=conversation,
                workflow_engine=workflow_engine,
                strands_agent=strands_agent,
                assistant_content=action_content,
                turn_usage=turn_usage,
                back_data_service_url=back_data_service_url,
                trx_service_url=trx_service_url,
                control_store=control_store,
            )

        if _is_negative(user_content):
            reformulated_request = _extract_rejection_reformulation(user_content)
            _clear_pending_workflow_suggestion(conversation)

            if reformulated_request:
                user_content = reformulated_request
            else:
                # Rechazo del candidato ambiguo (Salir) -> formulario PQRS, igual
                # que el no-match: workflow interno pqrs_no_ruteo (boton -> satisfaccion).
                conversation.workflow = "pqrs_no_ruteo"
                conversation.current_step = "1"
                conversation.status = ConversationStatus.ACTIVE
                conversation.flow_answers.clear()
                conversation.captured_data.pop("centrales_riesgo_form_option", None)
                return (
                    workflow_engine.render_current_step_prompt(conversation)
                    or workflow_engine.build_routing_clarification_message()
                )

        _clear_pending_workflow_suggestion(conversation)

    judge_block = await judge_user_message(user_content)
    if judge_block:
        logger.info(
            "Scope judge blocked input at start phase conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.current_step = "start"
        conversation.status = ConversationStatus.ACTIVE
        # Mismo contrato que el filtro de reglas: el benchmark y la analitica
        # deben ver este turno como guardrail_blocked, no como "other". Sin esto
        # el banco adversarial daba por fallidas las inyecciones que SI se pararon.
        conversation.captured_data["_last_guardrail_blocked"] = "true"
        conversation.captured_data["routing_outcome"] = "guardrail_blocked"
        mark_routing_done(conversation, turn_usage)
        return judge_block

    routing_catalog = workflow_engine.build_routing_catalog()

    group_keys, prefilter_usage = await strands_agent.select_groups_with_usage(
        conversation=conversation,
        user_message=user_content,
        routing_catalog=routing_catalog,
    )
    _accumulate_token_usage(turn_usage, prefilter_usage)
    routing_catalog = filter_catalog_by_groups(
        routing_catalog=routing_catalog,
        group_keys=group_keys,
    )
    logger.info(
        "Nivel 1 prefiltro conversation_id=%s grupos=%s catalogo=%s->%s",
        conversation.conversation_id,
        group_keys,
        len(workflow_engine.catalog.welcome.groups),
        len(routing_catalog),
    )

    (
        routing_decision,
        routing_usage,
    ) = await strands_agent.route_initial_workflow_with_usage(
        conversation=conversation,
        user_message=user_content,
        routing_catalog=routing_catalog,
    )
    _accumulate_token_usage(turn_usage, routing_usage)

    # Red de seguridad: si el LLM NO ruteó con confianza pero el mensaje es un
    # caso de centrales de riesgo, llevarlo al menú de centrales (no al no-match).
    # No pisa un match de FAQ ni de otro workflow: solo rescata el no-match.
    if not accepts_routing(routing_decision) and _looks_like_centrales_case(
        user_content
    ):
        logger.info(
            "Keyword-gate centrales -> centrales_de_riesgo conversation_id=%s (LLM sin match)",
            conversation.conversation_id,
        )
        routing_decision = WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key="pqrs",
            workflow="centrales_de_riesgo",
            confidence="high",
            rationale="keyword-gate: caso de centrales de riesgo detectado por reglas",
        )

    mark_routing_decision(routing_decision)

    if accepts_routing(routing_decision):
        logger.info(
            "ROUTING aceptado workflow=%s confidence=%s",
            routing_decision.workflow,
            getattr(routing_decision, "confidence", "n/a"),
        )
        conversation.captured_data["routing_outcome"] = "matched"
        # El cliente logro expresarse: el contador de no-match se reinicia para
        # que un no-match posterior (otro tema) vuelva a tener su reintento.
        _reset_no_match_streak(conversation)
        cap_message = await _maybe_handle_category_cap(
            conversation=conversation,
            control_store=control_store,
            workflow_engine=workflow_engine,
            workflow=routing_decision.workflow,
        )
        if cap_message is not None:
            return cap_message

        entry_hint = _resolve_routing_entry_hint(
            workflow=routing_decision.workflow,
            user_content=user_content,
            rationale=routing_decision.rationale,
        )

        # Auto-start the identified workflow without asking for confirmation.
        if control_store is not None:
            _entry_client_id = conversation.user_id or _extract_customer_id(
                conversation.conversation_id
            )
            try:
                _, _selector_option = workflow_engine._find_workflow_selector_option(
                    routing_decision.workflow
                )
                await control_store.record_workflow_completion(
                    client_id=_entry_client_id,
                    workflow_id=routing_decision.workflow,
                    workflow_label=_selector_option.label,
                )
                # Centrales de riesgo is counted per sub-flow at step 1.4.1,
                # so it is NOT counted here at start.
                if routing_decision.workflow != _CENTRALES_WORKFLOW:
                    await _record_category_interaction_safely(
                        control_store=control_store,
                        client_id=_entry_client_id,
                        category=workflow_engine.get_limit_key(
                            routing_decision.workflow
                        ),
                        workflow_label=_selector_option.label,
                        conversation_id=conversation.conversation_id,
                    )
                conversation.captured_data["control_interaction_recorded"] = "true"
                logger.info(
                    "Control-table entry recorded (auto-start) conversation_id=%s client_id=%s workflow_id=%s",
                    conversation.conversation_id,
                    _entry_client_id,
                    routing_decision.workflow,
                )
            except Exception as _exc_ct:
                logger.exception(
                    "Control-table write failed on auto-start conversation_id=%s workflow=%s",
                    conversation.conversation_id,
                    routing_decision.workflow,
                )
                _trace_control_table_write_failure(
                    conversation_id=conversation.conversation_id,
                    client_id=_entry_client_id,
                    momento="auto_start",
                    error=_exc_ct,
                    workflow_id=routing_decision.workflow,
                )

        started_prompt = workflow_engine.start_workflow(
            conversation,
            routing_decision.workflow,
            entry_hint=entry_hint,
        )

        mark_routing_done(conversation, turn_usage)

        # Always store the real user message as entry hint for smart_route
        # classification. The resolved entry_hint shortcut is only for
        # start_workflow step selection; passing it to the classifier would
        # give the LLM an ambiguous workflow-name string instead of the actual
        # user intent.
        conversation.captured_data[_WORKFLOW_ENTRY_HINT_KEY] = user_content

        if back_data_service_url:
            await _prefetch_back_data_if_needed(
                conversation=conversation,
                back_data_service_url=back_data_service_url,
                control_store=control_store,
            )
        if trx_service_url or back_data_service_url:
            await _prefetch_trx_data_if_needed(
                conversation=conversation,
                trx_service_url=trx_service_url,
                back_data_service_url=back_data_service_url,
                control_store=control_store,
            )

        action_content = _apply_current_step_action_if_needed(
            conversation=conversation,
            workflow_engine=workflow_engine,
            assistant_content=started_prompt,
        )
        return await _apply_smart_route_if_needed(
            conversation=conversation,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            assistant_content=action_content,
            turn_usage=turn_usage,
            back_data_service_url=back_data_service_url,
            trx_service_url=trx_service_url,
            control_store=control_store,
        )

    # Candidato plausible pero AMBIGUO (is_match=true, confidence=low): en vez de
    # auto-start (reservado a high/medium) o de escalar a PQRS (reservado a
    # none/no-match), se CONFIRMA con el usuario: "¿Te refieres a ...?" con
    # botones Continuar/Salir. Continuar -> entra al flujo; Salir -> pqrs_no_ruteo.
    if (
        getattr(routing_decision, "is_match", False)
        and routing_decision.workflow
        and getattr(routing_decision, "confidence", "none") == "low"
    ):
        _low_entry_hint = _resolve_routing_entry_hint(
            workflow=routing_decision.workflow,
            user_content=user_content,
            rationale=routing_decision.rationale,
        )
        conversation.captured_data["routing_outcome"] = "confirmation"
        _set_pending_workflow_suggestion(
            conversation,
            workflow=routing_decision.workflow,
            confidence="low",
            rationale=routing_decision.rationale,
            entry_hint=_low_entry_hint,
        )
        logger.info(
            "ROUTING ambiguo (low) -> confirmacion conversation_id=%s workflow=%s",
            conversation.conversation_id,
            routing_decision.workflow,
        )
        return workflow_engine.build_workflow_confirmation_message(
            routing_decision.workflow,
            confidence="low",
        )

    # Meta-peticion "pelada" de PQR (sin causal) que el router NO pudo mapear a
    # un flujo: en vez de tirar el formulario generico, pedimos el motivo (dos
    # pasos) y luego re-ruteamos. Gate POST-router: nunca pisa un match, solo
    # refina el fallback no-match. Cuando ya venimos re-ruteando un causal
    # capturado, user_content no es "pelado" y este bloque no dispara.
    if _is_bare_pqrs_request(user_content):
        logger.info(
            "Meta-peticion PQR pelada -> aclaracion de causal (2 pasos) conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.captured_data[_PQRS_CLARIFY_STATE_KEY] = (
            _PQRS_CLARIFY_AWAIT_CONTINUE
        )
        conversation.workflow = None
        conversation.current_step = "start"
        conversation.status = ConversationStatus.ACTIVE
        conversation.flow_answers.clear()
        conversation.captured_data.pop("centrales_riesgo_form_option", None)
        conversation.captured_data["routing_outcome"] = "pqrs_clarify"
        _reset_no_match_streak(conversation)
        return _PQRS_CLARIFY_INTRO_MESSAGE

    logger.info(
        "ROUTING sin match -> selector de subflujos de centrales conversation_id=%s",
        conversation.conversation_id,
    )
    _reset_no_match_streak(conversation)
    conversation.captured_data["routing_outcome"] = "centrales_selector"
    conversation.flow_answers.clear()
    conversation.captured_data.pop("centrales_riesgo_form_option", None)
    conversation.captured_data.pop(_WORKFLOW_ENTRY_HINT_KEY, None)
    return workflow_engine.start_workflow(
        conversation,
        _CENTRALES_WORKFLOW,
        entry_hint=None,
    )


@log_execution
def _should_generate_friendly_closure(conversation: Conversation) -> bool:
    """
    Determine whether the closing response should be generated by the agent.

    Args:
        conversation: Conversation whose group determines the close behavior.

    Returns:
        `True` only for guide flows that require an LLM-crafted closing message.
    """

    normalized_general_workflow = _normalize_text(
        conversation.general_workflow
    ).replace(
        " ",
        "_",
    )
    should_generate = normalized_general_workflow == "guia_rapida"
    logger.info(
        "Evaluated friendly closure conversation_id=%s general_workflow=%s should_generate=%s",
        conversation.conversation_id,
        conversation.general_workflow,
        should_generate,
    )
    return should_generate


@log_execution
def _has_resolved_guide_data(conversation: Conversation) -> bool:
    """
    Determine whether a guide workflow already has response data to share.

    Args:
        conversation: Conversation that may contain resolved business data.

    Returns:
        `True` when the guide flow has non-empty resolved data available.
    """

    has_data = any(
        isinstance(value, str) and value.strip()
        for key, value in conversation.captured_data.items()
        if key not in _INTERNAL_CAPTURED_DATA_KEYS
    )
    logger.info(
        "Evaluated resolved guide data conversation_id=%s captured_keys=%s has_data=%s",
        conversation.conversation_id,
        sorted(conversation.captured_data.keys()),
        has_data,
    )
    return has_data


@log_execution
def _is_guide_opt_out(conversation: Conversation) -> bool:
    """
    Determine whether the guide flow ended because the user chose not to continue.

    Args:
        conversation: Conversation that may contain an explicit opt-out answer.

    Returns:
        `True` when the workflow captured a negative continuation decision.
    """

    opted_out = (
        conversation.workflow == "centrales_de_riesgo"
        and conversation.flow_answers.get("continuar_consulta_centrales_de_riesgo")
        == "no"
    )
    logger.info(
        "Evaluated guide opt-out conversation_id=%s workflow=%s opted_out=%s",
        conversation.conversation_id,
        conversation.workflow,
        opted_out,
    )
    return opted_out


@log_execution
def _build_unavailable_guide_response() -> str:
    """
    Build the default guide-flow message when there is no resolved information.

    Returns:
        Friendly fallback message for unresolved guide requests.
    """

    return (
        "Lo siento, pero actualmente no puedo responder esto. Gracias por comunicarte."
    )


@log_execution
def _should_keep_guide_terminal_response(
    conversation: Conversation,
    assistant_content: str,
) -> bool:
    """
    Preserve explicit terminal guide messages that should not be replaced.

    Args:
        conversation: Conversation that may carry internal preservation flags.
        assistant_content: Terminal response generated by the workflow engine.

    Returns:
        `True` when the workflow message should be returned as-is.
    """

    normalized_content = _normalize_text(assistant_content)
    preserve_terminal_response = (
        conversation.captured_data.get("preserve_terminal_response") == "true"
    )
    sold_portfolio_case = (
        conversation.flow_answers.get("novedad_producto_pasivo_centrales_de_riesgo")
        == "cartera_vendida"
    )
    negative_report_notification_case = (
        conversation.flow_answers.get("tipo_inconveniente_centrales_de_riesgo")
        == "reporte_negativo_sin_notificacion"
    )
    should_keep = (
        preserve_terminal_response
        or sold_portfolio_case
        or negative_report_notification_case
        or "aun no puedo hacer esto" in normalized_content
    )
    logger.info(
        "Evaluated guide terminal preservation conversation_id=%s should_keep=%s preserve_terminal_response=%s sold_portfolio_case=%s negative_report_notification_case=%s assistant_content=%s",
        conversation.conversation_id,
        should_keep,
        preserve_terminal_response,
        sold_portfolio_case,
        negative_report_notification_case,
        assistant_content,
    )
    return should_keep


@log_execution
def _is_central_risk_privacy_case(conversation: Conversation) -> bool:
    """
    Determine whether the guide flow closed on the privacy-related risk branch.

    Args:
        conversation: Conversation that may contain the selected central-risk issue.

    Returns:
        `True` when the user selected the unauthorized-query option.
    """

    is_privacy_case = (
        conversation.workflow == "centrales_de_riesgo"
        and conversation.flow_answers.get("tipo_inconveniente_centrales_de_riesgo")
        == "consulta_sin_permiso"
    )
    logger.info(
        "Evaluated central risk privacy case conversation_id=%s workflow=%s is_privacy_case=%s",
        conversation.conversation_id,
        conversation.workflow,
        is_privacy_case,
    )
    return is_privacy_case


@log_execution
def _is_central_risk_pasive_guidance_case(conversation: Conversation) -> bool:
    """
    Determine whether the passive-product novelty requires an agent closing response.

    Args:
        conversation: Conversation that may contain a passive-product novelty selection.

    Returns:
        `True` when the selected novelty should close with agent guidance.
    """

    novelty = conversation.flow_answers.get(
        "novedad_producto_pasivo_centrales_de_riesgo"
    )
    is_guidance_case = novelty in {
        "cuenta_aperturada_no_reconocida",
        "reporte_negativo_adelanto_nomina",
    }
    logger.info(
        "Evaluated passive-product guidance case conversation_id=%s novelty=%s is_guidance_case=%s",
        conversation.conversation_id,
        novelty,
        is_guidance_case,
    )
    return is_guidance_case


@log_execution
def _get_guide_closure_mode_override(conversation: Conversation) -> str | None:
    """
    Return a workflow-specific closing mode when the guide flow requests one.

    Args:
        conversation: Conversation that may include a custom close behavior.

    Returns:
        Requested closure mode or `None` when not defined.
    """

    closure_mode = conversation.captured_data.get("guide_closure_mode")
    logger.info(
        "Resolved guide closure mode override conversation_id=%s closure_mode=%s",
        conversation.conversation_id,
        closure_mode,
    )
    return closure_mode or None


@log_execution
def _should_skip_guide_closure_agent(
    *,
    conversation: Conversation,
    closure_mode_override: str | None,
) -> bool:
    """
    Determine whether the guide-flow closing message should bypass the agent.

    Args:
        conversation: Conversation that may request a deterministic closure.
        closure_mode_override: Workflow-specific closure mode stored in the conversation.

    Returns:
        `True` when the current closing response must be returned as-is.
    """

    should_skip = closure_mode_override == "central_risk_account_status_guidance"
    logger.info(
        "Evaluated guide closure agent bypass conversation_id=%s workflow=%s closure_mode=%s should_skip=%s",
        conversation.conversation_id,
        conversation.workflow,
        closure_mode_override,
        should_skip,
    )
    return should_skip


@log_execution
def _apply_turn_token_usage(
    user_message: Message,
    assistant_message: Message,
    turn_usage: TokenUsage,
) -> None:
    """
    Persist aggregated model usage on the user and assistant messages.

    Args:
        user_message: Incoming user message that initiated the turn.
        assistant_message: Assistant message generated for the turn.
        turn_usage: Aggregated token usage across all model calls in the turn.
    """

    logger.info(
        "Applying turn token usage user_message_id=%s assistant_message_id=%s total_tokens=%s",
        user_message.id,
        assistant_message.id,
        turn_usage.total_tokens,
    )
    user_message.tokens.input_tokens = turn_usage.input_tokens
    user_message.tokens.output_tokens = 0
    user_message.tokens.total_tokens = turn_usage.input_tokens

    assistant_message.tokens.input_tokens = turn_usage.input_tokens
    assistant_message.tokens.output_tokens = turn_usage.output_tokens
    assistant_message.tokens.total_tokens = turn_usage.total_tokens


@log_execution
async def _resolve_assistant_content(
    *,
    conversation: Conversation,
    user_content: str,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    control_store: ControlTableStore | None = None,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
) -> tuple[str, TokenUsage]:
    """
    Resolve the next assistant content with the deterministic workflow engine
    and, only for `guia_rapida`, an LLM-crafted friendly closing message.

    Args:
        conversation: Runtime conversation being updated.
        user_content: Raw user input received by the API.
        workflow_engine: Deterministic workflow tree engine.
        strands_agent: Strands wrapper used for validation and closing messages.

    Returns:
        Assistant content to append to the conversation and the aggregated
        token usage generated while handling the turn.
    """

    logger.info(
        "Resolving assistant content conversation_id=%s workflow=%s current_step=%s",
        conversation.conversation_id,
        conversation.workflow,
        conversation.current_step,
    )
    was_closed = conversation.status == ConversationStatus.CLOSED
    turn_usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    # Snapshot of the centrales sub-flow answer BEFORE this turn, to detect when
    # step 1.4.1 resolves a situation (manual pick or smart-route auto-advance).
    centrales_subflow_before = conversation.flow_answers.get(
        _CENTRALES_SUBFLOW_ANSWER
    )

    # --- Token de piloto TXNR: se procesa ANTES del guardrail y del router ---
    # Habilita el flujo real solo para ESTA conversacion. El mensaje no se rutea, no
    # se envia al LLM y su valor NO se registra. Si el token es incorrecto se trata
    # como mensaje normal (no se responde "token invalido": seria un oraculo).
    if _is_trx_canary_token(user_content):
        conversation.captured_data[_TRX_CANARY_KEY] = "true"
        conversation.captured_data["routing_outcome"] = "trx_canary_enabled"
        if conversation.status == ConversationStatus.RUNNING:
            conversation.status = ConversationStatus.ACTIVE
            conversation.running_since = None
        logger.info(
            "TXNR canary habilitado por token conversation_id=%s (valor no registrado)",
            conversation.conversation_id,
        )
        return _TRX_CANARY_ACK_MESSAGE, turn_usage

    block_message = screen_user_input(user_content)
    # Marca del turno: ¿el guardrail bloqueó la entrada? (lo lee _build_turn_event)
    conversation.captured_data["_last_guardrail_blocked"] = (
        "true" if block_message else "false"
    )
    if block_message:
        conversation.captured_data["routing_outcome"] = "guardrail_blocked"
        # Un bloqueo del guardrail finaliza el turno de forma sincrona (respuesta
        # deterministica). Hay que normalizar el turno en curso RUNNING -> ACTIVE
        # para que la respuesta salga como Active y el front la renderice, en vez
        # de quedarse en polling. Aplica a TODO bloqueo: inyeccion, fuera de
        # alcance, entrada vacia y datos de terceros.
        if conversation.status == ConversationStatus.RUNNING:
            conversation.status = ConversationStatus.ACTIVE
            conversation.running_since = None
        mark_routing_done(conversation, turn_usage)
        logger.info(
            "Guardrail blocked input conversation_id=%s",
            conversation.conversation_id,
        )
        return block_message, turn_usage

    # Saludo puro en un punto neutro (inicio, confirmacion o satisfaccion): se
    # re-saluda de forma deterministica en vez de rutear al formulario o
    # consumirlo como respuesta del flujo. Resuelve fugas tipo "buena tarde" o
    # "hola como vas" que llegan tanto al inicio como a mitad de conversacion.
    if _is_pure_greeting(user_content) and _is_greeting_safe_point(conversation):
        logger.info(
            "Pure greeting detected at neutral point; returning welcome without routing conversation_id=%s current_step=%s",
            conversation.conversation_id,
            conversation.current_step,
        )
        _reset_conversation_for_reroute(conversation)
        conversation.captured_data["routing_outcome"] = "greeting"
        # Un saludo no consume el reintento de aclaracion.
        _reset_no_match_streak(conversation)
        mark_routing_done(conversation, turn_usage)
        return _build_greeting_response(workflow_engine), turn_usage

    # Entrada sin ninguna palabra interpretable ("9+", "...", "??"): se pide
    # aclaracion sin gastar una llamada al LLM y sin arriesgar que el router
    # invente un match. Solo en el paso `start` (fuera de cualquier flujo) para
    # no pisar respuestas legitimas como "1" o "no" dentro de un flujo.
    # Si el reintento ya se uso, NO se atrapa aqui: sigue al router, que escalara
    # al formulario con la misma regla que cualquier otro no-match.
    if (
        conversation.workflow is None
        and conversation.current_step == "start"
        and _is_unintelligible(user_content)
        and _no_match_streak(conversation) < _NO_MATCH_MAX_RETRIES
    ):
        _streak = _no_match_streak(conversation) + 1
        conversation.captured_data[_NO_MATCH_STREAK_KEY] = str(_streak)
        conversation.captured_data["routing_outcome"] = "clarify_unintelligible"
        conversation.status = ConversationStatus.ACTIVE
        logger.info(
            "Entrada sin palabras interpretables -> pide aclaracion (intento %s) conversation_id=%s",
            _streak,
            conversation.conversation_id,
        )
        return workflow_engine.build_unintelligible_input_message(), turn_usage

    if conversation.workflow is None:
        assistant_content = await _resolve_start_phase(
            conversation=conversation,
            user_content=user_content,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            control_store=control_store,
            turn_usage=turn_usage,
            back_data_service_url=back_data_service_url,
            trx_service_url=trx_service_url,
        )
        mark_routing_done(conversation, turn_usage)
    else:
        if _should_reroute_from_active_workflow(
            conversation=conversation,
            workflow_engine=workflow_engine,
            user_content=user_content,
        ):
            logger.info(
                "Rerouting active conversation from start step conversation_id=%s previous_workflow=%s",
                conversation.conversation_id,
                conversation.workflow,
            )
            _reset_conversation_for_reroute(conversation)
            assistant_content = await _resolve_start_phase(
                conversation=conversation,
                user_content=user_content,
                workflow_engine=workflow_engine,
                strands_agent=strands_agent,
                control_store=control_store,
                turn_usage=turn_usage,
                back_data_service_url=back_data_service_url,
                trx_service_url=trx_service_url,
            )
        else:
            # Turno dentro de un workflow ya iniciado (no hubo ruteo nuevo).
            conversation.captured_data["routing_outcome"] = "in_flow"
            trx_capture_content = await _handle_trx_interactive_capture_step(
                conversation=conversation,
                user_content=user_content,
                workflow_engine=workflow_engine,
                trx_service_url=trx_service_url,
                back_data_service_url=back_data_service_url,
                control_store=control_store,
            )
            if trx_capture_content is not None:
                assistant_content = trx_capture_content
            else:
                assistant_content = workflow_engine.generate_response(
                    conversation,
                    user_content,
                )

            if not was_closed:
                step_before_prefetch = conversation.current_step
                if back_data_service_url:
                    await _prefetch_back_data_if_needed(
                        conversation=conversation,
                        back_data_service_url=back_data_service_url,
                        control_store=control_store,
                    )
                if trx_service_url or back_data_service_url:
                    await _prefetch_trx_data_if_needed(
                        conversation=conversation,
                        trx_service_url=trx_service_url,
                        back_data_service_url=back_data_service_url,
                        control_store=control_store,
                    )
                if conversation.current_step != step_before_prefetch:
                    assistant_content = (
                        workflow_engine.render_current_step_prompt(conversation)
                        or assistant_content
                    )

                await _load_trx_customer_address_if_needed(
                    conversation=conversation,
                        trx_service_url=trx_service_url,
                )

                assistant_content = _apply_current_step_action_if_needed(
                    conversation=conversation,
                    workflow_engine=workflow_engine,
                    assistant_content=assistant_content,
                )
                assistant_content = await _apply_smart_route_if_needed(
                    conversation=conversation,
                    workflow_engine=workflow_engine,
                    strands_agent=strands_agent,
                    assistant_content=assistant_content,
                    turn_usage=turn_usage,
                    back_data_service_url=back_data_service_url,
                    trx_service_url=trx_service_url,
                    control_store=control_store,
                )

    # Per-SUB-FLOW daily cap for centrales de riesgo. If step 1.4.1 just
    # resolved a situation THIS turn (either a manual pick or a smart-route
    # auto-advance), count/enforce it with key centrales_de_riesgo:<subflow>.
    if conversation.workflow == _CENTRALES_WORKFLOW:
        centrales_subflow_after = conversation.flow_answers.get(
            _CENTRALES_SUBFLOW_ANSWER
        )
        if (
            centrales_subflow_after
            and centrales_subflow_after != centrales_subflow_before
        ):
            centrales_cap_message = await _maybe_handle_centrales_subflow_cap(
                conversation=conversation,
                control_store=control_store,
                subflow_key=centrales_subflow_after,
            )
            if centrales_cap_message is not None:
                assistant_content = centrales_cap_message

    if (
        conversation.status == ConversationStatus.CLOSED
        and not was_closed
        and _should_generate_friendly_closure(conversation)
    ):
        closure_mode_override = _get_guide_closure_mode_override(conversation)

        if _should_keep_guide_terminal_response(conversation, assistant_content):
            logger.info(
                "Keeping explicit guide terminal response conversation_id=%s workflow=%s",
                conversation.conversation_id,
                conversation.workflow,
            )
        elif _should_skip_guide_closure_agent(
            conversation=conversation,
            closure_mode_override=closure_mode_override,
        ):
            logger.info(
                "Keeping deterministic guide closure without LLM conversation_id=%s workflow=%s closure_mode=%s",
                conversation.conversation_id,
                conversation.workflow,
                closure_mode_override,
            )
        elif not _llm_closure_enabled() and (
            closure_mode_override is not None
            or _has_resolved_guide_data(conversation)
            or _is_guide_opt_out(conversation)
            or _is_central_risk_privacy_case(conversation)
            or _is_central_risk_pasive_guidance_case(conversation)
        ):
            # Cierre por LLM apagado (LLM_CLOSURE_ENABLED=false): se conserva el
            # mensaje deterministico del YAML que ya venia calculado, en vez de
            # dejar que el modelo lo reescriba. Se preserva la rama `else` de
            # abajo para el caso "sin datos resueltos", que tiene su propio
            # mensaje fijo.
            logger.info(
                "LLM closure disabled; keeping deterministic content conversation_id=%s workflow=%s",
                conversation.conversation_id,
                conversation.workflow,
            )
        elif closure_mode_override is not None:
            (
                assistant_content,
                summary_usage,
            ) = await strands_agent.generate_final_response_with_usage(
                conversation=conversation,
                default_message=assistant_content,
                closure_mode=closure_mode_override,
            )
            _accumulate_token_usage(turn_usage, summary_usage)
        elif _has_resolved_guide_data(conversation):
            (
                assistant_content,
                summary_usage,
            ) = await strands_agent.generate_final_response_with_usage(
                conversation=conversation,
                default_message=assistant_content,
                closure_mode="resolved_data",
            )
            _accumulate_token_usage(turn_usage, summary_usage)
        elif _is_guide_opt_out(conversation):
            (
                assistant_content,
                summary_usage,
            ) = await strands_agent.generate_final_response_with_usage(
                conversation=conversation,
                default_message=assistant_content,
                closure_mode="opt_out",
            )
            _accumulate_token_usage(turn_usage, summary_usage)
        elif _is_central_risk_privacy_case(conversation):
            (
                assistant_content,
                summary_usage,
            ) = await strands_agent.generate_final_response_with_usage(
                conversation=conversation,
                default_message=assistant_content,
                closure_mode="privacy_guidance",
            )
            _accumulate_token_usage(turn_usage, summary_usage)
        elif _is_central_risk_pasive_guidance_case(conversation):
            (
                assistant_content,
                summary_usage,
            ) = await strands_agent.generate_final_response_with_usage(
                conversation=conversation,
                default_message=assistant_content,
                closure_mode="passive_product_guidance",
            )
            _accumulate_token_usage(turn_usage, summary_usage)
        else:
            assistant_content = _build_unavailable_guide_response()
            logger.info(
                "Guide workflow closed without resolved data conversation_id=%s workflow=%s",
                conversation.conversation_id,
                conversation.workflow,
            )
    elif conversation.status == ConversationStatus.CLOSED and not was_closed:
        logger.info(
            "Skipping LLM closing message conversation_id=%s general_workflow=%s",
            conversation.conversation_id,
            conversation.general_workflow,
        )

    logger.info(
        "Resolved assistant content conversation_id=%s current_step=%s status=%s total_tokens=%s",
        conversation.conversation_id,
        conversation.current_step,
        conversation.status.value,
        turn_usage.total_tokens,
    )
    return assistant_content, turn_usage


def _emit_turn_summary(
    *,
    conversation: Conversation,
    customer_id: str,
    user_message: str,
    elapsed_ms: float,
    operation: str,
) -> None:
    """Emit a per-client trace summarizing how the agent handled this turn.

    Captures the user message, the workflow/step the agent landed on, the
    assistant response and the turn latency, so the full agent behaviour per
    user is visible in the trace store. Best-effort: never raises.
    """

    response_text = ""
    try:
        for msg in reversed(conversation.messages):
            role = getattr(msg, "role", None)
            role_val = getattr(role, "value", role)
            if role_val == "assistant":
                response_text = getattr(msg, "content", "") or ""
                break
        if not response_text and conversation.messages:
            response_text = getattr(conversation.messages[-1], "content", "") or ""
    except Exception:  # noqa: BLE001
        response_text = ""

    status_val = getattr(getattr(conversation, "status", None), "value", None)
    schedule_trace_event(
        event_type="chat_turn",
        operation=operation,
        outcome="ok",
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        elapsed_ms=elapsed_ms,
        request_summary={
            "user_message": (user_message or "")[:500],
            "content_length": len(user_message or ""),
        },
        response_summary={
            "general_workflow": conversation.general_workflow,
            "workflow": conversation.workflow,
            "current_step": conversation.current_step,
            "status": status_val,
            "response": response_text[:1200],
            "response_length": len(response_text),
        },
        tags=["chat_turn", "agent"],
    )


@log_execution
async def process_chat_message(
    *,
    content: str,
    conversation_id: str,
    store: ConversationStore,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
) -> Conversation:
    """
    Load an existing conversation, persist the incoming user message,
    generate the next workflow response, and persist the turn incrementally.

    Args:
        content: Raw user message content received by the API.
        conversation_id: Conversation identifier used to load existing context.
        store: Persistence backend responsible for conversation storage.
        workflow_engine: Decision-tree engine used to drive the workflow prompts.
        strands_agent: Strands wrapper used to validate answers and draft closures.

    Returns:
        The updated conversation instance.
    """

    logger.info(
        "Processing chat message conversation_id=%s content_length=%s",
        conversation_id,
        len(content),
    )
    customer_id = _extract_customer_id(conversation_id)
    _turn_start = time.perf_counter()
    conversation_lock = await _get_conversation_lock(conversation_id)

    async with conversation_lock:
        conversation = await store.load_conversation(conversation_id)

        if conversation is None:
            raise ResourceNotFoundError(
                "Conversation not found. Start it first using POST /start.",
                details={"conversation_id": conversation_id},
            )

        conversation.user_id = customer_id
        conversation = await _process_message_turn(
            conversation=conversation,
            content=content,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

    _emit_turn_summary(
        conversation=conversation,
        customer_id=customer_id,
        user_message=content,
        elapsed_ms=round((time.perf_counter() - _turn_start) * 1000, 2),
        operation="process_chat_message",
    )

    if conversation.status in {ConversationStatus.CLOSED, ConversationStatus.ERROR}:
        await _release_conversation_lock(conversation_id)

    return conversation


@log_execution
async def process_start_message(
    *,
    user_id: str,
    store: ConversationStore,
    control_store: ControlTableStore | None = None,
    benchmark_mode: bool = False,
) -> Conversation:
    """
    Initialize a new conversation and persist the greeting returned by
    `POST /start`.

    A conversation id is deterministic per user and calendar day
    (``user_id_yyyymmdd``). When the previous session for that id is already
    ``CLOSED``, the user is allowed to reopen a fresh session over the same id
    (its stale messages are removed first). When the previous session is still
    ``ACTIVE`` it is treated as a conflict. The number of sessions a user may
    start per day is capped by ``MAX_DAILY_SESSIONS``.

    Args:
        user_id: User identifier used to generate the conversation id.
        store: Persistence backend responsible for conversation storage.
        control_store: Optional control-table backend used to enforce the
            daily session limit. When ``None`` the limit is not applied.
        benchmark_mode: ``True`` when the request carried ``X-Benchmark-Mode``
            (benchmark/canary). The conversation is then persistently marked
            with ``captured_data["source"] = "benchmark"`` so every analytics
            event it emits is routed away from the live indices.

    Returns:
        The created conversation instance.
    """

    conversation_id = _build_conversation_id(user_id)
    benchmark_mode = benchmark_mode or _benchmark_context_active()
    logger.info(
        "Processing start message user_id=%s conversation_id=%s",
        user_id,
        conversation_id,
    )
    conversation_lock = await _get_conversation_lock(conversation_id)

    async with conversation_lock:
        existing_conversation = await store.load_conversation(conversation_id)

        if existing_conversation is not None:
            # Idempotent /start (Architecture A): an in-progress session is
            # returned as-is so re-entering the chat RESUMES where the user left
            # off. A new session is NOT created and the daily session counter is
            # NOT incremented. Only a terminated session (Closed/Error) or a
            # stuck Running one reopens a fresh session over the same id.
            # Concurrency-safe: the whole block runs under the per-conversation
            # lock, and each client has an independent conversation id, so
            # multiple simultaneous users never interfere with one another.
            is_stuck_running = (
                existing_conversation.status == ConversationStatus.RUNNING
                and _is_running_stuck(existing_conversation)
            )
            is_terminated = existing_conversation.status in {
                ConversationStatus.CLOSED,
                ConversationStatus.ERROR,
            }

            if not is_terminated and not is_stuck_running:
                logger.info(
                    "Resuming existing session (idempotent start) conversation_id=%s status=%s message_count=%s",
                    conversation_id,
                    existing_conversation.status.value,
                    len(existing_conversation.messages),
                )
                if benchmark_mode and _mark_benchmark_conversation(
                    existing_conversation
                ):
                    await store.save_conversation_reference(existing_conversation)
                    await store.refresh()
                return existing_conversation

            # A previous session is closed/errored/stuck: reopen a fresh session
            # over the same deterministic id and drop the stale message history so
            # the new session does not inherit it.
            logger.info(
                "Reopening conversation over a previous session conversation_id=%s previous_status=%s",
                conversation_id,
                existing_conversation.status.value,
            )
            await store.delete_conversation_messages(conversation_id)

        conversation = _build_new_conversation(conversation_id, user_id)
        if benchmark_mode:
            _mark_benchmark_conversation(conversation)
            logger.info(
                "Conversation marked as benchmark source conversation_id=%s",
                conversation_id,
            )
        assistant_started_at = datetime.now(UTC)
        assistant_responded_at = datetime.now(UTC)
        assistant_message = _build_assistant_message(
            await _build_start_greeting(user_id),
            received_at=assistant_started_at,
            responded_at=assistant_responded_at,
        )
        conversation.add_message(assistant_message)
        await store.save_conversation_reference(conversation)
        await store.save_message(conversation.conversation_id, assistant_message)
        await store.refresh()

        if control_store is not None:
            await _record_session_start_safely(
                control_store=control_store,
                client_id=user_id,
                conversation_id=conversation_id,
            )

        _emit_event("conversation.started", _build_started_event(conversation))

        logger.info(
            "Completed start conversation creation conversation_id=%s current_step=%s status=%s message_count=%s",
            conversation.conversation_id,
            conversation.current_step,
            conversation.status.value,
            len(conversation.messages),
        )
        return conversation


@log_execution
async def _is_daily_session_limit_reached(
    *,
    control_store: ControlTableStore,
    client_id: str,
    conversation_id: str,
) -> bool:
    """Return whether the client has reached the daily session limit.

    Never raises: if the control table is unavailable the start is allowed so a
    transient persistence issue does not block legitimate customers.
    """

    max_daily_sessions = load_max_daily_sessions()

    try:
        record = await control_store.get_record(client_id)
    except Exception:
        # Never block a legitimate start because the control table is unavailable.
        logger.exception(
            "Daily session limit check failed; allowing start conversation_id=%s client_id=%s",
            conversation_id,
            client_id,
        )
        return False

    current_count = control_store.get_daily_session_count(record)
    logger.info(
        "Daily session limit check conversation_id=%s client_id=%s current_count=%s max=%s",
        conversation_id,
        client_id,
        current_count,
        max_daily_sessions,
    )

    return current_count >= max_daily_sessions


@log_execution
async def _build_capped_session_conversation(
    *,
    conversation_id: str,
    user_id: str,
    store: ConversationStore,
    message: str | None = None,
) -> Conversation:
    """Build and persist a Closed conversation carrying a graceful limit message.

    Replaces the previous hard 409: the client receives a formal message instead
    of an error, and the daily session counter is NOT incremented. ``message``
    lets callers choose the text (daily session cap vs full-day block).
    """

    conversation = _build_new_conversation(conversation_id, user_id)
    started_at = datetime.now(UTC)
    assistant_message = _build_assistant_message(
        message or _GENERAL_MESSAGES.daily_session_limit_message,
        received_at=started_at,
        responded_at=datetime.now(UTC),
    )
    conversation.add_message(assistant_message)
    conversation.current_step = "start"
    conversation.status = ConversationStatus.CLOSED

    await store.save_conversation_reference(conversation)
    await store.save_message(conversation.conversation_id, assistant_message)
    await store.refresh()

    logger.info(
        "Daily session limit reached; returning graceful message conversation_id=%s client_id=%s",
        conversation_id,
        user_id,
    )
    return conversation


@log_execution
async def _record_session_start_safely(
    *,
    control_store: ControlTableStore,
    client_id: str,
    conversation_id: str,
) -> None:
    """Increment the daily session counter, swallowing persistence errors."""

    try:
        await control_store.record_session_start(client_id)
    except Exception:
        logger.exception(
            "Failed to record daily session start conversation_id=%s client_id=%s",
            conversation_id,
            client_id,
        )


def _last_assistant_message(conversation: Conversation) -> Message | None:
    """Return the assistant message currently on screen, if there is one."""

    for message in reversed(conversation.messages):
        if message.role == MessageRole.ASSISTANT:
            return message
    return None


@log_execution
async def _process_message_turn(
    *,
    conversation: Conversation,
    content: str,
    store: ConversationStore,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    control_store: ControlTableStore | None = None,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
) -> Conversation:
    """Persist one user-assistant turn for a conversation."""

    prior_status = conversation.status
    step_before_turn = conversation.current_step

    # La marca de repintado la pone el motor DURANTE este turno; una heredada
    # del turno anterior haria que se pisara la tarjeta equivocada.
    conversation.captured_data.pop(MULTI_SELECT_REFRESH_KEY, None)
    card_before_turn = _last_assistant_message(conversation)

    user_message = _build_user_message(content)
    conversation.add_message(user_message)
    await store.save_message(conversation.conversation_id, user_message)
    assistant_started_at = datetime.now(UTC)
    assistant_content, turn_usage = await _resolve_assistant_content(
        conversation=conversation,
        user_content=content,
        workflow_engine=workflow_engine,
        strands_agent=strands_agent,
        control_store=control_store,
        back_data_service_url=back_data_service_url,
        trx_service_url=trx_service_url,
    )

    assistant_responded_at = datetime.now(UTC)

    # Marcar una casilla o pasar de pagina NO es un turno de conversacion: el
    # selector es UNA tarjeta que se repinta. Se reutiliza el mismo message_id,
    # de modo que ``save_message`` (index_document) la actualiza en sitio en vez
    # de encolar otra copia del listado, y el clic tampoco queda como mensaje.
    refresh_card = (
        conversation.captured_data.pop(MULTI_SELECT_REFRESH_KEY, None) == "true"
        and card_before_turn is not None
    )

    if refresh_card:
        conversation.messages.remove(user_message)
        assistant_message = card_before_turn
        assistant_message.content = assistant_content
        assistant_message.timing.responded_at = assistant_responded_at
        conversation.refresh_message_dates()

        # La tarjeta ya traia el consumo del turno que la genero; repintarla se
        # SUMA, no lo reemplaza, para no perder esos tokens en las metricas.
        turn_usage = TokenUsage(
            input_tokens=assistant_message.tokens.input_tokens
            + turn_usage.input_tokens,
            output_tokens=assistant_message.tokens.output_tokens
            + turn_usage.output_tokens,
            total_tokens=assistant_message.tokens.total_tokens
            + turn_usage.total_tokens,
        )

        logger.info(
            "Multi-select card refreshed in place conversation_id=%s step=%s message_id=%s",
            conversation.conversation_id,
            conversation.current_step,
            assistant_message.id,
        )
    else:
        assistant_message = _build_assistant_message(
            assistant_content,
            received_at=assistant_started_at,
            responded_at=assistant_responded_at,
        )
        conversation.add_message(assistant_message)

    _apply_turn_token_usage(user_message, assistant_message, turn_usage)
    _finalize_user_message_timing(user_message, assistant_responded_at)

    # Traza de transicion por turno (ajuste 13/08): en el flujo trx, cada
    # turno deja paso_origen -> paso_destino con la respuesta enmascarada.
    # Un solo punto de emision: cubre motor y gates sin sembrar llamadas.
    _trx_trace_turn_transition(conversation, step_before=step_before_turn)

    # RUNNING lo pone este modulo antes de lanzar el turno, y le toca a el
    # quitarlo: el motor no tiene por que conocer un estado de transporte.
    # Sin esto, una opcion no reconocida dejaba la conversacion en RUNNING
    # y el cliente esperaba los 150 s del watchdog por una respuesta lista.
    # Solo se toca RUNNING: CLOSED y ERROR son deliberados.
    if conversation.status == ConversationStatus.RUNNING:
        conversation.status = ConversationStatus.ACTIVE
        conversation.running_since = None

    if refresh_card:
        # El clic ya se habia guardado por durabilidad, antes de saber que solo
        # repintaba la tarjeta; se retira para que el historial no lo muestre.
        await store.delete_message(conversation.conversation_id, user_message.id)
        await store.save_message(conversation.conversation_id, assistant_message)
    else:
        await asyncio.gather(
            store.save_message(conversation.conversation_id, user_message),
            store.save_message(conversation.conversation_id, assistant_message),
        )
    await store.refresh()
    await store.save_conversation_reference(conversation)

    if (
        control_store is not None
        and conversation.status == ConversationStatus.CLOSED
        and conversation.workflow
        and not conversation.captured_data.get("control_interaction_recorded")
    ):
        # Fallback: entry-time recording failed earlier; attempt once more at close.
        _client_id = conversation.user_id or _extract_customer_id(
            conversation.conversation_id
        )
        logger.warning(
            "Control-table entry was not recorded at workflow start; retrying at close conversation_id=%s client_id=%s workflow_id=%s",
            conversation.conversation_id,
            _client_id,
            conversation.workflow,
        )
        try:
            _, _selector_option = workflow_engine._find_workflow_selector_option(
                conversation.workflow
            )
            await control_store.record_workflow_completion(
                client_id=_client_id,
                workflow_id=conversation.workflow,
                workflow_label=_selector_option.label,
            )
            conversation.captured_data["control_interaction_recorded"] = "true"
            await store.save_conversation_reference(conversation)
            logger.info(
                "Control-table fallback recorded successfully conversation_id=%s client_id=%s workflow_id=%s",
                conversation.conversation_id,
                _client_id,
                conversation.workflow,
            )
        except Exception as _exc_ct:
            logger.exception(
                "Control-table fallback write also failed conversation_id=%s workflow=%s client_id=%s",
                conversation.conversation_id,
                conversation.workflow,
                _client_id,
            )
            _trace_control_table_write_failure(
                conversation_id=conversation.conversation_id,
                client_id=_client_id,
                momento="fallback_al_cerrar",
                error=_exc_ct,
                workflow_id=conversation.workflow,
            )

    logger.info(
        "Completed turn processing conversation_id=%s current_step=%s status=%s message_count=%s",
        conversation.conversation_id,
        conversation.current_step,
        conversation.status.value,
        len(conversation.messages),
    )

    turn_duration_ms = max(
        int((assistant_responded_at - assistant_started_at).total_seconds() * 1000),
        0,
    )
    # Paso final del turno para la cabecera del benchmark (datasets de bypass).
    mark_final_step(conversation)
    _emit_event(
        "conversation.turn",
        _build_turn_event(
            conversation,
            turn_usage=turn_usage,
            duration_ms=turn_duration_ms,
        ),
    )
    # Traza de la conversacion (pregunta del usuario + respuesta del bot) para el
    # tablero de analitica (indice pqr-conversations-*).
    _emit_event(
        "conversation.trace",
        _build_trace_event(
            conversation,
            turn_usage=turn_usage,
            duration_ms=turn_duration_ms,
        ),
    )

    # Architecture A: a /chat turn does not end the SESSION when a CONSULTATION
    # finishes — it returns to the start phase so the customer can ask again.
    # EXCEPTION: a limit-terminated session (daily cap / exhausted rechecks /
    # decline) stays CLOSED so the user cannot keep asking (and further messages
    # are answered from cache without the LLM). The session also closes for good
    # via POST /end or the maintenance inactivity sweep (abandonment at 5 min).
    session_limit_closed = (
        conversation.captured_data.get(_SESSION_LIMIT_CLOSED_KEY) == "true"
    )
    if (
        prior_status != ConversationStatus.CLOSED
        and conversation.status == ConversationStatus.CLOSED
        and not session_limit_closed
    ):
        logger.info(
            "Consultation finished; keeping session open and returning to start (Architecture A) conversation_id=%s previous_step=%s",
            conversation.conversation_id,
            conversation.current_step,
        )
        _reset_conversation_for_reroute(conversation)
        await store.save_conversation_reference(conversation)

    if (
        prior_status != ConversationStatus.CLOSED
        and conversation.status == ConversationStatus.CLOSED
    ):
        _emit_event("conversation.closed", _build_closed_event(conversation))

    return conversation


@log_execution
async def _run_chat_turn_in_background(
    *,
    content: str,
    conversation_id: str,
    store: ConversationStore,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    control_store: ControlTableStore | None = None,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
) -> Conversation:
    """Execute one chat turn in the background and recover gracefully on errors."""

    conversation: Conversation | None = None
    try:
        customer_id = _extract_customer_id(conversation_id)
        conversation_lock = await _get_conversation_lock(conversation_id)

        async with conversation_lock:
            conversation = await store.load_conversation(conversation_id)

            if conversation is None:
                raise ResourceNotFoundError(
                    "Conversation not found. Start it first using POST /start.",
                    details={"conversation_id": conversation_id},
                )

            conversation.user_id = customer_id

        conversation = await asyncio.wait_for(
            _process_message_turn(
                conversation=conversation,
                content=content,
                store=store,
                workflow_engine=workflow_engine,
                strands_agent=strands_agent,
                control_store=control_store,
                back_data_service_url=back_data_service_url,
                trx_service_url=trx_service_url,
            ),
            timeout=_TURN_HARD_CAP_SECONDS,
        )
        if conversation.status in {ConversationStatus.CLOSED, ConversationStatus.ERROR}:
            await _release_conversation_lock(conversation_id)

        return conversation
    except Exception as error:
        if isinstance(error, asyncio.TimeoutError):
            logger.warning(
                "Background chat turn exceeded hard cap conversation_id=%s seconds=%s",
                conversation_id,
                _TURN_HARD_CAP_SECONDS,
            )
        logger.exception(
            "Background chat turn failed conversation_id=%s",
            conversation_id,
        )
        # Fire-and-forget audit push; never blocks or changes the error outcome.
        _schedule_error_report(conversation_id=conversation_id, error=error)
        _emit_event(
            "conversation.error",
            _build_error_event(conversation_id, error, conversation),
        )
        return await _finalize_background_chat_error(
            conversation_id=conversation_id,
            store=store,
        )


@log_execution
async def _finalize_background_chat_error(
    *,
    conversation_id: str,
    store: ConversationStore,
) -> Conversation:
    """Persist a deterministic assistant error message for a failed async turn."""

    conversation_lock = await _get_conversation_lock(conversation_id)

    async with conversation_lock:
        conversation = await store.load_conversation(conversation_id)

        if conversation is None:
            raise ResourceNotFoundError(
                "Conversation not found. Start it first using POST /start.",
                details={"conversation_id": conversation_id},
            )

        responded_at = datetime.now(UTC)
        latest_user_message = next(
            (
                message
                for message in reversed(conversation.messages)
                if message.role == MessageRole.USER
                and message.timing.responded_at is None
            ),
            None,
        )

        if latest_user_message is not None:
            _finalize_user_message_timing(latest_user_message, responded_at)
            await store.save_message(conversation.conversation_id, latest_user_message)

        assistant_message = _build_assistant_message(
            _ASYNC_CHAT_ERROR_MESSAGE,
            received_at=responded_at,
            responded_at=responded_at,
        )
        conversation.status = ConversationStatus.ERROR
        conversation.add_message(assistant_message)
        await store.save_message(conversation.conversation_id, assistant_message)
        await store.save_conversation_reference(conversation)
        await store.refresh()

    await _release_conversation_lock(conversation_id)
    return conversation


@log_execution
async def process_chat_message_with_timeout(
    *,
    content: str,
    conversation_id: str,
    store: ConversationStore,
    workflow_engine: WorkflowEngine,
    strands_agent: StrandsWorkflowAgent,
    control_store: ControlTableStore | None = None,
    back_data_service_url: str | None = None,
    trx_service_url: str | None = None,
    processing_timeout_seconds: float = _ASYNC_CHAT_TIMEOUT_SECONDS,
) -> Conversation | None:
    """
    Process a chat turn with a soft timeout and keep the work running in background.

    Returns:
        The completed conversation when the turn finishes within the timeout,
        otherwise `None` so the API can answer with `204 No Content`.
    """

    logger.info(
        "Processing chat message with timeout conversation_id=%s content_length=%s timeout_seconds=%s",
        conversation_id,
        len(content),
        processing_timeout_seconds,
    )
    customer_id = _extract_customer_id(conversation_id)
    conversation_lock = await _get_conversation_lock(conversation_id)

    async with conversation_lock:
        conversation = await store.load_conversation(conversation_id)

        if conversation is None:
            raise ResourceNotFoundError(
                "Conversation not found. Start it first using POST /start.",
                details={"conversation_id": conversation_id},
            )

        if conversation.status == ConversationStatus.RUNNING:
            if _is_running_stuck(conversation):
                # Stale RUNNING (no live task): recover and start a fresh turn.
                await _recover_stuck_running(conversation, store, release_lock=False)
            else:
                logger.info(
                    "Conversation already running conversation_id=%s",
                    conversation_id,
                )
                return None

        conversation.user_id = customer_id
        conversation.status = ConversationStatus.RUNNING
        conversation.running_since = datetime.now(UTC)
        await store.save_conversation_reference(conversation)
        await store.refresh()

    background_task = asyncio.create_task(
        _run_chat_turn_in_background(
            content=content,
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            control_store=control_store,
            back_data_service_url=back_data_service_url,
            trx_service_url=trx_service_url,
        )
    )
    await _register_background_chat_task(conversation_id, background_task)

    try:
        return await asyncio.wait_for(
            asyncio.shield(background_task),
            timeout=processing_timeout_seconds,
        )
    except TimeoutError:
        logger.info(
            "Chat processing exceeded timeout conversation_id=%s timeout_seconds=%s",
            conversation_id,
            processing_timeout_seconds,
        )
        return None


@log_execution
async def get_conversation_snapshot(
    *,
    conversation_id: str,
    store: ConversationStore,
) -> Conversation:
    """Load the latest persisted snapshot for a conversation."""

    conversation_lock = await _get_conversation_lock(conversation_id)

    async with conversation_lock:
        conversation = await store.load_conversation(conversation_id)

        if conversation is None:
            raise ResourceNotFoundError(
                "Conversation not found. Start it first using POST /start.",
                details={"conversation_id": conversation_id},
            )

        if _is_running_stuck(conversation):
            # Stale RUNNING with no live task: recover so polling stops waiting.
            await _recover_stuck_running(conversation, store)

        return conversation


@log_execution
def _resolve_end_conversation_callback_url(
    *,
    conversation: Conversation,
    callback_url: str,
) -> str:
    """Resolve URL templates used by the end-conversation callback."""

    return callback_url.replace(
        "{conversation_id}",
        conversation.conversation_id,
    ).replace(
        "{onversation_id}",
        conversation.conversation_id,
    )


@log_execution
async def _notify_end_conversation_callback(
    *,
    conversation: Conversation,
    callback_url: str | None,
) -> None:
    """Ask the maintenance service to archive and free a closed conversation.

    Best-effort: when no URL is configured the call is skipped, and any failure
    is swallowed by the maintenance client so the close always succeeds (the
    maintenance cron archives closed conversations as a fallback).
    """

    if not callback_url:
        logger.info(
            "End conversation maintenance archive skipped because no URL is configured "
            "conversation_id=%s",
            conversation.conversation_id,
        )
        return

    await trigger_archive_conversation(
        base_url=callback_url,
        conversation_id=conversation.conversation_id,
    )


@log_execution
async def process_end_conversation(
    *,
    conversation_id: str,
    store: ConversationStore,
) -> Conversation:
    """Finalize an existing conversation by updating only its reference status."""

    logger.info(
        "Processing end conversation conversation_id=%s",
        conversation_id,
    )

    conversation_lock = await _get_conversation_lock(conversation_id)
    callback_url = load_end_conversation_callback_url()
    should_notify_callback = False

    async with conversation_lock:
        conversation = await store.load_conversation(conversation_id)

        if conversation is None:
            raise ResourceNotFoundError(
                "Conversation not found. Start it first using POST /start.",
                details={"conversation_id": conversation_id},
            )

        if conversation.status == ConversationStatus.CLOSED:
            logger.info(
                "Conversation already closed conversation_id=%s current_step=%s message_count=%s",
                conversation.conversation_id,
                conversation.current_step,
                len(conversation.messages),
            )
            return conversation

        conversation.status = ConversationStatus.CLOSED
        await store.save_conversation_reference(conversation)
        await store.refresh()
        should_notify_callback = True

        logger.info(
            "Completed end conversation conversation_id=%s status=%s current_step=%s message_count=%s",
            conversation.conversation_id,
            conversation.status.value,
            conversation.current_step,
            len(conversation.messages),
        )

    if should_notify_callback:
        await _release_conversation_lock(conversation_id)
        _emit_event("conversation.closed", _build_closed_event(conversation))
        await _notify_end_conversation_callback(
            conversation=conversation,
            callback_url=callback_url,
        )

    return conversation
