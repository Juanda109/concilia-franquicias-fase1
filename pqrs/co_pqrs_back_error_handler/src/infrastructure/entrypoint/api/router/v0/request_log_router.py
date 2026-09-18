"""Router for per-request full log ingestion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from application.request_log.request_log_service import record_request_log
from domain.request_log.models import RequestLogCommand
from infrastructure.core.logger import log_execution
from infrastructure.entrypoint.api.dependencies import (
    get_app_logger,
    get_request_log_writer,
)
from infrastructure.entrypoint.api.router.v0.model.request_log_models import (
    RequestLogRequest,
    RequestLogResponse,
)
from infrastructure.filesystem.request_log_writer import RequestLogWriter

router = APIRouter(prefix="/v0/request-logs", tags=["request-logs"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RequestLogResponse,
    summary="Store the full per-request log capture to MinIO (request-logs/ prefix)",
)
@log_execution
async def create_request_log(
    payload: RequestLogRequest,
    logger: logging.Logger = Depends(get_app_logger),
    writer: RequestLogWriter = Depends(get_request_log_writer),
) -> RequestLogResponse:
    """Receive a full per-request log capture and persist it near real-time."""

    logger.info(
        "Received request log component=%s conversation_id=%s segment=%s lines=%s truncated=%s",
        payload.component,
        payload.conversation_id,
        payload.segment,
        payload.line_count,
        payload.truncated,
    )
    record, stored_path = await record_request_log(
        RequestLogCommand(**payload.model_dump()),
        writer=writer,
    )

    return RequestLogResponse(
        request_log_id=record.metadata.request_log_id,
        stored_path=str(stored_path),
        recorded_at=record.metadata.recorded_at,
    )
