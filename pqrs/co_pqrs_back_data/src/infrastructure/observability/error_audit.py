"""Fire-and-forget error auditing for co_pqrs_back_data.

Pushes structured error reports to the co_pqrs_back_error_handler service (which
persists them to MinIO ``audit-logs``). Best-effort and gated by
``ERROR_HANDLER_SERVICE_URL``: it is a no-op when unset and never raises or
blocks, so auditing can never affect the service or its latency.
"""

from __future__ import annotations

import asyncio
import traceback as _traceback
from typing import Any

import httpx

from infrastructure.core.config import load_error_handler_service_url
from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)

_COMPONENT = "co_pqrs_back_data"
_ERROR_REPORT_PATH = "/v0/error-reports"
_REPORT_TIMEOUT_SECONDS = 5.0

# Strong refs so detached tasks are not garbage-collected before they finish.
_AUDIT_TASKS: set[asyncio.Task[None]] = set()


def _correlation_id() -> str | None:
    correlation_id = get_correlation_id()
    return correlation_id if correlation_id and correlation_id != "-" else None


async def _post_error_report(base_url: str, payload: dict[str, Any]) -> None:
    """POST the report to the error-handler, swallowing all errors."""

    url = f"{base_url.rstrip('/')}{_ERROR_REPORT_PATH}"
    headers = {}
    correlation_id = payload.get("conversation_id") or payload.get("trace_id")
    if correlation_id:
        headers["X-Correlation-Id"] = str(correlation_id)
    try:
        async with httpx.AsyncClient(timeout=_REPORT_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
        logger.info("Error report accepted component=%s status=%s", _COMPONENT, response.status_code)
    except Exception:
        logger.exception("Error report notification failed component=%s url=%s", _COMPONENT, url)


def _spawn(payload: dict[str, Any]) -> None:
    try:
        base_url = load_error_handler_service_url()
    except Exception:
        logger.exception("Could not resolve error-handler URL; skipping audit")
        return

    if not base_url:
        return

    try:
        task = asyncio.create_task(_post_error_report(base_url, payload))
        _AUDIT_TASKS.add(task)
        task.add_done_callback(_AUDIT_TASKS.discard)
    except RuntimeError:
        logger.warning("No running loop to schedule an error audit")
    except Exception:
        logger.exception("Failed to schedule an error audit")


def schedule_error_report(
    *,
    error: BaseException,
    source: str | None = None,
    conversation_id: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Audit an unhandled exception (with traceback). Fire-and-forget."""

    conv_id = conversation_id if conversation_id is not None else _correlation_id()
    extra = dict(extra_context or {})
    extra.setdefault(
        "traceback",
        "".join(_traceback.format_exception(type(error), error, error.__traceback__)),
    )
    _spawn(
        {
            "conversation_id": conv_id,
            "component": _COMPONENT,
            "error_message": str(error) or repr(error),
            "error_type": type(error).__name__,
            "error_source": _COMPONENT,
            "trace_id": conv_id,
            "tags": ["back_data", "auto-audit", "exception"],
            "agent_context": {"source": source} if source else {},
            "extra_context": extra,
        }
    )


def schedule_http_error_report(
    *,
    status_code: int,
    method: str,
    path: str,
    conversation_id: str | None = None,
    detail: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Audit an HTTP error response (status >= threshold). Fire-and-forget."""

    conv_id = conversation_id if conversation_id is not None else _correlation_id()
    error_class = "client_error" if 400 <= status_code < 500 else "server_error"
    _spawn(
        {
            "conversation_id": conv_id,
            "component": _COMPONENT,
            "error_message": detail or f"HTTP {status_code} on {method} {path}",
            "error_type": f"HTTP{status_code}",
            "error_source": _COMPONENT,
            "trace_id": conv_id,
            "tags": ["back_data", "auto-audit", "http", error_class, str(status_code)],
            "agent_context": {
                "source": f"{method} {path}",
                "http_method": method,
                "path": path,
                "status_code": status_code,
                "error_class": error_class,
            },
            "extra_context": dict(extra_context or {}),
        }
    )
