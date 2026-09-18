"""API models for the error report endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.error_report.models import ErrorAnalytics


class ErrorReportRequest(BaseModel):
    """Request body for exporting an error report."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str | None = Field(
        default=None,
        description="Identifier used to query the conversation in OpenSearch. Optional for non-conversation services.",
        examples=["03966512_20260421"],
    )
    error_message: str = Field(
        min_length=1,
        description="Exact error message received from the failing agent flow.",
        examples=["TimeoutError: model response exceeded 30 seconds"],
    )
    component: str | None = Field(
        default=None,
        description="Logical component/service that failed (e.g. co_pqrs_back_data).",
        examples=["co_pqrs_back_data"],
    )
    error_type: str | None = Field(
        default=None,
        description="Optional technical classification of the failure.",
        examples=["TimeoutError"],
    )
    error_source: str | None = Field(
        default="co_pqrs_back_agent",
        description="Service or module that emitted the failure.",
    )
    reported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the failure was reported to this API.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Correlation id for logs and distributed tracing.",
        examples=["pqr-err-20260422-0001"],
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional labels for later analytics grouping.",
        examples=[["llm", "timeout", "production"]],
    )
    agent_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw context received from the agent at failure time.",
    )
    extra_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional arbitrary metadata relevant for diagnostics.",
    )


class ErrorReportResponse(BaseModel):
    """API response after exporting the report."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    conversation_id: str | None
    conversation_found: bool
    exported_file_path: str
    generated_at: datetime
    analytics: ErrorAnalytics
