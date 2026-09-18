"""Unit tests for per-category daily counters and recheck counters."""

import unittest
from datetime import datetime, timezone

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


class CategoryCounterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = ControlTableStore(settings=_build_settings())
        self.store.client = FakeOpenSearchClient()

    async def test_category_count_increments(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_category_interaction(
            client_id="111", category="centrales", workflow_label="Centrales de Riesgo",
            interaction_at=now,
        )
        await self.store.record_category_interaction(
            client_id="111", category="centrales", workflow_label="Centrales de Riesgo",
            interaction_at=now,
        )

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_category_day_count(record, "centrales", reference_at=now), 2
        )

    async def test_categories_are_isolated(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_category_interaction(
            client_id="111", category="centrales", workflow_label="Centrales de Riesgo",
            interaction_at=now,
        )

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_category_day_count(record, "centrales", reference_at=now), 1
        )
        self.assertEqual(
            self.store.get_category_day_count(record, "general", reference_at=now), 0
        )

    async def test_category_count_isolated_per_day(self) -> None:
        day_one = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
        day_two = datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)

        await self.store.record_category_interaction(
            client_id="111", category="general", workflow_label="Impuesto 4x1000",
            interaction_at=day_one,
        )

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_category_day_count(record, "general", reference_at=day_one), 1
        )
        self.assertEqual(
            self.store.get_category_day_count(record, "general", reference_at=day_two), 0
        )

    async def test_last_flow_label_stored_per_category(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_category_interaction(
            client_id="111", category="general", workflow_label="Impuesto 4x1000",
            interaction_at=now,
        )

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_category_last_flow_label(record, "general", reference_at=now),
            "Impuesto 4x1000",
        )
        self.assertIsNone(
            self.store.get_category_last_flow_label(record, "centrales", reference_at=now)
        )

    async def test_missing_record_returns_zero_and_none(self) -> None:
        self.assertEqual(self.store.get_category_day_count(None, "centrales"), 0)
        self.assertEqual(self.store.get_category_day_count({}, "centrales"), 0)
        self.assertIsNone(self.store.get_category_last_flow_label(None, "centrales"))

    async def test_category_recording_does_not_touch_daily_sessions(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_session_start("111", interaction_at=now)
        await self.store.record_category_interaction(
            client_id="111", category="centrales", workflow_label="Centrales de Riesgo",
            interaction_at=now,
        )

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_daily_session_count(record, reference_at=now), 1
        )


class RecheckCounterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = ControlTableStore(settings=_build_settings())
        self.store.client = FakeOpenSearchClient()

    async def test_recheck_increments(self) -> None:
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)

        await self.store.record_recheck("111", "general", interaction_at=now)
        await self.store.record_recheck("111", "general", interaction_at=now)
        await self.store.record_recheck("111", "general", interaction_at=now)

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_recheck_count(record, "general", reference_at=now), 3
        )
        # Insistence is per-category: a different category stays at zero.
        self.assertEqual(
            self.store.get_recheck_count(record, "centrales", reference_at=now), 0
        )

    async def test_recheck_isolated_per_day(self) -> None:
        day_one = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
        day_two = datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)

        await self.store.record_recheck("111", "general", interaction_at=day_one)

        record = await self.store.get_record("111")
        self.assertEqual(
            self.store.get_recheck_count(record, "general", reference_at=day_one), 1
        )
        self.assertEqual(
            self.store.get_recheck_count(record, "general", reference_at=day_two), 0
        )

    async def test_missing_record_returns_zero(self) -> None:
        self.assertEqual(self.store.get_recheck_count(None, "general"), 0)
        self.assertEqual(self.store.get_recheck_count({}, "general"), 0)


if __name__ == "__main__":
    unittest.main()
