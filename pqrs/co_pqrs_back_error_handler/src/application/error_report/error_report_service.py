"""Use case for exporting agent error reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import re

from domain.conversation.models import Conversation, Message, MessageRole
from domain.error_report.models import (
    ConversationSnapshot,
    ErrorAnalytics,
    ErrorReport,
    ErrorReportCommand,
    ErrorReportFailure,
    ErrorReportMetadata,
    StoredErrorReport,
)
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.filesystem.error_report_writer import ErrorReportWriter
from infrastructure.persistence.conversation_store import ConversationStore

logger = get_logger(__name__)


@log_execution
async def generate_error_report(
    command: ErrorReportCommand,
    *,
    store: ConversationStore,
    writer: ErrorReportWriter,
) -> StoredErrorReport:
    """Fetch conversation context, build analytics, and persist the JSON report."""

    snapshot = await _load_snapshot_resiliently(store, command.conversation_id)
    generated_at = datetime.now(timezone.utc)
    metadata = ErrorReportMetadata(
        report_id=_build_report_id(
            command.conversation_id or command.component,
            generated_at,
        ),
        generated_at=generated_at,
    )
    failure = ErrorReportFailure(
        conversation_id=command.conversation_id,
        error_message=command.error_message,
        component=command.component,
        error_type=command.error_type,
        error_source=command.error_source,
        reported_at=command.reported_at,
        trace_id=command.trace_id,
        tags=command.tags,
        agent_context=command.agent_context,
        extra_context=command.extra_context,
    )
    analytics = _build_analytics(
        command=command,
        snapshot=snapshot,
        generated_at=metadata.generated_at,
    )
    report = ErrorReport(
        metadata=metadata,
        failure=failure,
        analytics=analytics,
        conversation_snapshot=snapshot,
    )
    exported_file_path = await writer.write_report(report)

    logger.info(
        "Error report exported report_id=%s conversation_id=%s path=%s",
        report.metadata.report_id,
        command.conversation_id,
        exported_file_path,
    )
    return StoredErrorReport(report=report, exported_file_path=exported_file_path)


async def _load_snapshot_resiliently(
    store: ConversationStore,
    conversation_id: str | None,
) -> ConversationSnapshot:
    """Load the conversation snapshot, tolerating OpenSearch outages.

    If enrichment fails (e.g. OpenSearch is down), we still produce a report so
    the failure is never lost — just with an empty snapshot and a warning.
    """

    if not conversation_id:
        # Non-conversation services (e.g. back_data) have nothing to enrich.
        return ConversationSnapshot(
            conversation_id=conversation_id,
            found_in_opensearch=False,
        )

    try:
        return await store.load_conversation_snapshot(conversation_id)
    except Exception as exc:
        logger.warning(
            "Could not enrich error report from OpenSearch conversation_id=%s reason=%s",
            conversation_id,
            repr(exc),
        )
        return ConversationSnapshot(
            conversation_id=conversation_id,
            found_in_opensearch=False,
            warnings=[f"snapshot_load_failed: {type(exc).__name__}: {exc}"],
        )


def _build_analytics(
    *,
    command: ErrorReportCommand,
    snapshot: ConversationSnapshot,
    generated_at: datetime,
) -> ErrorAnalytics:
    """Create analytics-friendly aggregates for the exported report."""

    parsed_messages = snapshot.messages
    conversation = snapshot.conversation
    message_count_by_role = Counter(message.role.value for message in parsed_messages)
    total_input_tokens = sum(message.tokens.input_tokens for message in parsed_messages)
    total_output_tokens = sum(message.tokens.output_tokens for message in parsed_messages)
    total_tokens = sum(message.tokens.total_tokens for message in parsed_messages)
    turn_durations = [
        message.timing.total_duration_ms
        for message in parsed_messages
        if message.timing.total_duration_ms is not None
    ]

    first_message_at = _resolve_first_message_at(conversation, parsed_messages)
    last_message_at = _resolve_last_message_at(conversation, parsed_messages)
    normalized_error_fingerprint = _normalize_error_message(command.error_message)
    last_message = parsed_messages[-1] if parsed_messages else None
    last_user_message = _find_last_message(parsed_messages, MessageRole.USER)
    last_assistant_message = _find_last_message(parsed_messages, MessageRole.ASSISTANT)
    last_tool_message = _find_last_message(parsed_messages, MessageRole.TOOL)

    return ErrorAnalytics(
        conversation_found=snapshot.found_in_opensearch,
        conversation_reference_found=snapshot.conversation_document is not None,
        message_documents_found=bool(snapshot.message_documents),
        message_document_count=len(snapshot.message_documents),
        parsed_message_count=len(parsed_messages),
        invalid_message_count=max(
            len(snapshot.message_documents) - len(parsed_messages),
            0,
        ),
        conversation_status=conversation.status.value if conversation else None,
        general_workflow=conversation.general_workflow if conversation else None,
        workflow=conversation.workflow if conversation else None,
        current_step=conversation.current_step if conversation else None,
        message_count_by_role=dict(message_count_by_role),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        first_message_at=first_message_at,
        last_message_at=last_message_at,
        conversation_duration_ms=_calculate_duration_ms(first_message_at, last_message_at),
        average_turn_duration_ms=(
            round(sum(turn_durations) / len(turn_durations), 2) if turn_durations else None
        ),
        max_turn_duration_ms=max(turn_durations) if turn_durations else None,
        last_message_role=last_message.role.value if last_message else None,
        last_message_excerpt=_excerpt(last_message.content) if last_message else None,
        last_user_message_excerpt=(
            _excerpt(last_user_message.content) if last_user_message else None
        ),
        last_assistant_message_excerpt=(
            _excerpt(last_assistant_message.content) if last_assistant_message else None
        ),
        last_tool_message_excerpt=(
            _excerpt(last_tool_message.content) if last_tool_message else None
        ),
        has_tool_messages=bool(message_count_by_role.get(MessageRole.TOOL.value)),
        failure_stage=_infer_failure_stage(conversation, last_message, snapshot),
        normalized_error_fingerprint=normalized_error_fingerprint,
        normalized_error_hash=_hash_value(normalized_error_fingerprint),
        exact_error_hash=_hash_value(command.error_message),
        reported_delay_ms=_calculate_duration_ms(last_message_at, command.reported_at),
        parsing_warnings=snapshot.warnings,
        report_generated_at=generated_at,
    )


def _build_report_id(conversation_id: str | None, generated_at: datetime) -> str:
    timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    safe_conversation_id = _safe_path_fragment(conversation_id or "service")
    return f"{safe_conversation_id}_{timestamp}"


def _resolve_first_message_at(
    conversation: Conversation | None,
    messages: list[Message],
) -> datetime | None:
    if conversation and conversation.first_msg_date is not None:
        return conversation.first_msg_date
    if not messages:
        return None
    return min(message.timing.received_at for message in messages)


def _resolve_last_message_at(
    conversation: Conversation | None,
    messages: list[Message],
) -> datetime | None:
    if conversation and conversation.last_msg_date is not None:
        return conversation.last_msg_date
    if not messages:
        return None
    return max(message.timing.responded_at or message.timing.received_at for message in messages)


def _calculate_duration_ms(
    start: datetime | None,
    end: datetime | None,
) -> int | None:
    if start is None or end is None:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def _find_last_message(
    messages: list[Message],
    role: MessageRole,
) -> Message | None:
    for message in reversed(messages):
        if message.role == role:
            return message
    return None


def _infer_failure_stage(
    conversation: Conversation | None,
    last_message: Message | None,
    snapshot: ConversationSnapshot,
) -> str:
    if not snapshot.found_in_opensearch:
        return "context_not_found"
    if last_message is None:
        return "conversation_without_messages"
    if conversation and conversation.status.value.casefold() == "error":
        return "conversation_marked_error"
    if last_message.role == MessageRole.TOOL:
        return "tool_execution"
    if last_message.role == MessageRole.ASSISTANT:
        return "assistant_response"
    if last_message.role == MessageRole.USER:
        return "after_user_message"
    return "system_processing"


def _normalize_error_message(message: str) -> str:
    normalized = message.casefold()
    normalized = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", normalized)
    normalized = re.sub(r"\b\d+\b", "<num>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _hash_value(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _excerpt(value: str, limit: int = 280) -> str:
    compact_value = " ".join(value.split())
    if len(compact_value) <= limit:
        return compact_value
    return f"{compact_value[: limit - 3]}..."


def _safe_path_fragment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return sanitized or "conversation"
