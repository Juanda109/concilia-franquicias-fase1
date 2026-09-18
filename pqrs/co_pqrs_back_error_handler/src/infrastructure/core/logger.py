"""Centralized logging helpers."""

from __future__ import annotations

import inspect
import logging
import os
from functools import wraps
from typing import Any, Callable


def configure_logging(level: int | str | None = None) -> None:
    """Configure standard application logging."""

    logging.basicConfig(
        level=level or os.getenv("ERROR_HANDLER_LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=level is not None,
    )


def get_logger(name: str = "co_pqrs_back_error_handler") -> logging.Logger:
    """Return a configured logger instance."""

    configure_logging()
    return logging.getLogger(name)


def log_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    """Log start, end, and failure for sync and async functions."""

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            logger.info("START %s", func.__qualname__)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                logger.exception("FAIL %s", func.__qualname__)
                raise
            logger.info("END %s", func.__qualname__)
            return result

        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = get_logger(func.__module__)
        logger.info("START %s", func.__qualname__)
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception("FAIL %s", func.__qualname__)
            raise
        logger.info("END %s", func.__qualname__)
        return result

    return sync_wrapper
