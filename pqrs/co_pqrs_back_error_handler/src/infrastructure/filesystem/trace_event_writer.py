"""Persist E2E trace events to MinIO (or the local filesystem as fallback).

Mirrors the storage strategy of ``ErrorReportWriter`` but writes lightweight
trace events (one object per event) under a dedicated ``traces/`` prefix, so
the ASO / Postgres end-to-end path is queryable in MinIO near real-time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re

from domain.trace_event.models import TraceEventRecord
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


class TraceEventWriter:
    """Write trace events to a MinIO bucket or to local JSON files."""

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
    async def write_trace_event(self, record: TraceEventRecord) -> Path:
        """Persist the trace event and return the object key or file path."""

        if self.minio_settings.enabled:
            return await asyncio.to_thread(self._write_minio, record)
        return await asyncio.to_thread(self._write_sync, record)

    def _write_minio(self, record: TraceEventRecord) -> Path:
        assert self._object_store is not None  # guaranteed by __init__
        partition = record.metadata.recorded_at.strftime("%Y-%m-%d")
        customer = _customer_folder(record)
        conversation = _safe_path_fragment(record.event.conversation_id or "no-conversation")
        # Time-prefixed file name so a conversation's events sort in order.
        time_prefix = record.metadata.recorded_at.strftime("%H%M%S%f")
        event_name = _safe_path_fragment(
            f"{time_prefix}_{record.event.component or 'svc'}_"
            f"{record.event.operation}_{record.event.outcome}"
        )
        raw_key = (
            f"clients/customer={customer}/dt={partition}/"
            f"conversation={conversation}/{event_name}.json"
        )
        # Global flat summary kept for cross-client analytics/queries.
        summary_key = f"trace-summaries/dt={partition}/{_safe_path_fragment(record.metadata.trace_event_id)}.json"

        try:
            self._object_store.write_json(raw_key, record.model_dump(mode="json"))
            self._object_store.write_ndjson(summary_key, [_build_trace_summary(record)])
        except Exception as exc:  # noqa: BLE001 - normalize to a domain error
            raise ReportPersistenceError(
                "The trace event could not be written to MinIO.",
                details={
                    "bucket": self._object_store.bucket,
                    "key": raw_key,
                    "reason": repr(exc),
                },
            ) from exc

        logger.info(
            "Trace event persisted to MinIO bucket=%s key=%s",
            self._object_store.bucket,
            raw_key,
        )
        return Path(raw_key)

    def _write_sync(self, record: TraceEventRecord) -> Path:
        partition = record.metadata.recorded_at.strftime("%Y-%m-%d")
        customer = _customer_folder(record)
        conversation = _safe_path_fragment(record.event.conversation_id or "no-conversation")
        target_directory = (
            self.settings.output_dir
            / "clients"
            / f"customer={customer}"
            / f"dt={partition}"
            / f"conversation={conversation}"
        )
        time_prefix = record.metadata.recorded_at.strftime("%H%M%S%f")
        file_name = _safe_path_fragment(
            f"{time_prefix}_{record.event.component or 'svc'}_"
            f"{record.event.operation}_{record.event.outcome}"
        ) + ".json"
        file_path = (target_directory / file_name).resolve()

        try:
            target_directory.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                record.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ReportPersistenceError(
                "The trace event could not be written to disk.",
                details={
                    "output_dir": str(self.settings.output_dir),
                    "file_path": str(file_path),
                    "reason": repr(exc),
                },
            ) from exc

        logger.info("Trace event persisted to %s", file_path)
        return file_path


def _build_trace_summary(record: TraceEventRecord) -> dict[str, object | None]:
    """Flatten a trace event into a single analytics-friendly record."""

    event = record.event
    return {
        "trace_event_id": record.metadata.trace_event_id,
        "recorded_at": record.metadata.recorded_at.isoformat(),
        "occurred_at": event.occurred_at.isoformat(),
        "event_type": event.event_type,
        "operation": event.operation,
        "outcome": event.outcome,
        "component": event.component,
        "conversation_id": event.conversation_id,
        "customer_id": event.customer_id,
        "trace_id": event.trace_id,
        "target": event.target,
        "status_code": event.status_code,
        "elapsed_ms": event.elapsed_ms,
        "error_type": event.error_type,
        "error_message": event.error_message,
        "tags": event.tags,
    }


def _safe_path_fragment(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return sanitized or "event"


def _customer_folder(record: TraceEventRecord) -> str:
    """Resolve the customer_id used to partition storage.

    Prefers the explicit customer_id; otherwise derives it from the
    conversation_id (format ``<customer_id>_<YYYYMMDD>``); falls back to
    ``unknown`` so events are never dropped.
    """

    cid = (record.event.customer_id or "").strip()
    if not cid:
        conv = (record.event.conversation_id or "").strip()
        if conv:
            cid = conv.split("_", 1)[0]
    return _safe_path_fragment(cid or "unknown")
