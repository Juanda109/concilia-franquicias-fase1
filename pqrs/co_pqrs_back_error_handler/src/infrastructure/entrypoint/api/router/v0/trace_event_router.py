"""Router for E2E trace-event ingestion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from application.trace_event.trace_event_service import record_trace_event
from domain.trace_event.models import TraceEventCommand
from infrastructure.core.logger import log_execution
from infrastructure.entrypoint.api.dependencies import (
    get_app_logger,
    get_trace_event_writer,
)
from infrastructure.entrypoint.api.router.v0.model.trace_event_models import (
    TraceEventRequest,
    TraceEventResponse,
)
from infrastructure.filesystem.trace_event_writer import TraceEventWriter

router = APIRouter(prefix="/v0/trace-events", tags=["trace-events"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TraceEventResponse,
    summary="Record an E2E trace event (ASO / Postgres / external call) to MinIO",
)
@log_execution
async def create_trace_event(
    payload: TraceEventRequest,
    logger: logging.Logger = Depends(get_app_logger),
    writer: TraceEventWriter = Depends(get_trace_event_writer),
) -> TraceEventResponse:
    """Receive a trace event and persist it near real-time."""

    logger.info(
        "Received trace event type=%s op=%s outcome=%s status=%s conversation_id=%s",
        payload.event_type,
        payload.operation,
        payload.outcome,
        payload.status_code,
        payload.conversation_id,
    )
    record, stored_path = await record_trace_event(
        TraceEventCommand(**payload.model_dump()),
        writer=writer,
    )

    return TraceEventResponse(
        trace_event_id=record.metadata.trace_event_id,
        stored_path=str(stored_path),
        recorded_at=record.metadata.recorded_at,
    )
