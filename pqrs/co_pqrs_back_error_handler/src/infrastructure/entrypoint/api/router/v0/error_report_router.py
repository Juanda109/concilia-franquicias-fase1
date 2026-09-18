"""Router for error report generation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from application.error_report.error_report_service import generate_error_report
from domain.error_report.models import ErrorReportCommand
from infrastructure.core.logger import log_execution
from infrastructure.entrypoint.api.dependencies import (
    get_app_logger,
    get_conversation_store,
    get_error_report_writer,
)
from infrastructure.entrypoint.api.router.v0.model.error_report_models import (
    ErrorReportRequest,
    ErrorReportResponse,
)
from infrastructure.filesystem.error_report_writer import ErrorReportWriter
from infrastructure.persistence.conversation_store import ConversationStore

router = APIRouter(prefix="/v0/error-reports", tags=["error-reports"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ErrorReportResponse,
    summary="Generate a local JSON error report from a conversation id",
)
@log_execution
async def create_error_report(
    payload: ErrorReportRequest,
    logger: logging.Logger = Depends(get_app_logger),
    store: ConversationStore = Depends(get_conversation_store),
    writer: ErrorReportWriter = Depends(get_error_report_writer),
) -> ErrorReportResponse:
    """Receive an agent failure, recover the conversation, and export the report."""

    logger.info(
        "Received error report request conversation_id=%s error_type=%s trace_id=%s",
        payload.conversation_id,
        payload.error_type,
        payload.trace_id,
    )
    stored_report = await generate_error_report(
        ErrorReportCommand(**payload.model_dump()),
        store=store,
        writer=writer,
    )

    return ErrorReportResponse(
        report_id=stored_report.report.metadata.report_id,
        conversation_id=payload.conversation_id,
        conversation_found=stored_report.report.analytics.conversation_found,
        exported_file_path=str(stored_report.exported_file_path),
        generated_at=stored_report.report.metadata.generated_at,
        analytics=stored_report.report.analytics,
    )
