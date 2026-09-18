"""API models for the trace-events endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceEventRequest(BaseModel):
    """Request body for recording an E2E trace event."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_type: str = Field(min_length=1, examples=["aso", "postgres"])
    operation: str = Field(min_length=1, examples=["commercial_info_overview", "read_customer_identity"])
    outcome: str = Field(default="ok", examples=["ok", "error"])
    component: str | None = Field(default=None, examples=["co_pqrs_back_data"])
    conversation_id: str | None = None
    customer_id: str | None = None
    trace_id: str | None = None
    target: str | None = Field(default=None, examples=["https://aso/overview"])
    status_code: int | None = None
    elapsed_ms: float | None = Field(default=None, ge=0)
    request_summary: dict[str, Any] = Field(default_factory=dict)
    response_summary: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    tags: list[str] = Field(default_factory=list)
    extra_context: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraceEventResponse(BaseModel):
    """API response after recording a trace event."""

    model_config = ConfigDict(extra="forbid")

    trace_event_id: str
    stored_path: str
    recorded_at: datetime
