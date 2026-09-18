"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging

from infrastructure.core.logger import get_logger, log_execution
from infrastructure.filesystem.error_report_writer import ErrorReportWriter
from infrastructure.filesystem.request_log_writer import RequestLogWriter
from infrastructure.filesystem.trace_event_writer import TraceEventWriter
from infrastructure.persistence.conversation_store import ConversationStore

conversation_store = ConversationStore()
error_report_writer = ErrorReportWriter()
trace_event_writer = TraceEventWriter()
request_log_writer = RequestLogWriter()
logger = get_logger(__name__)


@log_execution
async def get_app_logger() -> logging.Logger:
    """Return the shared application logger."""

    return get_logger("co_pqrs_back_error_handler.api")


@log_execution
async def get_conversation_store() -> ConversationStore:
    """Return the shared OpenSearch-backed conversation store."""

    return conversation_store


@log_execution
async def get_error_report_writer() -> ErrorReportWriter:
    """Return the shared JSON report writer."""

    return error_report_writer


@log_execution
async def get_trace_event_writer() -> TraceEventWriter:
    """Return the shared trace-event writer."""

    return trace_event_writer


@log_execution
async def get_request_log_writer() -> RequestLogWriter:
    """Return the shared per-request log writer."""

    return request_log_writer
