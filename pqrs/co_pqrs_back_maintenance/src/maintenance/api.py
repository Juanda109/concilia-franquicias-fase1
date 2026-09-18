from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from classes.models import ArchiveConversationResult, Settings
from commons.logging_utils import configure_logging, get_logger
from commons.error_audit import report_job_failure
from commons.opensearch_helpers import build_client, log_connection_help
from maintenance.services import archive_conversation_by_id
from settings.config import load_settings


configure_logging()
logger = get_logger(__name__)
app = FastAPI(
    title="Conversation Maintenance API",
    version="0.2.0",
)


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_client() -> OpenSearch:
    return build_client(get_settings())


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/end/{conversation_id}")
def archive_conversation_endpoint(
    conversation_id: str,
    x_maintenance_token: str | None = Header(default=None),
) -> dict[str, object | None]:
    settings = get_settings()
    validate_api_token(settings, x_maintenance_token)

    try:
        result = archive_conversation_by_id(
            client=get_client(),
            settings=settings,
            conversation_id=conversation_id,
            now=datetime.now(UTC),
        )
    except OpenSearchConnectionError as error:
        log_connection_help(settings)
        report_job_failure(settings, error, source=f"POST /end/{conversation_id}")
        raise HTTPException(status_code=503, detail="Could not connect to OpenSearch") from None
    except Exception as error:
        report_job_failure(settings, error, source=f"POST /end/{conversation_id}")
        raise

    status_code = map_result_status_code(result)
    logger.info(
        "Archive endpoint processed conversation_id=%s status=%s detail=%s",
        conversation_id,
        result.status,
        result.detail,
    )
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=serialize_result(result))

    return JSONResponse(status_code=status_code, content=serialize_result(result))


def validate_api_token(settings: Settings, provided_token: str | None) -> None:
    if settings.api_token is None:
        return

    if provided_token == settings.api_token:
        return

    raise HTTPException(status_code=401, detail="Invalid maintenance token")


def map_result_status_code(result: ArchiveConversationResult) -> int:
    if result.status in {"archived", "already_exported"}:
        return 200
    if result.status == "already_processing":
        return 202
    if result.status in {"ambiguous", "not_closed"}:
        return 409
    if result.status == "not_found":
        return 404
    return 500


def serialize_result(result: ArchiveConversationResult) -> dict[str, object | None]:
    return {
        "status": result.status,
        "conversation_id": result.conversation_id,
        "document_id": result.document_id,
        "export_relative_path": result.export_relative_path,
        "message_count": result.message_count,
        "deleted_messages": result.deleted_messages,
        "deleted_conversation": result.deleted_conversation,
        "marked_as_exported": result.marked_as_exported,
        "detail": result.detail,
    }
