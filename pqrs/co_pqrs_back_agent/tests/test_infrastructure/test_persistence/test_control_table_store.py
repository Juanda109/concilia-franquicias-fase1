"""Unit tests for the daily session counter in ControlTableStore."""

import unittest
from datetime import datetime, timedelta, timezone

from infrastructure.core.config import OpenSearchSettings
from infrastructure.persistence.control_table_store import ControlTableStore


def _build_settings() -> OpenSearchSettings:
    return OpenSearchSettings(
        endpoint="https://localhost:9200",
        user="admin",
        password="admin",
        verify_ssl=False,
        control_record_ttl_days=30,
    )


class FakeOpenSearchClient:
    """In-memory stand-in for the OpenSearch client used by the control store."""

    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    async def get_document(self, index_name: str, document_id: str):
        return self.documents.get(document_id)

    async def update_document(self, index_name, document_id, document, *, upsert=True):
        self.documents[document_id] = dict(document)

    async def delete_by_term(self, index_name, field_name, value):
        self.documents.pop(value, None)


class DailySessionCounterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = ControlTableStore(settings=_build_settings())
        self.fake_client = FakeOpenSearchClient()
        self.store.client = self.fake_client

    async def test_first_session_start_sets_count_to_one(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_session_start("111", interaction_at=now)

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_daily_session_count(record, reference_at=now),
            1,
        )

    async def test_successive_starts_increment_same_day(self) -> None:
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)

        await self.store.record_session_start("111", interaction_at=now)
        await self.store.record_session_start("111", interaction_at=now)
        await self.store.record_session_start("111", interaction_at=now)

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_daily_session_count(record, reference_at=now),
            3,
        )

    async def test_counter_resets_on_a_new_day(self) -> None:
        day_one = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        day_two = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)

        await self.store.record_session_start("111", interaction_at=day_one)
        await self.store.record_session_start("111", interaction_at=day_one)

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_daily_session_count(record, reference_at=day_one),
            2,
        )
        self.assertEqual(
            self.store.get_daily_session_count(record, reference_at=day_two),
            0,
        )

    async def test_missing_record_returns_zero(self) -> None:
        self.assertEqual(self.store.get_daily_session_count(None), 0)
        self.assertEqual(self.store.get_daily_session_count({}), 0)

    async def test_expired_record_is_not_counted(self) -> None:
        expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.fake_client.documents["111"] = {
            "client_id": "111",
            "daily_sessions": {"20260618": {"count": 2}},
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            "expires_at": expired_at,
        }

        # get_record drops expired records, so the next read starts fresh.
        record = await self.store.get_record("111")
        self.assertIsNone(record)
        self.assertEqual(self.store.get_daily_session_count(record), 0)


if __name__ == "__main__":
    unittest.main()
