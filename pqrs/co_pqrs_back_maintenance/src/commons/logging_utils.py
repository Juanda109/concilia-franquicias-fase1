"""Centralized logging utilities for the maintenance job."""

from __future__ import annotations

import logging
import os
from functools import wraps
from typing import Any, Callable


def configure_logging(level: int | str | None = None) -> None:
    logging.basicConfig(
        level=level or os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=level is not None,
    )


def get_logger(name: str = "maintenance") -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def log_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    """Log START, END and FAIL for relevant sync functions."""

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
