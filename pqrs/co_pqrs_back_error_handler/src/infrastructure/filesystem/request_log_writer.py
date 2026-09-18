"""Persist per-request full log captures to MinIO (or local fs as fallback).

Writes one ``.log`` object per captured request under a DEDICATED
``request-logs/`` prefix, partitioned per customer / conversation, kept
SEPARATE from the structured trace events (``clients/`` prefix) so the two
storage layouts never interfere.

Key layout:
  request-logs/customer=<id>/dt=<YYYY-MM-DD>/conversation=<conv>/<req>_<HHMMSSffffff>_<segment>.log
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from domain.request_log.models import RequestLogRecord
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


class RequestLogWriter:
    """Write per-request log captures to a MinIO bucket or to local files."""

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
    async def write_request_log(self, record: RequestLogRecord) -> Path:
        """Persist the request log and return the object key or file path."""

        if self.minio_settings.enabled:
            return await asyncio.to_thread(self._write_minio, record)
        return await asyncio.to_thread(self._write_sync, record)

    def _relative_key(self, record: RequestLogRecord) -> str:
        partition = record.metadata.recorded_at.strftime("%Y-%m-%d")
        customer = _customer_folder(record)
        conversation = _safe_path_fragment(
            record.log.conversation_id or "no-conversation"
        )
        time_prefix = record.metadata.recorded_at.strftime("%H%M%S%f")
        req = _safe_path_fragment(record.log.request_id or "req")
        segment = _safe_path_fragment(record.log.segment or "main")
        file_name = f"{req}_{time_prefix}_{segment}.log"
        return (
            f"request-logs/customer={customer}/dt={partition}/"
            f"conversation={conversation}/{file_name}"
        )

    def _write_minio(self, record: RequestLogRecord) -> Path:
        assert self._object_store is not None  # guaranteed by __init__
        key = self._relative_key(record)
        try:
            self._object_store.write_text(key, record.log.log_text)
        except Exception as exc:  # noqa: BLE001 - normalize to a domain error
            raise ReportPersistenceError(
                "The request log could not be written to MinIO.",
                details={
                    "bucket": self._object_store.bucket,
                    "key": key,
                    "reason": repr(exc),
                },
            ) from exc

        logger.info(
            "Request log persisted to MinIO bucket=%s key=%s bytes=%s lines=%s truncated=%s",
            self._object_store.bucket,
            key,
            len(record.log.log_text.encode("utf-8")),
            record.log.line_count,
            record.log.truncated,
        )
        return Path(key)

    def _write_sync(self, record: RequestLogRecord) -> Path:
        key = self._relative_key(record)
        file_path = (self.settings.output_dir / key).resolve()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(record.log.log_text, encoding="utf-8")
        except OSError as exc:
            raise ReportPersistenceError(
                "The request log could not be written to disk.",
                details={
                    "output_dir": str(self.settings.output_dir),
                    "file_path": str(file_path),
                    "reason": repr(exc),
                },
            ) from exc

        logger.info("Request log persisted to %s", file_path)
        return file_path


def _safe_path_fragment(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return sanitized or "log"


def _customer_folder(record: RequestLogRecord) -> str:
    """Resolve the customer_id used to partition storage.

    Prefers the explicit customer_id; otherwise derives it from the
    conversation_id (format ``<customer_id>_<YYYYMMDD>``); falls back to
    ``unknown`` so logs are never dropped.
    """

    cid = (record.log.customer_id or "").strip()
    if not cid:
        conv = (record.log.conversation_id or "").strip()
        if conv:
            cid = conv.split("_", 1)[0]
    return _safe_path_fragment(cid or "unknown")
