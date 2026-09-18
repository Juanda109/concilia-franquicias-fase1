"""Fire-and-forget error auditing for the maintenance service.

Pushes a structured error report to the co_pqrs_back_error_handler service
(persisted to MinIO ``audit-logs``) when the maintenance job or API fails.

The maintenance service is synchronous and has no httpx dependency, so this uses
the standard library ``urllib``. It is best-effort: gated by
``error_handler_service_url`` and it never raises (so auditing can never break
the maintenance flow).
"""

from __future__ import annotations

import json
import traceback as _traceback
import urllib.error
import urllib.request
from typing import Any

from classes.models import Settings
from commons.logging_utils import get_logger

logger = get_logger(__name__)

_COMPONENT = "co_pqrs_back_maintenance"
_ERROR_REPORT_PATH = "/v0/error-reports"
_REPORT_TIMEOUT_SECONDS = 5.0


def report_job_failure(
    settings: Settings,
    error: BaseException,
    *,
    source: str,
    extra_context: dict[str, Any] | None = None,
) -> None:
    """Send a best-effort error report. Never raises."""

    base_url = (settings.error_handler_service_url or "").rstrip("/")
    if not base_url:
        return

    extra = dict(extra_context or {})
    extra.setdefault(
        "traceback",
        "".join(_traceback.format_exception(type(error), error, error.__traceback__)),
    )
    payload = {
        "conversation_id": None,
        "component": _COMPONENT,
        "error_message": str(error) or repr(error),
        "error_type": type(error).__name__,
        "error_source": _COMPONENT,
        "tags": ["maintenance", "auto-audit", "exception"],
        "agent_context": {"source": source},
        "extra_context": extra,
    }

    url = f"{base_url}{_ERROR_REPORT_PATH}"
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_REPORT_TIMEOUT_SECONDS) as response:
            logger.info(
                "Error report accepted component=%s status=%s",
                _COMPONENT,
                getattr(response, "status", "n/a"),
            )
    except Exception:
        logger.exception(
            "Error report notification failed component=%s url=%s", _COMPONENT, url
        )
