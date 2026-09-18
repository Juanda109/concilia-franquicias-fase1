"""Recover conversations and messages from OpenSearch."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from domain.conversation.models import Conversation, Message
from domain.error_report.models import ConversationSnapshot
from infrastructure.core.config import OpenSearchSettings, load_opensearch_settings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.opensearch_client import OpenSearchClient

logger = get_logger(__name__)

_OPENSEARCH_DOT_ESCAPE = "\uFF0E"


class ConversationStore:
    """Read conversation context using the same index layout as the agent backend."""

    def __init__(
        self,
        settings: OpenSearchSettings | None = None,
        *,
        env_path: str = ".env",
    ) -> None:
        self.settings = settings or load_opensearch_settings(env_path)
        self.client = OpenSearchClient(self.settings)
        self._lock = asyncio.Lock()

    @log_execution
    async def load_conversation_snapshot(
        self,
        conversation_id: str,
    ) -> ConversationSnapshot:
        """Load the conversation reference document and message history."""

        async with self._lock:
            conversation_document = await asyncio.to_thread(
                self.client.get_document,
                self.settings.conversations_index,
                conversation_id,
            )
            message_documents = await asyncio.to_thread(
                self.client.search_by_term,
                self.settings.messages_index,
                "conversation_id",
                conversation_id,
                sort=[
                    {"timing.received_at": {"order": "asc"}},
                    {"id": {"order": "asc"}},
                ],
            )

        parsed_messages, warnings = self._deserialize_messages(message_documents)
        conversation, conversation_warning = self._deserialize_conversation(
            conversation_document,
            parsed_messages,
        )
        if conversation_warning is not None:
            warnings.append(conversation_warning)

        if conversation is not None and parsed_messages:
            conversation.refresh_message_dates()

        found_in_opensearch = conversation_document is not None or bool(message_documents)

        return ConversationSnapshot(
            conversation_id=conversation_id,
            found_in_opensearch=found_in_opensearch,
            conversation=conversation,
            messages=parsed_messages,
            conversation_document=conversation_document,
            message_documents=message_documents,
            warnings=warnings,
        )

    def _deserialize_messages(
        self,
        message_documents: list[dict[str, Any]],
    ) -> tuple[list[Message], list[str]]:
        parsed_messages: list[Message] = []
        warnings: list[str] = []

        for message_document in message_documents:
            try:
                parsed_messages.append(self._deserialize_message(message_document))
            except ValidationError as exc:
                message_id = message_document.get("id", "unknown")
                warning = (
                    f"Message {message_id} could not be parsed: "
                    f"{exc.errors()[0]['msg']}"
                )
                logger.warning(warning)
                warnings.append(warning)

        return parsed_messages, warnings

    def _deserialize_conversation(
        self,
        conversation_document: dict[str, Any] | None,
        messages: list[Message],
    ) -> tuple[Conversation | None, str | None]:
        if conversation_document is None:
            return None, None

        decoded_document = dict(conversation_document)
        decoded_document["flow_answers"] = self._decode_storage_dict(
            decoded_document.get("flow_answers", {})
        )
        decoded_document["captured_data"] = self._decode_storage_dict(
            decoded_document.get("captured_data", {})
        )

        try:
            conversation = Conversation.model_validate(
                {
                    **decoded_document,
                    "messages": messages,
                }
            )
        except ValidationError as exc:
            warning = f"Conversation could not be parsed: {exc.errors()[0]['msg']}"
            logger.warning(warning)
            return None, warning

        return conversation, None

    def _deserialize_message(self, message_document: dict[str, Any]) -> Message:
        return Message.model_validate(
            {
                key: value
                for key, value in message_document.items()
                if key != "conversation_id"
            }
        )

    def _decode_storage_dict(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        flattened_payload = self._flatten_storage_dict(payload)
        return {
            self._decode_storage_key(key): str(value)
            for key, value in flattened_payload.items()
        }

    def _flatten_storage_dict(
        self,
        payload: Any,
        prefix: str | None = None,
    ) -> dict[str, Any]:
        flattened_payload: dict[str, Any] = {}

        if not isinstance(payload, dict):
            return flattened_payload

        for key, value in payload.items():
            compound_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flattened_payload.update(
                    self._flatten_storage_dict(value, prefix=compound_key)
                )
                continue
            flattened_payload[compound_key] = value

        return flattened_payload

    def _decode_storage_key(self, key: str) -> str:
        return key.replace(_OPENSEARCH_DOT_ESCAPE, ".")
