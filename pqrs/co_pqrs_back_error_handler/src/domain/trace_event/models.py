"""Domain models for E2E trace events (ASO / Postgres / external calls).

A trace event is a lightweight, per-interaction record (success OR failure)
emitted by upstream services (co_pqrs_back_data, co_pqrs_back_agent) so the full
end-to-end path of a request can be reconstructed in MinIO. Unlike error
reports, trace events are NOT enriched from OpenSearch: they are written as-is,
near real-time, one object per event.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceEventCommand(BaseModel):
    """Input payload accepted by the trace-events endpoint."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # What happened
    event_type: str = Field(
        min_length=1,
        description="High-level category: aso | postgres | opensearch | http | ...",
    )
    operation: str = Field(
        min_length=1,
        description="Concrete operation, e.g. tsec | commercial_info_overview | read_customer_identity.",
    )
    outcome: str = Field(
        default="ok",
        description="ok | error.",
    )

    # Where / who
    component: str | None = Field(
        default=None,
        description="Emitting service, e.g. co_pqrs_back_data.",
    )
    conversation_id: str | None = None
    customer_id: str | None = None
    trace_id: str | None = None

    # Result detail
    target: str | None = Field(
        default=None,
        description="URL or table/index the operation hit (secrets already stripped).",
    )
    status_code: int | None = Field(
        default=None,
        description="HTTP status code when applicable.",
    )
    elapsed_ms: float | None = Field(default=None, ge=0)
    request_summary: dict[str, Any] = Field(default_factory=dict)
    response_summary: dict[str, Any] = Field(default_factory=dict)

    # Error detail (only when outcome == error)
    error_type: str | None = None
    error_message: str | None = None

    tags: list[str] = Field(default_factory=list)
    extra_context: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraceEventMetadata(BaseModel):
    """Metadata attached to each stored trace event."""

    model_config = ConfigDict(extra="forbid")

    trace_event_id: str
    schema_version: str = "1.0.0"
    service_name: str = "co_pqrs_back_error_handler"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraceEventRecord(BaseModel):
    """Full persisted trace event (metadata + the received command)."""

    model_config = ConfigDict(extra="forbid")

    metadata: TraceEventMetadata
    event: TraceEventCommand
