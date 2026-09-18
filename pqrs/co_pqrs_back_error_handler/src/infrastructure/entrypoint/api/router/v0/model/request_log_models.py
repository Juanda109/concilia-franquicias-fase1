"""API models for the request-logs endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RequestLogRequest(BaseModel):
    """Request body for storing a per-request full log capture."""

    model_config = ConfigDict(extra="forbid")

    component: str | None = Field(default=None, examples=["co_pqrs_back_agent"])
    conversation_id: str | None = None
    customer_id: str | None = None
    request_id: str | None = None
    segment: str = Field(default="main", examples=["main", "background"])
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    elapsed_ms: float | None = Field(default=None, ge=0)
    line_count: int = Field(default=0, ge=0)
    truncated: bool = False
    log_text: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class RequestLogResponse(BaseModel):
    """API response after storing a request log."""

    model_config = ConfigDict(extra="forbid")

    request_log_id: str
    stored_path: str
    recorded_at: datetime
