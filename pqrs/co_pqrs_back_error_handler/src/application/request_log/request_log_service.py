"""Use case for recording per-request full log captures."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from domain.request_log.models import (
    RequestLogCommand,
    RequestLogMetadata,
    RequestLogRecord,
)
from domain.trace_event.sanitizer import mask_text
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.filesystem.request_log_writer import RequestLogWriter

logger = get_logger(__name__)


@log_execution
async def record_request_log(
    command: RequestLogCommand,
    *,
    writer: RequestLogWriter,
) -> tuple[RequestLogRecord, Path]:
    """Build a request-log record and persist it (MinIO or local fallback)."""

    # Los logs capturados pueden traer PAN o correos en los cuerpos: se enmascaran al persistir.

    command = command.model_copy(update={"log_text": mask_text(command.log_text or "")})

    recorded_at = datetime.now(timezone.utc)
    metadata = RequestLogMetadata(
        request_log_id=_build_request_log_id(command, recorded_at),
        recorded_at=recorded_at,
    )
    record = RequestLogRecord(metadata=metadata, log=command)

    stored_path = await writer.write_request_log(record)

    logger.info(
        "Request log recorded id=%s component=%s conversation_id=%s segment=%s lines=%s truncated=%s",
        metadata.request_log_id,
        command.component,
        command.conversation_id,
        command.segment,
        command.line_count,
        command.truncated,
    )
    return record, stored_path


def _build_request_log_id(command: RequestLogCommand, recorded_at: datetime) -> str:
    timestamp = recorded_at.strftime("%Y%m%dT%H%M%S%fZ")
    base = command.request_id or command.conversation_id or command.customer_id or "req"
    return f"{_safe_fragment(base)}_{_safe_fragment(command.segment)}_{timestamp}"


def _safe_fragment(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return sanitized or "req"
