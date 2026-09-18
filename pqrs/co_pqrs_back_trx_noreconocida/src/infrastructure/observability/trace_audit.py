"""Emisión fire-and-forget de trace-events E2E para co_pqrs_back_trx_noreconocida.

Envía eventos estructurados (ASO / Postgres / recurrencia, éxito Y error) al
co_pqrs_back_error_handler, que los persiste en MinIO (bucket ``audit-logs``,
prefijo ``clients/customer=.../conversation=.../``) casi en tiempo real.

Restricciones:
- Nunca bloquea ni lanza (observabilidad no puede afectar el flujo).
- Funciona desde cualquier contexto (hilo daemon con POST síncrono).
- No-op si ``ERROR_HANDLER_SERVICE_URL`` no está configurado.
- Los secretos (``tsec``, passwords) los quita el que llama antes de emitir.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

from infrastructure.core.config import load_error_handler_service_url
from infrastructure.core.logger import get_correlation_id, get_logger

logger = get_logger(__name__)

_COMPONENT = "co_pqrs_back_trx_noreconocida"
_TRACE_PATH = "/v0/trace-events"
_TRACE_TIMEOUT_SECONDS = 5.0

_PII_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PII_DIGITS_RE = re.compile(r"\d{6,}")


def _clean(value: str | None) -> str | None:
    return value if value and value != "-" else None


# --- Toggles ----------------------------------------------------------------
def aso_trace_full_body() -> bool:
    return str(os.getenv("ASO_TRACE_FULL_BODY") or "false").strip().casefold() in {"1", "true", "yes", "on"}


def e2e_debug_enabled() -> bool:
    return str(os.getenv("E2E_DEBUG_TRACE") or "false").strip().casefold() in {"1", "true", "yes", "on"}


def trace_body_maxlen() -> int:
    try:
        return max(200, int(str(os.getenv("TRACE_BODY_MAXLEN") or "4000").strip()))
    except (TypeError, ValueError):
        return 4000


def mask_pii(text: str) -> str:
    """Enmascara emails y corridas largas de dígitos (docs/PAN) dejando los últimos 4."""
    text = _PII_EMAIL_RE.sub("***@***", text or "")
    text = _PII_DIGITS_RE.sub(lambda m: "****" + m.group(0)[-4:], text)
    return text


def url_completa(url: str | None, params: dict[str, Any] | None = None) -> str | None:
    """URL con su query string. Nunca lanza: si no se puede armar, devuelve la base."""
    if not url:
        return None
    try:
        return str(httpx.URL(url).copy_merge_params(params or {}))
    except Exception:  # noqa: BLE001 - observabilidad nunca rompe el flujo
        return url


def resumen_peticion(
    method: str | None, url: str | None, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`request_summary` con el mismo formato de las trazas del ASO.

    Mismas claves que `aso_client._request_debug` (`method`, `url`, `url_completa`,
    `params`), para que un evento de endpoint se lea igual que el de
    financial-overview. Sin URL (paso que no llama a nadie) devuelve `{}`.
    """
    if not url:
        return {}
    return {
        "method": method,
        "url": url,
        "url_completa": url_completa(url, params),
        "params": dict(params or {}),
    }


def body_snapshot(payload: Any) -> dict[str, Any]:
    """Snapshot enmascarado+truncado del body para tracing (según ASO_TRACE_FULL_BODY)."""
    import json as _json

    try:
        text = payload if isinstance(payload, str) else _json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        text = str(payload)
    full_len = len(text or "")
    snap: dict[str, Any] = {"body_length": full_len}
    if aso_trace_full_body():
        limit = trace_body_maxlen()
        snap["body_masked"] = mask_pii((text or "")[:limit])
        snap["body_truncated"] = full_len > limit
    return snap


def _post_trace_event(base_url: str, payload: dict[str, Any]) -> None:
    url = f"{base_url.rstrip('/')}{_TRACE_PATH}"
    headers = {}
    correlation_id = payload.get("conversation_id") or payload.get("trace_id")
    if correlation_id:
        headers["X-Correlation-Id"] = str(correlation_id)
    try:
        with httpx.Client(timeout=_TRACE_TIMEOUT_SECONDS) as client:
            client.post(url, json=payload, headers=headers)
    except Exception:  # noqa: BLE001 - observabilidad nunca rompe el flujo
        logger.debug("Trace event notification failed url=%s op=%s", url, payload.get("operation"))


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
        threading.Thread(
            target=_post_trace_event, args=(base_url, payload), name="trx-trace-emit", daemon=True
        ).start()
    except Exception:  # noqa: BLE001
        logger.debug("Failed to schedule trace event op=%s", operation)
