"""Domain models for exported error reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.conversation.models import Conversation, Message


class ErrorReportCommand(BaseModel):
    """Input data needed to generate a report."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str | None = None
    error_message: str = Field(min_length=1)
    component: str | None = None
    error_type: str | None = None
    error_source: str | None = None
    reported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    agent_context: dict[str, Any] = Field(default_factory=dict)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class ConversationSnapshot(BaseModel):
    """Snapshot recovered from OpenSearch."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    found_in_opensearch: bool
    conversation: Conversation | None = None
    messages: list[Message] = Field(default_factory=list)
    conversation_document: dict[str, Any] | None = None
    message_documents: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ErrorAnalytics(BaseModel):
    """Aggregates meant for later failure analytics."""

    model_config = ConfigDict(extra="forbid")

    conversation_found: bool
    conversation_reference_found: bool
    message_documents_found: bool
    message_document_count: int = Field(ge=0)
    parsed_message_count: int = Field(ge=0)
    invalid_message_count: int = Field(ge=0)
    conversation_status: str | None = None
    general_workflow: str | None = None
    workflow: str | None = None
    current_step: str | None = None
    message_count_by_role: dict[str, int] = Field(default_factory=dict)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    conversation_duration_ms: int | None = Field(default=None, ge=0)
    average_turn_duration_ms: float | None = Field(default=None, ge=0)
    max_turn_duration_ms: int | None = Field(default=None, ge=0)
    last_message_role: str | None = None
    last_message_excerpt: str | None = None
    last_user_message_excerpt: str | None = None
    last_assistant_message_excerpt: str | None = None
    last_tool_message_excerpt: str | None = None
    has_tool_messages: bool
    failure_stage: str
    normalized_error_fingerprint: str
    normalized_error_hash: str
    exact_error_hash: str
    reported_delay_ms: int | None = Field(default=None, ge=0)
    parsing_warnings: list[str] = Field(default_factory=list)
    report_generated_at: datetime


class ErrorReportMetadata(BaseModel):
    """Metadata attached to each generated report."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    schema_version: str = "1.0.0"
    service_name: str = "co_pqrs_back_error_handler"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorReportFailure(BaseModel):
    """Failure information received by the API."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    error_message: str
    component: str | None = None
    error_type: str | None = None
    error_source: str | None = None
    reported_at: datetime
    trace_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    agent_context: dict[str, Any] = Field(default_factory=dict)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class ErrorReport(BaseModel):
    """Full exported error report."""

    model_config = ConfigDict(extra="forbid")

    metadata: ErrorReportMetadata
    failure: ErrorReportFailure
    analytics: ErrorAnalytics
    conversation_snapshot: ConversationSnapshot


class StoredErrorReport(BaseModel):
    """Report plus the filesystem location where it was exported."""

    model_config = ConfigDict(extra="forbid")

    report: ErrorReport
    exported_file_path: Path
