"""Per-request full log capture -> co_pqrs_back_error_handler (request-logs/ prefix).

Captures the COMPLETE application log stream produced while handling a single
request into an in-memory, context-scoped buffer, then ships it to the
error-handler service, which stores it in MinIO under a SEPARATE
``request-logs/`` prefix, partitioned per customer/conversation. This is kept
apart from the structured trace events (``clients/`` prefix) so neither storage
layout breaks the other.

Opt-in: no-op unless ``REQUEST_LOG_CAPTURE_ENABLED`` is truthy AND
``ERROR_HANDLER_SERVICE_URL`` is configured. Best-effort: never blocks the
request (ships from a short-lived daemon thread) and never raises.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from infrastructure.core.config import load_error_handler_service_url
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

_COMPONENT = "co_pqrs_back_data"
_REQUEST_LOG_PATH = "/v0/request-logs"
_SHIP_TIMEOUT_SECONDS = 5.0
_TRUTHY = {"1", "true", "yes", "on"}

# PII masking (mirrors the ASO masking): emails and long digit runs.
_PII_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PII_DIGITS_RE = re.compile(r"\d{6,}")


def _env_const(name: str) -> str | None:
    """Read from merged .env constants (configmap mounts .env as a file, so
    os.environ alone would NOT see it); falls back to real env vars.
    """
    try:
        from infrastructure.core.config import load_env_constants

        value = load_env_constants().get(name)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        value = os.environ.get(name)
    return value


def capture_enabled() -> bool:
    """Whether per-request full-log capture is turned on for this process."""

    return str(_env_const("REQUEST_LOG_CAPTURE_ENABLED") or "").strip().lower() in _TRUTHY


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(_env_const(name) or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _configured_level() -> int:
    raw = str(_env_const("REQUEST_LOG_CAPTURE_LEVEL") or "INFO").strip().upper() or "INFO"
    level = logging.getLevelName(raw)
    return level if isinstance(level, int) else logging.INFO


def _mask(text: str) -> str:
    text = _PII_EMAIL_RE.sub("***@***", text)
    text = _PII_DIGITS_RE.sub(lambda m: "****" + m.group(0)[-4:], text)
    return text


@dataclass
class _CaptureBuffer:
    request_id: str | None = None
    lines: list[str] = field(default_factory=list)
    byte_count: int = 0
    dropped: int = 0
    truncated: bool = False
    max_lines: int = 3000
    max_bytes: int = 512_000

    def append(self, line: str) -> None:
        if len(self.lines) >= self.max_lines or self.byte_count >= self.max_bytes:
            self.truncated = True
            self.dropped += 1
            return
        self.lines.append(line)
        self.byte_count += len(line) + 1


_capture_ctx: ContextVar[_CaptureBuffer | None] = ContextVar(
    "request_log_capture", default=None
)


class RequestLogCaptureHandler(logging.Handler):
    """Logging handler that appends formatted records to the active buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        buffer = _capture_ctx.get()
        if buffer is None:
            return
        try:
            buffer.append(_mask(self.format(record)))
        except Exception:  # noqa: BLE001 - logging must never break the flow
            pass


_handler_installed = False
_install_lock = threading.Lock()


def install_capture_handler() -> None:
    """Attach the capture handler to the root logger once (idempotent)."""

    global _handler_installed
    if _handler_installed or not capture_enabled():
        return
    with _install_lock:
        if _handler_installed:
            return
        handler = RequestLogCaptureHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        handler.setLevel(_configured_level())
        root = logging.getLogger()
        root.addHandler(handler)
        # Ensure records at the configured level actually reach handlers.
        if root.level == logging.NOTSET or root.level > handler.level:
            root.setLevel(handler.level)
        _handler_installed = True
        logger.info(
            "Request-log capture handler installed level=%s",
            logging.getLevelName(handler.level),
        )


def start_request_capture(request_id: str | None = None) -> Token | None:
    """Begin capturing logs for the current request context."""

    if not capture_enabled():
        return None
    buffer = _CaptureBuffer(
        request_id=request_id,
        max_lines=_int_env("REQUEST_LOG_MAX_LINES", 3000),
        max_bytes=_int_env("REQUEST_LOG_MAX_BYTES", 512_000),
    )
    return _capture_ctx.set(buffer)


def finish_request_capture(token: Token | None) -> _CaptureBuffer | None:
    """Stop capturing, reset the context and return the captured buffer."""

    if token is None:
        return None
    buffer = _capture_ctx.get()
    try:
        _capture_ctx.reset(token)
    except Exception:  # noqa: BLE001
        _capture_ctx.set(None)
    return buffer


def ship_request_log(
    *,
    buffer: _CaptureBuffer | None,
    conversation_id: str | None,
    customer_id: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    elapsed_ms: float | None = None,
    segment: str = "main",
) -> None:
    """Ship the captured request log to the error-handler (fire-and-forget)."""

    if buffer is None or not buffer.lines:
        return
    try:
        base_url = load_error_handler_service_url()
    except Exception:  # noqa: BLE001
        return
    if not base_url:
        return

    log_text = "\n".join(buffer.lines)
    if buffer.truncated:
        log_text += (
            f"\n... [TRUNCATED: {buffer.dropped} more lines dropped "
            f"(caps: max_lines/max_bytes)] ..."
        )

    payload: dict[str, Any] = {
        "component": _COMPONENT,
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "request_id": buffer.request_id,
        "segment": segment,
        "method": method,
        "path": path,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "line_count": len(buffer.lines),
        "truncated": buffer.truncated,
        "log_text": log_text,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "tags": ["request-log", _COMPONENT],
    }

    try:
        threading.Thread(
            target=_post_request_log,
            args=(base_url, payload),
            name="request-log-ship",
            daemon=True,
        ).start()
    except Exception:  # noqa: BLE001
        pass


def _post_request_log(base_url: str, payload: dict[str, Any]) -> None:
    url = f"{base_url.rstrip('/')}{_REQUEST_LOG_PATH}"
    headers: dict[str, str] = {}
    if payload.get("conversation_id"):
        headers["X-Correlation-Id"] = str(payload["conversation_id"])
    try:
        with httpx.Client(timeout=_SHIP_TIMEOUT_SECONDS) as client:
            client.post(url, json=payload, headers=headers)
    except Exception:  # noqa: BLE001 - observability must never break the flow
        logger.debug("Request-log shipping failed url=%s", url)
