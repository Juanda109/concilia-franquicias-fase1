"""Fire-and-forget HTTP client for the co_pqrs_back_maintenance service.

The maintenance service exposes ``POST /end/{conversation_id}`` which archives
(exports to disk) and deletes a closed conversation and its messages, freeing
the deterministic ``user_id_yyyymmdd`` id so the user can open a new session.

The call is best-effort: failures never block the conversation close because the
maintenance cron also archives closed conversations as a fallback.
"""

import httpx

from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)

_MAINTENANCE_TIMEOUT_SECONDS = 5.0


def _correlation_headers() -> dict[str, str]:
    """Propagate the current conversation id so maintenance logs correlate."""

    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        return {"X-Correlation-Id": correlation_id}
    return {}


def _resolve_archive_url(*, base_url: str, conversation_id: str) -> str:
    """Resolve the maintenance archive URL for a conversation.

    Supports both a templated URL (containing ``{conversation_id}``) and a plain
    base URL, in which case ``/end/{conversation_id}`` is appended.
    """

    if "{conversation_id}" in base_url:
        return base_url.replace("{conversation_id}", conversation_id)

    return f"{base_url.rstrip('/')}/end/{conversation_id}"


async def trigger_archive_conversation(
    *,
    base_url: str,
    conversation_id: str,
) -> None:
    """
    Ask the maintenance service to archive and delete a closed conversation,
    freeing its deterministic id for a new session.

    This call is fire-and-forget: all errors are swallowed after logging so the
    close operation always succeeds and the maintenance cron acts as a fallback.
    """

    url = _resolve_archive_url(base_url=base_url, conversation_id=conversation_id)
    logger.info(
        "Triggering maintenance archive conversation_id=%s url=%s",
        conversation_id,
        url,
    )
    try:
        async with httpx.AsyncClient(timeout=_MAINTENANCE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=_correlation_headers())
        logger.info(
            "Maintenance archive accepted conversation_id=%s status=%s",
            conversation_id,
            response.status_code,
        )
    except Exception:
        logger.exception(
            "Maintenance archive notification failed conversation_id=%s url=%s",
            conversation_id,
            url,
        )
