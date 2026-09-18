"""Centralized logging utilities for the project.

Logs go to STDOUT/STDERR (the terminal / pod logs). Every line carries a
correlation block (``cid``/``cust``/``req``) so a single customer request can be
traced end-to-end (and matched against the agent via ``X-Correlation-Id``).

Discipline (to keep the terminal readable):
- INFO  -> milestones (request in, identity resolved, decision/id_msg, OpenSearch write).
- DEBUG -> detail: full payloads, raw central-risk JSON, per-obligation findings.
- WARNING -> recoverable issues (customer not found, email not sent, fallback).
- ERROR -> something broke the request.

Enable detail with ``CO_PQRS_BACK_DATA_LOG_LEVEL=DEBUG``.
"""

import contextvars
import inspect
import logging
import os
import uuid
from functools import wraps
from typing import Any, Callable

_SERVICE_DEFAULT_NAME = "co_pqrs_back_data"
_LEVEL_ENV_VAR = "CO_PQRS_BACK_DATA_LOG_LEVEL"
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(corr)s | %(message)s"

# --- Correlation context (propagated automatically into every log record) ----
_conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_id", default="-"
)
_customer_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "customer_id", default="-"
)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class _CorrelationFilter(logging.Filter):
    """Inject the current correlation block into each log record as ``corr``."""

    def filter(self, record: logging.LogRecord) -> bool:
        parts: list[str] = []
        conversation_id = _conversation_id_var.get()
        customer_id = _customer_id_var.get()
        request_id = _request_id_var.get()
        if conversation_id and conversation_id != "-":
            parts.append(f"cid={conversation_id}")
        if customer_id and customer_id != "-":
            parts.append(f"cust={customer_id}")
        if request_id and request_id != "-":
            parts.append(f"req={request_id}")
        record.corr = " ".join(parts) if parts else "-"
        return True


_configured = False


def configure_logging(level: int | str | None = None) -> None:
    """Configure root logging to STDOUT with the correlation-aware formatter.

    Idempotent: only reconfigures when an explicit ``level`` is provided.
    """

    global _configured
    if _configured and level is None:
        return

    log_level = level or os.getenv(_LEVEL_ENV_VAR, "INFO")

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_CorrelationFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    _configured = True


def get_logger(name: str = _SERVICE_DEFAULT_NAME) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


# --- Correlation helpers ------------------------------------------------------
def bind_correlation(
    *,
    conversation_id: str | None = None,
    customer_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Bind correlation fields for the current context (request/task)."""

    if conversation_id is not None:
        _conversation_id_var.set(str(conversation_id))
    if customer_id is not None:
        _customer_id_var.set(str(customer_id))
    if request_id is not None:
        _request_id_var.set(str(request_id))


def new_request_id() -> str:
    """Generate and bind a short request id for the current context."""

    request_id = uuid.uuid4().hex[:8]
    _request_id_var.set(request_id)
    return request_id


def get_correlation_id() -> str:
    """Return the current conversation id (or '-' when unset)."""

    return _conversation_id_var.get()


def get_customer_id() -> str:
    """Return the current customer id (or '-' when unset)."""

    return _customer_id_var.get()


def clear_correlation() -> None:
    """Reset correlation fields (call at the end of a request)."""

    _conversation_id_var.set("-")
    _customer_id_var.set("-")
    _request_id_var.set("-")


def log_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    """Log the start, end (DEBUG) and failure (ERROR) of a function or method.

    START/END are emitted at DEBUG to avoid saturating the terminal; failures
    are always logged with the traceback.
    """

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            logger.debug("START %s", func.__qualname__)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.exception("FAIL %s", func.__qualname__)
                raise

            logger.debug("END %s", func.__qualname__)
            return result

        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = get_logger(func.__module__)
        logger.debug("START %s", func.__qualname__)
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception("FAIL %s", func.__qualname__)
            raise

        logger.debug("END %s", func.__qualname__)
        return result

    return sync_wrapper


logger = get_logger()
