"""Persist exported error reports to local JSON files or to MinIO."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re

from domain.error_report.models import ErrorReport
from infrastructure.core.config import (
    MinioSettings,
    ReportStorageSettings,
    load_minio_settings,
    load_report_storage_settings,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import ReportPersistenceError
from infrastructure.storage.object_store import ObjectStore

logger = get_logger(__name__)


class ErrorReportWriter:
    """Write reports to the local filesystem or to a MinIO bucket.

    The backend is selected by ``MinioSettings.enabled``. When MinIO is enabled
    the raw report is stored under ``error-reports/dt=YYYY-MM-DD/<report_id>.json``
    and a flattened NDJSON summary under ``error-summaries/dt=YYYY-MM-DD/``.
    """

    def __init__(
        self,
        settings: ReportStorageSettings | None = None,
        *,
        minio_settings: MinioSettings | None = None,
        object_store: ObjectStore | None = None,
        env_path: str = ".env",
    ) -> None:
        self.settings = settings or load_report_storage_settings(env_path)
        self.minio_settings = minio_settings or load_minio_settings(env_path)
        self._object_store = object_store
        if self.minio_settings.enabled and self._object_store is None:
            self._object_store = ObjectStore(self.minio_settings)

    @log_execution
    async def write_report(self, report: ErrorReport) -> Path:
        """Persist the report and return the file path or object key."""

        if self.minio_settings.enabled:
            return await asyncio.to_thread(self._write_report_minio, report)
        return await asyncio.to_thread(self._write_report_sync, report)

    def _write_report_minio(self, report: ErrorReport) -> Path:
        assert self._object_store is not None  # guaranteed by __init__
        partition = report.metadata.generated_at.strftime("%Y-%m-%d")
        safe_report_id = _safe_path_fragment(report.metadata.report_id)
        raw_key = f"error-reports/dt={partition}/{safe_report_id}.json"
        summary_key = f"error-summaries/dt={partition}/{safe_report_id}.json"

        try:
            self._object_store.write_json(raw_key, report.model_dump(mode="json"))
            self._object_store.write_ndjson(summary_key, [_build_error_summary(report)])
        except Exception as exc:  # noqa: BLE001 - normalize to a domain error
            raise ReportPersistenceError(
                "The error report could not be written to MinIO.",
                details={
                    "bucket": self._object_store.bucket,
                    "key": raw_key,
                    "reason": repr(exc),
                },
            ) from exc

        logger.info("Report persisted to MinIO bucket=%s key=%s", self._object_store.bucket, raw_key)
        return Path(raw_key)

    def _write_report_sync(self, report: ErrorReport) -> Path:
        target_directory = (
            self.settings.output_dir
            / report.metadata.generated_at.strftime("%Y")
            / report.metadata.generated_at.strftime("%m")
            / report.metadata.generated_at.strftime("%d")
        )
        safe_conversation_id = _safe_path_fragment(report.failure.conversation_id)
        file_name = (
            f"{self.settings.file_prefix}_"
            f"{safe_conversation_id}_"
            f"{report.metadata.generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        file_path = (target_directory / file_name).resolve()

        try:
            target_directory.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ReportPersistenceError(
                "The error report could not be written to disk.",
                details={
                    "output_dir": str(self.settings.output_dir),
                    "file_path": str(file_path),
                    "reason": repr(exc),
                },
            ) from exc

        logger.info("Report persisted to %s", file_path)
        return file_path


def _build_error_summary(report: ErrorReport) -> dict[str, object | None]:
    """Flatten an error report into a single analytics-friendly record."""

    analytics = report.analytics
    failure = report.failure
    return {
        "report_id": report.metadata.report_id,
        "generated_at": report.metadata.generated_at.isoformat(),
        "conversation_id": failure.conversation_id,
        "component": failure.component,
        "error_type": failure.error_type,
        "error_source": failure.error_source,
        "trace_id": failure.trace_id,
        "tags": failure.tags,
        "conversation_found": analytics.conversation_found,
        "conversation_status": analytics.conversation_status,
        "general_workflow": analytics.general_workflow,
        "workflow": analytics.workflow,
        "current_step": analytics.current_step,
        "failure_stage": analytics.failure_stage,
        "normalized_error_fingerprint": analytics.normalized_error_fingerprint,
        "normalized_error_hash": analytics.normalized_error_hash,
        "exact_error_hash": analytics.exact_error_hash,
        "parsed_message_count": analytics.parsed_message_count,
        "total_tokens": analytics.total_tokens,
        "conversation_duration_ms": analytics.conversation_duration_ms,
        "reported_delay_ms": analytics.reported_delay_ms,
    }


def _safe_path_fragment(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return sanitized or "service"
