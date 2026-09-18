"""Centralized, fire-and-forget error auditing.

A single place that pushes structured error reports to the error-handler service
(which persists them to MinIO ``audit-logs``). It is used from:

- the global HTTP middleware (every unhandled exception and every error response),
- the request-validation handler (malformed payloads, e.g. a bad conversation id),
- the background chat turn (failures after the async timeout).

All functions are best-effort and NEVER raise or block: they are no-ops when no
error-handler URL is configured, and every failure is swallowed after logging.
"""

from __future__ import annotations

import asyncio
import traceback as _traceback
from typing import Any

from infrastructure.core.config import load_error_handler_service_url
from infrastructure.core.logger import get_correlation_id, get_logger
from infrastructure.persistence.error_handler_client import report_agent_error

logger = get_logger(__name__)

# Strong references so the event loop does not garbage-collect detached tasks.
_AUDIT_TASKS: set[asyncio.Task[None]] = set()


def _spawn(coro) -> None:
    """Schedule a coroutine as a detached, reference-held task. Never raises."""

    try:
        task = asyncio.create_task(coro)
        _AUDIT_TASKS.add(task)
        task.add_done_callback(_AUDIT_TASKS.discard)
    except RuntimeError:
        # No running event loop (called outside async context). Skip silently.
        logger.warning("No running loop available to schedule an error audit")
        coro.close()
    except Exception:
        logger.exception("Failed to schedule an error audit")


def _format_traceback(error: BaseException) -> str:
    return "".join(
        _traceback.format_exception(type(error), error, error.__traceback__)
    )


def schedule_error_report(
    *,
    conversation_id: str | None,
    error: BaseException,
    source: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Audit an unhandled exception (with traceback). Fire-and-forget."""

    try:
        base_url = load_error_handler_service_url()
    except Exception:
        logger.exception("Could not resolve error-handler URL; skipping error audit")
        return

    if not base_url:
        return

    extra = dict(extra_context or {})
    extra.setdefault("traceback", _format_traceback(error))

    agent_context: dict[str, Any] = {}
    if source:
        agent_context["source"] = source

    _spawn(
        report_agent_error(
            base_url=base_url,
            conversation_id=conversation_id or "unknown",
            error_message=str(error) or repr(error),
            error_type=type(error).__name__,
            error_source="co_pqrs_back_agent",
            trace_id=get_correlation_id() or None,
            tags=["agent", "auto-audit", "exception"],
            agent_context=agent_context,
            extra_context=extra,
        )
    )


def schedule_http_error_report(
    *,
    conversation_id: str | None,
    status_code: int,
    method: str,
    path: str,
    detail: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Audit an HTTP error response (status >= threshold). Fire-and-forget.

    Covers handled client errors (e.g. bad/malformed conversation id -> 406,
    not found -> 404, conflict -> 409) and server errors that became responses.
    """

    try:
        base_url = load_error_handler_service_url()
    except Exception:
        logger.exception("Could not resolve error-handler URL; skipping http audit")
        return

    if not base_url:
        return

    error_class = "client_error" if 400 <= status_code < 500 else "server_error"
    agent_context: dict[str, Any] = {
        "source": f"{method} {path}",
        "http_method": method,
        "path": path,
        "status_code": status_code,
        "error_class": error_class,
    }

    _spawn(
        report_agent_error(
            base_url=base_url,
            conversation_id=conversation_id or "unknown",
            error_message=detail or f"HTTP {status_code} on {method} {path}",
            error_type=f"HTTP{status_code}",
            error_source="co_pqrs_back_agent",
            trace_id=get_correlation_id() or None,
            tags=["agent", "auto-audit", "http", error_class, str(status_code)],
            agent_context=agent_context,
            extra_context=dict(extra_context or {}),
        )
    )
