"""Tests for the error report use case."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
import unittest
from unittest.mock import AsyncMock

from application.error_report.error_report_service import generate_error_report
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from domain.error_report.models import ConversationSnapshot, ErrorReportCommand
from infrastructure.core.config import ReportStorageSettings
from infrastructure.filesystem.error_report_writer import ErrorReportWriter


class GenerateErrorReportTests(unittest.IsolatedAsyncioTestCase):
    """Validate analytics and file export behavior."""

    async def test_generate_error_report_exports_report_with_analytics(self) -> None:
        received_at = datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc)
        responded_at = datetime(2026, 4, 22, 14, 0, 2, tzinfo=timezone.utc)
        user_message = Message(
            id="msg-user-1",
            role=MessageRole.USER,
            content="Necesito ayuda con mi solicitud.",
            tokens=TokenUsage(input_tokens=11, output_tokens=0, total_tokens=11),
            timing=MessageTiming(
                received_at=received_at,
                responded_at=received_at,
                total_duration_ms=0,
            ),
        )
        assistant_message = Message(
            id="msg-assistant-1",
            role=MessageRole.ASSISTANT,
            content="Claro, voy a revisar tu caso.",
            tokens=TokenUsage(input_tokens=9, output_tokens=17, total_tokens=26),
            timing=MessageTiming(
                received_at=received_at,
                responded_at=responded_at,
                total_duration_ms=2000,
            ),
        )
        conversation = Conversation(
            conversation_id="03966512_20260421",
            status=ConversationStatus.ACTIVE,
            current_step="2.1",
            general_workflow="Hazlo tu mismo",
            workflow="Solicitud",
            flow_version=1,
            user_id="03966512",
            messages=[user_message, assistant_message],
        )
        conversation.refresh_message_dates()

        snapshot = ConversationSnapshot(
            conversation_id=conversation.conversation_id,
            found_in_opensearch=True,
            conversation=conversation,
            messages=[user_message, assistant_message],
            conversation_document={"conversation_id": conversation.conversation_id},
            message_documents=[
                {"conversation_id": conversation.conversation_id, **user_message.model_dump(mode="json")},
                {
                    "conversation_id": conversation.conversation_id,
                    **assistant_message.model_dump(mode="json"),
                },
            ],
        )

        store = AsyncMock()
        store.load_conversation_snapshot.return_value = snapshot

        output_dir = Path.cwd() / "tests_output"
        rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            writer = ErrorReportWriter(
                settings=ReportStorageSettings(
                    output_dir=output_dir,
                    file_prefix="test_error_report",
                )
            )
            command = ErrorReportCommand(
                conversation_id=conversation.conversation_id,
                error_message="TimeoutError: model response exceeded 30 seconds",
                error_type="TimeoutError",
                error_source="co_pqrs_back_agent",
                reported_at=datetime(2026, 4, 22, 14, 0, 3, tzinfo=timezone.utc),
                trace_id="trace-001",
                tags=["llm", "timeout"],
            )

            stored_report = await generate_error_report(
                command,
                store=store,
                writer=writer,
            )

            self.assertTrue(stored_report.exported_file_path.exists())
            self.assertTrue(
                str(stored_report.exported_file_path).endswith(".json")
            )
            self.assertEqual(stored_report.report.analytics.parsed_message_count, 2)
            self.assertEqual(
                stored_report.report.analytics.message_count_by_role,
                {"user": 1, "assistant": 1},
            )
            self.assertEqual(stored_report.report.analytics.total_tokens, 37)
            self.assertEqual(
                stored_report.report.analytics.failure_stage,
                "assistant_response",
            )
            self.assertEqual(
                stored_report.report.analytics.reported_delay_ms,
                1000,
            )
        finally:
            rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
