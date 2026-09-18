"""Use case for recording E2E trace events."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from domain.trace_event.models import (
    TraceEventCommand,
    TraceEventMetadata,
    TraceEventRecord,
)
from domain.trace_event.sanitizer import sanitize_trace_event
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.filesystem.trace_event_writer import TraceEventWriter

logger = get_logger(__name__)


@log_execution
async def record_trace_event(
    command: TraceEventCommand,
    *,
    writer: TraceEventWriter,
) -> tuple[TraceEventRecord, Path]:
    """Build a trace-event record and persist it (MinIO or local fallback)."""

    # Ultima barrera: pase lo que pase en el emisor (flags de diagnostico,
    # un cuerpo volcado entero), nada sensible llega al bucket.
    command = TraceEventCommand.model_validate(sanitize_trace_event(command.model_dump(mode="python")))
    recorded_at = datetime.now(timezone.utc)
    metadata = TraceEventMetadata(
        trace_event_id=_build_trace_event_id(command, recorded_at),
        recorded_at=recorded_at,
    )
    record = TraceEventRecord(metadata=metadata, event=command)

    stored_path = await writer.write_trace_event(record)

    logger.info(
        "Trace event recorded id=%s type=%s op=%s outcome=%s status=%s elapsed_ms=%s conversation_id=%s",
        metadata.trace_event_id,
        command.event_type,
        command.operation,
        command.outcome,
        command.status_code,
        command.elapsed_ms,
        command.conversation_id,
    )
    return record, stored_path


def _build_trace_event_id(command: TraceEventCommand, recorded_at: datetime) -> str:
    timestamp = recorded_at.strftime("%Y%m%dT%H%M%S%fZ")
    base = command.conversation_id or command.customer_id or command.component or "event"
    return f"{_safe_fragment(base)}_{_safe_fragment(command.operation)}_{timestamp}"


def _safe_fragment(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return sanitized or "event"
