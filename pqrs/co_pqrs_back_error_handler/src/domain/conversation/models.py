"""Conversation models mirrored from the agent backend."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    """Allowed roles within the conversation history."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ConversationStatus(str, Enum):
    """Lifecycle states for a conversation."""

    ACTIVE = "Active"
    INACTIVE = "Inactive"
    CLOSED = "Closed"
    ERROR = "Error"


class TokenUsage(BaseModel):
    """Token accounting per message."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class MessageTiming(BaseModel):
    """Timing information attached to a message."""

    model_config = ConfigDict(extra="forbid")

    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    responded_at: datetime | None = None
    total_duration_ms: int | None = Field(default=None, ge=0)


class Message(BaseModel):
    """Conversation message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    role: MessageRole
    content: str = Field(min_length=1)
    tokens: TokenUsage
    timing: MessageTiming


class Conversation(BaseModel):
    """Conversation aggregate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str
    first_msg_date: datetime | None = None
    last_msg_date: datetime | None = None
    status: ConversationStatus
    current_step: str = "0"
    general_workflow: str | None = None
    workflow: str | None = None
    flow_version: int | None = None
    flow_answers: dict[str, str] = Field(default_factory=dict)
    captured_data: dict[str, str] = Field(default_factory=dict)
    user_id: str
    messages: list[Message] = Field(default_factory=list)

    def refresh_message_dates(self) -> None:
        """Refresh message timestamps based on the in-memory history."""

        if not self.messages:
            self.first_msg_date = None
            self.last_msg_date = None
            return

        self.first_msg_date = min(message.timing.received_at for message in self.messages)
        self.last_msg_date = max(
            message.timing.responded_at or message.timing.received_at
            for message in self.messages
        )
