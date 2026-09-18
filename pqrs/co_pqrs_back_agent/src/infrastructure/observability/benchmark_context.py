"""Captura de metricas de ruteo para el benchmark (opt-in, fire-and-forget).

Mide la ventana "llegada del request -> workflow decidido" sin alterar el turno.

El valor de la ContextVar es un DICT MUTABLE a proposito: el turno corre dentro
de una tarea creada con `asyncio.create_task`, que COPIA el contexto. Un `.set()`
dentro de la tarea no sube al padre, pero mutar el dict compartido si, porque
ambos contextos apuntan al mismo objeto (mismo patron que el `_CaptureBuffer` de
`request_log_capture`).

Todo es best-effort: ninguna funcion lanza y todas son no-op cuando el modo
benchmark esta apagado.
"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar, Token
from typing import Any

from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

# Cabecera que el cliente envia para pedir metricas, y la que se devuelve.
BENCHMARK_REQUEST_HEADER = "x-benchmark-mode"
BENCHMARK_HEADER = "X-Benchmark-Data"

_benchmark_ctx: ContextVar[dict[str, Any] | None] = ContextVar(
    "benchmark_ctx", default=None
)


def start_capture() -> Token | None:
    """Abrir la ventana de medicion (t0) y devolver el token para el reset."""

    try:
        return _benchmark_ctx.set({"_t0": time.perf_counter()})
    except Exception:  # noqa: BLE001 - la observabilidad nunca rompe el flujo
        return None


def is_active() -> bool:
    """True cuando la peticion (o la tarea hija) corre en modo benchmark.

    Sirve de fallback para etiquetar ``source="benchmark"`` en los eventos de
    analitica cuando la conversacion no trae la marca persistida. Nunca lanza.
    """

    try:
        return _benchmark_ctx.get() is not None
    except Exception:  # noqa: BLE001
        return False


def finish_capture(
    token: Token | None, *, complete_in_flow: bool = False
) -> dict[str, Any] | None:
    """Cerrar la ventana y devolver lo capturado, sin las claves internas.

    Con ``complete_in_flow`` una captura que quedo abierta (el turno respondio por
    una salida que no paso por ``mark_routing_done`` ni ``mark_final_step``, como
    la pregunta de satisfaccion o una transicion de paso) se completa con lo
    minimo: sin ruteo, 0 ms, desenlace ``in_flow``. Es el mismo criterio que
    aplica ``mark_final_step``. Sin cabecera el benchmark no puede seguir una
    conversacion de varios turnos y da el caso por no resuelto.
    """

    if token is None:
        return None

    data = _benchmark_ctx.get()
    try:
        _benchmark_ctx.reset(token)
    except Exception:  # noqa: BLE001
        pass

    if not data:
        return None
    if "routing_time_ms" not in data:
        if not complete_in_flow:
            return None
        data = dict(data)
        data["routing_time_ms"] = 0.0
        data.setdefault("workflow_result", "")
        data["routing_outcome"] = data.get("routing_outcome") or "in_flow"
        data.setdefault("llm_token_input", 0)
        data.setdefault("llm_token_cached", 0)
        data.setdefault("llm_token_output", 0)
        data.setdefault("current_step", "")
        data.setdefault("response_source", "")
    return {key: value for key, value in data.items() if not key.startswith("_")}


def set_model(model_id: str) -> None:
    """Registrar el modelo usado en el turno."""

    data = _benchmark_ctx.get()
    if data is not None:
        data["llm_model"] = model_id


def mark_routing_decision(decision: Any) -> None:
    """Registrar lo que decidio el LLM, ANTES de los overrides del flujo."""

    data = _benchmark_ctx.get()
    if data is None:
        return

    try:
        data["workflow_llm"] = getattr(decision, "workflow", "") or ""
        data["confidence"] = getattr(decision, "confidence", "none")
    except Exception:  # noqa: BLE001
        logger.debug("No se pudo registrar la decision de ruteo del benchmark")


def mark_routing_done(conversation: Any, turn_usage: Any) -> None:
    """Cerrar t1: workflow definitivo, desenlace, tokens y tiempo de ruteo.

    IDEMPOTENTE: solo cuenta la PRIMERA llamada, de modo que se puede invocar
    desde varias salidas de `_resolve_start_phase` sin falsear el tiempo.
    """

    data = _benchmark_ctx.get()
    if data is None or "routing_time_ms" in data:
        return

    try:
        data["routing_time_ms"] = round((time.perf_counter() - data["_t0"]) * 1000, 2)
        data["workflow_result"] = getattr(conversation, "workflow", None) or ""
        data["routing_outcome"] = (
            getattr(conversation, "captured_data", None) or {}
        ).get("routing_outcome", "")
        data["llm_token_input"] = getattr(turn_usage, "input_tokens", 0)
        # Porcion servida desde el cache de prefijo. Es SUBCONJUNTO de
        # llm_token_input, no se suma aparte. Sin esto el benchmark informa
        # cache_hit_pct = 0, que no es "no hubo cache" sino "no se midio".
        data["llm_token_cached"] = getattr(turn_usage, "cached_input_tokens", 0)
        data["llm_token_output"] = getattr(turn_usage, "output_tokens", 0)
        _mark_response_source(data, conversation)
    except Exception:  # noqa: BLE001
        logger.debug("No se pudo cerrar la captura del benchmark")


def mark_final_step(conversation: Any) -> None:
    """Anotar el paso en que quedo la conversacion al cerrar el turno.

    Lo usan los datasets de bypass del benchmark: un caso falla si la
    conversacion termina en un terminal de abono, bloqueo o reexpedicion
    (``forbid_steps``). Ultima llamada gana; no-op sin captura activa.
    """

    data = _benchmark_ctx.get()
    if data is None:
        return
    try:
        data["current_step"] = getattr(conversation, "current_step", "") or ""
        # Turno DENTRO del flujo (sin ruteo): antes no se emitia cabecera y el
        # benchmark no podia seguir una conversacion multiturno (bypass). Se
        # completa lo minimo para que la cabecera salga: workflow, desenlace
        # y un tiempo de ruteo de 0 ms, que es lo honesto cuando no hubo ruteo.
        if "routing_time_ms" not in data:
            data["routing_time_ms"] = 0.0
            data["workflow_result"] = getattr(conversation, "workflow", None) or ""
            captured = getattr(conversation, "captured_data", None) or {}
            data["routing_outcome"] = captured.get("routing_outcome", "") or "in_flow"
            data.setdefault("llm_token_input", 0)
            data.setdefault("llm_token_cached", 0)
            data.setdefault("llm_token_output", 0)
        _mark_response_source(data, conversation)
    except Exception:  # noqa: BLE001
        logger.debug("No se pudo anotar el paso final del benchmark")


def _mark_response_source(data: dict[str, Any], conversation: Any) -> None:
    """Quien redacto el ultimo texto que vio el cliente.

    ``model`` cuando lo escribio el LLM (cierre generativo), ``local_fallback_*``
    cuando cayo al respaldo local y vacio cuando fue el texto aprobado del YAML.
    Lo usa el dataset de grounding del benchmark: un cierre fiel a la fuente
    solo se puede acreditar al modelo si el modelo lo escribio.
    """

    captured = getattr(conversation, "captured_data", None) or {}
    data["response_source"] = str(captured.get("llm_response_source", "") or "")


def encode_header(data: dict[str, Any]) -> str:
    """Serializar compacto para caber holgado en una cabecera HTTP."""

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
