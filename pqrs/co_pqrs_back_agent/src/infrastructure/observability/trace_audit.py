"""Fire-and-forget E2E trace emission for co_pqrs_back_agent.

Pushes structured trace events (agent -> back_data calls, success AND failure)
to the co_pqrs_back_error_handler service, which persists them to MinIO near
real-time (bucket ``audit-logs``, prefix ``traces/``).

Best-effort: never blocks, never raises, and is a no-op when
``ERROR_HANDLER_SERVICE_URL`` is unset. Emitted from a short-lived daemon thread
(synchronous POST) so it works from any context.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import httpx

from infrastructure.core.config import load_error_handler_service_url
from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)

_COMPONENT = "co_pqrs_back_agent"
_TRACE_PATH = "/v0/trace-events"
_TRACE_TIMEOUT_SECONDS = 5.0


def _clean(value: str | None) -> str | None:
    return value if value and value != "-" else None


def _post_trace_event(base_url: str, payload: dict[str, Any]) -> None:
    url = f"{base_url.rstrip('/')}{_TRACE_PATH}"
    headers = {}
    correlation_id = payload.get("conversation_id") or payload.get("trace_id")
    if correlation_id:
        headers["X-Correlation-Id"] = str(correlation_id)
    try:
        with httpx.Client(timeout=_TRACE_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload, headers=headers)
        logger.debug(
            "Trace event accepted component=%s op=%s status=%s",
            _COMPONENT,
            payload.get("operation"),
            response.status_code,
        )
    except Exception:  # noqa: BLE001 - observability must never break the flow
        logger.debug(
            "Trace event notification failed component=%s url=%s op=%s",
            _COMPONENT,
            url,
            payload.get("operation"),
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
    """Emit a trace event (fire-and-forget). Safe from any context."""

    try:
        base_url = load_error_handler_service_url()
    except Exception:  # noqa: BLE001
        logger.debug("Could not resolve error-handler URL; skipping trace event")
        return

    if not base_url:
        return

    conv_id = conversation_id if conversation_id is not None else _clean(get_correlation_id())

    payload: dict[str, Any] = {
        "event_type": event_type,
        "operation": operation,
        "outcome": outcome,
        "component": _COMPONENT,
        "conversation_id": conv_id,
        "customer_id": customer_id,
        "trace_id": conv_id,
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
        thread = threading.Thread(
            target=_post_trace_event,
            args=(base_url, payload),
            name="trace-event-emit",
            daemon=True,
        )
        thread.start()
    except Exception:  # noqa: BLE001
        logger.debug("Failed to schedule a trace event op=%s", operation)
