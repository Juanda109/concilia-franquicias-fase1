from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    hosts: list[dict[str, Any]]
    http_auth: tuple[str, str] | None
    verify_certs: bool
    timeout_seconds: int
    default_timezone: str
    conversations_index: str
    messages_index: str
    output_dir: Path
    batch_size: int
    scroll_keepalive: str
    inactive_minutes: int
    conversation_status_field: str
    active_status_value: str
    closed_status_value: str
    conversation_id_field: str | None
    message_conversation_id_field: str
    last_interaction_fields: list[str]
    message_timestamp_fields: list[str]
    closed_at_field: str
    exported_at_field: str
    exported_path_field: str
    locked_at_field: str
    locked_by_field: str
    lock_timeout_seconds: int
    archive_lookup_retries: int
    archive_lookup_retry_seconds: int
    api_token: str | None
    delete_exported_conversations: bool
    delete_exported_messages: bool
    minio_enabled: bool
    minio_endpoint_url: str | None
    minio_bucket: str | None
    minio_region: str
    minio_access_key: str | None
    minio_secret_key: str | None
    minio_addressing_style: str
    control_index: str
    error_handler_service_url: str | None


@dataclass(frozen=True)
class ExportSummary:
    candidates_found: int
    exported_conversations: int
    deleted_conversations: int
    deleted_messages: int
    marked_as_exported: int


@dataclass(frozen=True)
class CloseSummary:
    candidates_found: int
    closed_from_active: int
    skipped_missing_last_interaction: int


@dataclass(frozen=True)
class ArchiveConversationResult:
    status: str
    conversation_id: str | None
    document_id: str | None
    export_relative_path: str | None
    message_count: int
    deleted_messages: int
    deleted_conversation: bool
    marked_as_exported: bool
    detail: str | None = None


@dataclass(frozen=True)
class ControlTableSnapshotSummary:
    clients_scanned: int
    records_written: int
    object_key: str | None
    skipped: bool = False


@dataclass(frozen=True)
class MaintenanceSummary:
    export_summary: ExportSummary
    close_summary: CloseSummary
    control_snapshot: ControlTableSnapshotSummary | None = None
