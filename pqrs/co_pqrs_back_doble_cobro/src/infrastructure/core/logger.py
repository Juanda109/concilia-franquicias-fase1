"""Centralized logging utilities (same pattern as the other co_pqrs_back_* services).

Logs go to STDOUT, with a correlation block (``cid``/``req``) so a conversation can
be traced end-to-end across services.
"""

from __future__ import annotations

import contextvars
import logging
import os
import uuid
from functools import wraps
from typing import Any, Callable

_LEVEL_ENV_VAR = "DOBLE_COBRO_LOG_LEVEL"
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(corr)s | %(message)s"

_conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_id", default="-"
)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        parts: list[str] = []
        conversation_id = _conversation_id_var.get()
        request_id = _request_id_var.get()
        if conversation_id and conversation_id != "-":
            parts.append(f"cid={conversation_id}")
        if request_id and request_id != "-":
            parts.append(f"req={request_id}")
        record.corr = " ".join(parts) if parts else "-"
        return True


_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    level_name = (os.getenv(_LEVEL_ENV_VAR) or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_CorrelationFilter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def bind_correlation(conversation_id: str | None = None, request_id: str | None = None) -> None:
    if conversation_id:
        _conversation_id_var.set(conversation_id)
    if request_id:
        _request_id_var.set(request_id)


def clear_correlation() -> None:
    _conversation_id_var.set("-")
    _request_id_var.set("-")


def log_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that logs entry/exit of a function (sync or async)."""

    logger = get_logger(func.__module__)

    @wraps(func)
    async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("-> %s", func.__qualname__)
        result = await func(*args, **kwargs)
        logger.debug("<- %s", func.__qualname__)
        return result

    @wraps(func)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("-> %s", func.__qualname__)
        result = func(*args, **kwargs)
        logger.debug("<- %s", func.__qualname__)
        return result

    import inspect

    return _async_wrapper if inspect.iscoroutinefunction(func) else _sync_wrapper
