"""Trazas del servicio de autorizacion hacia error_handler -> MinIO.

Misma via que el resto del pipeline (agente, TXNR): un POST fire-and-forget a
``ERROR_HANDLER_SERVICE_URL/v0/trace-events`` con el mismo contrato de payload,
para que el flujo OOB sea auditable de punta a punta por MinIO.

- No-op si ``ERROR_HANDLER_SERVICE_URL`` no esta configurado.
- La observabilidad NUNCA rompe el flujo: cualquier error se traga.
- Async (httpx.AsyncClient) porque el servicio corre en un loop asyncio; se
  lanza como tarea desprendida y no se espera.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from infrastructure.core.config import load_error_handler_service_url

logger = logging.getLogger(__name__)

_COMPONENT = "co_pqrs_authorization"
_TRACE_PATH = "/v0/trace-events"
_TRACE_TIMEOUT_SECONDS = 5.0


async def _post_trace_event(base_url: str, payload: dict[str, Any]) -> None:
    url = f"{base_url.rstrip('/')}{_TRACE_PATH}"
    headers: dict[str, str] = {}
    correlation_id = payload.get("conversation_id") or payload.get("trace_id")
    if correlation_id:
        headers["X-Correlation-Id"] = str(correlation_id)
    try:
        async with httpx.AsyncClient(timeout=_TRACE_TIMEOUT_SECONDS) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception:  # noqa: BLE001 - observabilidad nunca rompe el flujo
        logger.debug(
            "Trace event notification failed url=%s op=%s",
            url, payload.get("operation"),
        )


def schedule_trace_event(
    *,
    event_type: str,
    operation: str,
    outcome: str = "ok",
    status_code: int | None = None,
    elapsed_ms: float | None = None,
    target: str | None = None,
    request_summary: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    conversation_id: str | None = None,
    customer_id: str | None = None,
    tags: list[str] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Emite un trace-event (fire-and-forget). Seguro desde cualquier contexto."""

    try:
        base_url = load_error_handler_service_url()
    except Exception:  # noqa: BLE001
        return
    if not base_url:
        return

    payload: dict[str, Any] = {
        "event_type": event_type,
        "operation": operation,
        "outcome": outcome,
        "component": _COMPONENT,
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "trace_id": conversation_id,
        "target": target,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "request_summary": dict(request_summary or {}),
        "response_summary": dict(response_summary or {}),
        "error_type": error_type,
        "error_message": error_message,
        "tags": list(tags or []),
        "extra_context": dict(extra_context or {}),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Sin loop en marcha (p. ej. un test sincrono): se emite en un loop
        # efimero, sin bloquear al llamador mas alla del propio POST.
        try:
            asyncio.run(_post_trace_event(base_url, payload))
        except Exception:  # noqa: BLE001
            logger.debug("Failed to emit trace event op=%s", operation)
        return
    # Tarea desprendida: no se espera, no rompe el flujo si falla.
    task = loop.create_task(_post_trace_event(base_url, payload))
    # evita el warning de tarea sin referencia; se descarta al terminar
    task.add_done_callback(lambda _t: None)
