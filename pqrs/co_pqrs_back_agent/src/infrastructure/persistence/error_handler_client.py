"""Fire-and-forget HTTP client for the co_pqrs_back_error_handler service.

Used to push a structured error report when a chat turn fails. The call never
blocks the conversation and never raises: all errors are swallowed after
logging, so auditing can never affect the agent's latency or behavior.
"""

from __future__ import annotations

from typing import Any

import httpx

from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)

_ERROR_REPORT_PATH = "/v0/error-reports"
_REPORT_TIMEOUT_SECONDS = 5.0


def _correlation_headers() -> dict[str, str]:
    """Propagate the current conversation id so error_handler logs correlate."""

    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        return {"X-Correlation-Id": correlation_id}
    return {}


async def report_agent_error(
    *,
    base_url: str,
    conversation_id: str,
    error_message: str,
    error_type: str | None = None,
    error_source: str = "co_pqrs_back_agent",
    trace_id: str | None = None,
    tags: list[str] | None = None,
    agent_context: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """
    Push a structured error report to the error-handler service.

    This call is fire-and-forget: all errors are swallowed after logging so it
    can never affect the conversation or add latency to the agent.
    """

    url = f"{base_url.rstrip('/')}{_ERROR_REPORT_PATH}"
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "error_message": error_message,
        "error_source": error_source,
        "tags": tags or [],
        "agent_context": agent_context or {},
        "extra_context": extra_context or {},
    }
    if error_type:
        payload["error_type"] = error_type
    if trace_id:
        payload["trace_id"] = trace_id

    logger.info(
        "Reporting agent error to error-handler conversation_id=%s error_type=%s url=%s",
        conversation_id,
        error_type,
        url,
    )
    try:
        async with httpx.AsyncClient(timeout=_REPORT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=payload,
                headers=_correlation_headers(),
            )
        logger.info(
            "Error report accepted conversation_id=%s status=%s",
            conversation_id,
            response.status_code,
        )
    except Exception:
        logger.exception(
            "Error report notification failed conversation_id=%s url=%s",
            conversation_id,
            url,
        )
