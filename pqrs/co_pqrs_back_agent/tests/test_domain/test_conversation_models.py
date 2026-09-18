"""Tests for Conversation tolerance of maintenance-written fields."""

import unittest

from pydantic import ValidationError

from domain.conversation.models import Conversation, ConversationStatus


def _stored_doc_with_maintenance_fields() -> dict:
    """A conversation document as maintenance leaves it in OpenSearch."""

    return {
        "conversation_id": "01576905_20260701",
        "status": "Closed",
        "user_id": "01576905",
        "current_step": "start",
        "messages": [],
        "closed_at": "2026-07-02T01:54:58.525700+00:00",
        "maintenance_locked_by": "cron:co-pqrs-back-maintenance-1f240298699e39665fa7cb0",
        "maintenance_locked_at": "2026-07-02T01:55:06.964738+00:00",
        "maintenance_export_path": "conversations/01576905_20260701_20260702T015458Z.json",
    }


class ConversationMaintenanceFieldsTests(unittest.TestCase):
    def test_deserializes_document_touched_by_maintenance(self) -> None:
        # This used to raise "4 validation errors ... extra_forbidden".
        conversation = Conversation.model_validate(
            _stored_doc_with_maintenance_fields()
        )

        self.assertEqual(conversation.status, ConversationStatus.CLOSED)
        self.assertIsNotNone(conversation.closed_at)
        self.assertEqual(
            conversation.maintenance_export_path,
            "conversations/01576905_20260701_20260702T015458Z.json",
        )
        self.assertTrue(conversation.maintenance_locked_by)
        self.assertIsNotNone(conversation.maintenance_locked_at)

    def test_round_trips_maintenance_fields_on_dump(self) -> None:
        conversation = Conversation.model_validate(
            _stored_doc_with_maintenance_fields()
        )
        dumped = conversation.model_dump()

        for field in (
            "closed_at",
            "maintenance_locked_by",
            "maintenance_locked_at",
            "maintenance_export_path",
        ):
            self.assertIn(field, dumped)

    def test_document_without_maintenance_fields_still_valid(self) -> None:
        conversation = Conversation.model_validate(
            {
                "conversation_id": "111_20260701",
                "status": "Active",
                "user_id": "111",
            }
        )
        self.assertIsNone(conversation.closed_at)
        self.assertIsNone(conversation.maintenance_locked_by)

    def test_truly_unknown_field_is_still_rejected(self) -> None:
        # extra="forbid" must remain: only the known maintenance fields are allowed.
        with self.assertRaises(ValidationError):
            Conversation.model_validate(
                {
                    "conversation_id": "111_20260701",
                    "status": "Active",
                    "user_id": "111",
                    "campo_desconocido": "x",
                }
            )


if __name__ == "__main__":
    unittest.main()
