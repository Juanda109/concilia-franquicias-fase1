"""Public API schemas for chat endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageInputType = Literal["choice", "text", "date", "number", "multi_select", "terminal"]


class ChatRequest(BaseModel):
    """Request payload for posting a user conversation message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(
        pattern=r"^\d+_\d{8}$",
        description="Conversation identifier formatted as customer_id_yyyymmdd.",
        examples=["03966512_20260421"],
    )
    content: str = Field(
        min_length=1,
        max_length=1000,
        description="User message content to be processed by the API.",
        examples=["Hola, necesito ayuda con mi solicitud."],
    )

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: str) -> str:
        """Validate the partition suffix as a real YYYYMMDD date."""

        _, partition_date = value.rsplit("_", maxsplit=1)
        datetime.strptime(partition_date, "%Y%m%d")
        return value


class ChatMessageOption(BaseModel):
    """Selectable option rendered by the frontend."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(
        description="Stable option key sent back by the frontend when the user selects it.",
        examples=["centrales_de_riesgo"],
    )
    label: str = Field(
        description="User-facing option label rendered by the frontend.",
        examples=["Centrales de riesgo"],
    )


class StartMessageContent(BaseModel):
    """Structured assistant content rendered by the frontend for `POST /start`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(
        description="General question or message shown above the options.",
        examples=["Hola, en que te puedo ayudar?"],
    )
    options: list[ChatMessageOption] = Field(
        default_factory=list,
        description=(
            "Selectable options associated with the message. Empty for the "
            "initial greeting; populated when POST /start RESUMES a session "
            "parked on a choice step, so the frontend can render its buttons."
        ),
    )


class ChatMessageContent(StartMessageContent):
    """Structured assistant content rendered by the frontend for `POST /chat`."""

    options: list[ChatMessageOption] = Field(
        default_factory=list,
        description="Selectable options associated with the message, when applicable.",
    )


class StartMessageEnvelope(BaseModel):
    """Assistant message metadata plus structured start content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sender: Literal["bot"] = Field(
        description="Sender identifier expected by the frontend.",
        examples=["bot"],
    )
    timestamp: datetime = Field(
        description="UTC timestamp associated with the assistant response.",
    )
    input_type: MessageInputType = Field(
        description="Type of input the frontend should expect after rendering the message.",
        examples=["text"],
    )
    content: StartMessageContent = Field(
        description="Structured start content rendered by the chat frontend.",
    )


class ChatMessageEnvelope(BaseModel):
    """Assistant message metadata plus structured chat content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message_id: str = Field(
        description=(
            "Identifier of the assistant message. A step that repaints itself "
            "in place (a multi_select selector toggling a box or changing "
            "page) answers with the SAME id it already sent, so the frontend "
            "replaces that message instead of appending another copy."
        ),
        examples=["0a5f2c1e-2b7d-4a1e-9c33-0d1b5f7a9e21"],
    )
    sender: Literal["bot"] = Field(
        description="Sender identifier expected by the frontend.",
        examples=["bot"],
    )
    timestamp: datetime = Field(
        description="UTC timestamp associated with the assistant response.",
    )
    input_type: MessageInputType = Field(
        description="Type of input the frontend should expect after rendering the message.",
        examples=["choice"],
    )
    content: ChatMessageContent = Field(
        description="Structured chat content rendered by the chat frontend.",
    )


class BaseConversationResponse(BaseModel):
    """Shared response payload fields for conversation endpoints."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str = Field(
        description="Current lifecycle status of the conversation after processing the request.",
        examples=["Active"],
    )
    conversation_id: str = Field(
        pattern=r"^\d+_\d{8}$",
        description="Conversation identifier associated with the processed request.",
        examples=["03966512_20260421"],
    )


class ChatResponse(BaseConversationResponse):
    """Response payload for conversation message endpoints."""

    message: ChatMessageEnvelope = Field(
        description="Structured assistant response returned by the API.",
    )


class StartRequest(BaseModel):
    """Request payload for starting a new conversation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(
        pattern=r"^\d+$",
        min_length=1,
        description=(
            "Unique user identifier used to generate the conversation_id as "
            "`user_id_yyyymmdd`."
        ),
        examples=["03966512"],
    )
    content: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Optional initial text. `POST /start` ignores this field and returns "
            "the configured greeting; send the first real request to `POST /chat`."
        ),
        examples=["Hola, necesito ayuda con mi solicitud."],
    )


class StartResponse(BaseConversationResponse):
    """Response payload for the start endpoint."""

    message: StartMessageEnvelope = Field(
        description="Structured assistant greeting returned by the API.",
    )


class EndRequest(BaseModel):
    """Request payload for ending an existing conversation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(
        pattern=r"^\d+_\d{8}$",
        description="Conversation identifier formatted as customer_id_yyyymmdd.",
        examples=["03966512_20260421"],
    )

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: str) -> str:
        """Validate the partition suffix as a real YYYYMMDD date."""

        _, partition_date = value.rsplit("_", maxsplit=1)
        datetime.strptime(partition_date, "%Y%m%d")
        return value


class EndResponse(ChatResponse):
    """Response payload for ending an existing conversation."""


class PollingData(BaseModel):
    """Payload nested inside a polling status response."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str = Field(
        description="Current processing status of the conversation.",
        examples=["running"],
    )


class PollingResponse(BaseModel):
    """Response payload for `POST /polling` when the conversation is still processing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    data: PollingData = Field(
        description="Polling status data.",
    )


class PollingRequest(BaseModel):
    """Request payload for checking whether an async chat turn has finished."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(
        pattern=r"^\d+_\d{8}$",
        description="Conversation identifier formatted as customer_id_yyyymmdd.",
        examples=["03966512_20260421"],
    )

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: str) -> str:
        """Validate the partition suffix as a real YYYYMMDD date."""

        _, partition_date = value.rsplit("_", maxsplit=1)
        datetime.strptime(partition_date, "%Y%m%d")
        return value
