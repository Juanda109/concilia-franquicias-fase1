"""OpenSearch-backed conversation persistence with a storage-agnostic public interface."""

from __future__ import annotations

import asyncio
from typing import Any

from domain.conversation.models import Conversation, Message
from infrastructure.core.config import OpenSearchSettings, load_opensearch_settings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.opensearch_client import OpenSearchClient

logger = get_logger(__name__)

_OPENSEARCH_DOT_ESCAPE = "\uff0e"


class ConversationStore:
    """
    Persist and restore conversations and messages using OpenSearch.

    The public API stays intentionally small so the persistence backend can be
    replaced later without changing the calling code.
    """

    def __init__(
        self,
        settings: OpenSearchSettings | None = None,
        *,
        env_path: str = ".env",
    ) -> None:
        self.settings = settings or load_opensearch_settings(env_path)
        self.client = OpenSearchClient(self.settings)
        logger.info(
            "ConversationStore initialized endpoint=%s conversations_index=%s messages_index=%s",
            self.settings.endpoint,
            self.settings.conversations_index,
            self.settings.messages_index,
        )

    @log_execution
    async def save_conversation(self, conversation: Conversation) -> None:
        """
        Save a conversation reference and upsert all of its messages.

        This compatibility helper avoids deleting existing history and simply
        updates the reference document plus each message document by id.
        """

        logger.info(
            "Saving conversation conversation_id=%s message_count=%s status=%s current_step=%s",
            conversation.conversation_id,
            len(conversation.messages),
            conversation.status.value,
            conversation.current_step,
        )
        await asyncio.gather(
            self.save_conversation_reference(conversation),
            *[
                self.save_message(conversation.conversation_id, msg)
                for msg in conversation.messages
            ],
        )
        await self.refresh()

    @log_execution
    async def save_conversation_reference(self, conversation: Conversation) -> None:
        """Persist only the conversation reference document."""

        logger.info(
            "Saving conversation reference conversation_id=%s status=%s current_step=%s general_workflow=%s workflow=%s",
            conversation.conversation_id,
            conversation.status.value,
            conversation.current_step,
            conversation.general_workflow,
            conversation.workflow,
        )
        stored_conversation = self._serialize_conversation(conversation)
        await self.client.index_document(
            self.settings.conversations_index,
            conversation.conversation_id,
            stored_conversation,
        )

    @log_execution
    async def save_message(self, conversation_id: str, message: Message) -> None:
        """Persist or update a single message document."""

        logger.info(
            "Saving message conversation_id=%s message_id=%s role=%s",
            conversation_id,
            message.id,
            message.role.value,
        )
        stored_message = self._serialize_message(conversation_id, message)
        await self.client.index_document(
            self.settings.messages_index,
            stored_message["id"],
            stored_message,
        )

    @log_execution
    async def refresh(self) -> None:
        """Refresh both conversation indices after a completed turn."""

        logger.info(
            "Refreshing OpenSearch indices conversations_index=%s messages_index=%s",
            self.settings.conversations_index,
            self.settings.messages_index,
        )
        await asyncio.gather(
            self.client.refresh_index(self.settings.conversations_index),
            self.client.refresh_index(self.settings.messages_index),
        )

    @log_execution
    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        """Load a conversation and hydrate its message history."""

        logger.info("Loading conversation conversation_id=%s", conversation_id)
        stored_conversation = await self.client.get_document(
            self.settings.conversations_index,
            conversation_id,
        )

        if stored_conversation is None:
            logger.warning(
                "Conversation not found on first attempt, retrying after 300ms conversation_id=%s",
                conversation_id,
            )
            await asyncio.sleep(0.3)
            stored_conversation = await self.client.get_document(
                self.settings.conversations_index,
                conversation_id,
            )

        if stored_conversation is None:
            logger.info("Conversation not found conversation_id=%s", conversation_id)
            return None

        message_records = await self.client.search_by_term(
            self.settings.messages_index,
            "conversation_id",
            conversation_id,
            sort=[
                {"timing.received_at": {"order": "asc"}},
            ],
        )
        messages = self._filter_messages(message_records, conversation_id)
        conversation = self._deserialize_conversation(stored_conversation, messages)

        if messages:
            conversation.refresh_message_dates()

        logger.info(
            "Conversation loaded conversation_id=%s message_count=%s",
            conversation_id,
            len(messages),
        )
        return conversation

    @log_execution
    async def delete_conversation_messages(self, conversation_id: str) -> None:
        """Delete every message document belonging to a conversation.

        Used when a closed conversation is reopened on the same deterministic
        id so the new session does not inherit the previous session's history.
        """

        logger.info(
            "Deleting messages for conversation conversation_id=%s",
            conversation_id,
        )
        await self.client.delete_by_term(
            self.settings.messages_index,
            "conversation_id",
            conversation_id,
        )
        await self.client.refresh_index(self.settings.messages_index)

    @log_execution
    async def delete_message(self, conversation_id: str, message_id: str) -> None:
        """Delete a single message document by its identifier.

        Used when a turn turns out NOT to be a turn: a click that only repaints
        a multi_select selector in place is saved before the engine has decided
        what it was, and must not stay in the history afterwards.
        """

        logger.info(
            "Deleting message conversation_id=%s message_id=%s",
            conversation_id,
            message_id,
        )
        await self.client.delete_by_term(
            self.settings.messages_index,
            "id",
            message_id,
        )

    @log_execution
    async def load_messages(self, conversation_id: str) -> list[Message]:
        """Load all messages associated with a conversation identifier."""

        logger.info("Loading messages conversation_id=%s", conversation_id)
        message_records = await self.client.search_by_term(
            self.settings.messages_index,
            "conversation_id",
            conversation_id,
            sort=[
                {"timing.received_at": {"order": "asc"}},
            ],
        )
        return self._filter_messages(message_records, conversation_id)

    @log_execution
    def _filter_messages(
        self,
        message_records: list[dict[str, Any]],
        conversation_id: str,
    ) -> list[Message]:
        """Filter message records by conversation identifier."""

        logger.debug(
            "Filtering message records conversation_id=%s available_records=%s",
            conversation_id,
            len(message_records),
        )
        messages = [self._deserialize_message(record) for record in message_records]
        messages.sort(key=lambda message: (message.timing.received_at, message.id))
        return messages

    @log_execution
    def _serialize_conversation(self, conversation: Conversation) -> dict[str, Any]:
        """Serialize a conversation without its in-memory message list."""

        serialized_conversation = conversation.model_dump(
            mode="json",
            exclude={"messages"},
        )
        serialized_conversation["flow_answers"] = self._encode_storage_dict(
            serialized_conversation.get("flow_answers", {})
        )
        serialized_conversation["captured_data"] = self._encode_storage_dict(
            serialized_conversation.get("captured_data", {})
        )
        return serialized_conversation

    @log_execution
    def _deserialize_conversation(
        self,
        conversation_data: dict[str, Any],
        messages: list[Message],
    ) -> Conversation:
        """Deserialize a persisted conversation and attach its messages."""

        decoded_conversation = dict(conversation_data)
        decoded_conversation["flow_answers"] = self._decode_storage_dict(
            decoded_conversation.get("flow_answers", {})
        )
        decoded_conversation["captured_data"] = self._decode_storage_dict(
            decoded_conversation.get("captured_data", {})
        )

        return Conversation.model_validate(
            {
                **decoded_conversation,
                "messages": messages,
            }
        )

    @log_execution
    def _serialize_message(
        self,
        conversation_id: str,
        message: Message,
    ) -> dict[str, Any]:
        """Serialize a message with the conversation identifier used for storage."""

        logger.debug(
            "Serializing message conversation_id=%s message_id=%s role=%s",
            conversation_id,
            message.id,
            message.role.value,
        )
        return {
            "conversation_id": conversation_id,
            **message.model_dump(mode="json"),
        }

    @log_execution
    def _deserialize_message(self, message_data: dict[str, Any]) -> Message:
        """Deserialize a persisted message record into a runtime Message object."""

        return Message.model_validate(
            {
                key: value
                for key, value in message_data.items()
                if key != "conversation_id"
            }
        )

    @log_execution
    def _encode_storage_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Encode dictionary keys recursively before persisting them to OpenSearch.
        """

        encoded: dict[str, Any] = {}

        for key, value in payload.items():
            encoded_key = self._encode_storage_key(key)

            if isinstance(value, dict):
                encoded[encoded_key] = self._encode_storage_dict(value)
            elif isinstance(value, list):
                encoded[encoded_key] = [
                    self._encode_storage_dict(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                encoded[encoded_key] = value

        return encoded

    @log_execution
    def _decode_storage_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Decode dictionary keys recursively after reading from OpenSearch.
        """

        decoded: dict[str, Any] = {}

        for key, value in payload.items():
            decoded_key = self._decode_storage_key(key)

            if isinstance(value, dict):
                decoded[decoded_key] = self._decode_storage_dict(value)

            elif isinstance(value, list):
                decoded[decoded_key] = [
                    self._decode_storage_dict(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]

            else:
                decoded[decoded_key] = value

        return decoded

    @log_execution
    def _flatten_storage_dict(
        self,
        payload: dict[str, Any],
        prefix: str | None = None,
    ) -> dict[str, Any]:
        """Flatten nested storage dictionaries into a single dotted-key mapping."""

        flattened_payload: dict[str, Any] = {}

        for key, value in payload.items():
            compound_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                flattened_payload.update(
                    self._flatten_storage_dict(value, prefix=compound_key)
                )
                continue

            flattened_payload[compound_key] = value

        return flattened_payload

    @log_execution
    def _encode_storage_key(self, key: str) -> str:
        """Escape dots in a dictionary key before sending it to OpenSearch."""

        return key.replace(".", _OPENSEARCH_DOT_ESCAPE)

    @log_execution
    def _decode_storage_key(self, key: str) -> str:
        """Restore escaped dots in a dictionary key read from OpenSearch."""

        return key.replace(_OPENSEARCH_DOT_ESCAPE, ".")
