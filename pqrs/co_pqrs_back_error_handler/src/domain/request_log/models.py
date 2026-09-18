"""Domain models for per-request full log captures.

A request log is the COMPLETE log stream emitted while handling a single
chatbot request (one turn), captured by the upstream service and shipped here
so it can be stored in MinIO under a SEPARATE ``request-logs/`` prefix,
partitioned per customer / conversation. This is intentionally kept apart from
the structured trace events (``clients/`` prefix) so neither breaks the other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RequestLogCommand(BaseModel):
    """Input payload accepted by the request-logs endpoint."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    component: str | None = Field(
        default=None,
        description="Emitting service, e.g. co_pqrs_back_agent | co_pqrs_back_data.",
    )
    conversation_id: str | None = None
    customer_id: str | None = None
    request_id: str | None = Field(
        default=None,
        description="Correlation/request id of the captured request.",
    )
    segment: str = Field(
        default="main",
        description="main = request/response cycle; background = post-response async task.",
    )
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    elapsed_ms: float | None = Field(default=None, ge=0)
    line_count: int = Field(default=0, ge=0)
    truncated: bool = False
    log_text: str = Field(default="", description="The full captured log text.")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class RequestLogMetadata(BaseModel):
    """Metadata attached to each stored request log."""

    model_config = ConfigDict(extra="forbid")

    request_log_id: str
    schema_version: str = "1.0.0"
    service_name: str = "co_pqrs_back_error_handler"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RequestLogRecord(BaseModel):
    """Full persisted request log (metadata + the received command)."""

    model_config = ConfigDict(extra="forbid")

    metadata: RequestLogMetadata
    log: RequestLogCommand
