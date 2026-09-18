import unittest
from datetime import datetime, timedelta, timezone

from infrastructure.core.config import OpenSearchSettings
from infrastructure.persistence.trx_case_store import TrxCaseStore


def _settings() -> OpenSearchSettings:
    return OpenSearchSettings(
        endpoint="https://localhost:9200",
        user="admin",
        password="admin",
        verify_ssl=False,
        control_record_ttl_days=30,
    )


class FakeOpenSearchClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    async def get_document(self, index_name: str, document_id: str):
        return self.documents.get(document_id)

    async def update_document(self, index_name, document_id, document, *, upsert=True):
        self.documents[document_id] = dict(document)


class TrxCaseStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = TrxCaseStore(settings=_settings(), index="trx-no-reconocida-cases")
        self.store.client = FakeOpenSearchClient()

    async def test_record_entered_op4_agrega_entry(self) -> None:
        now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
        await self.store.record_milestone(
            client_id="1013634958", conversation_id="c1", milestone="entered_op4", at=now
        )
        rec = await self.store.get_case("1013634958")
        self.assertIn("entered_op4", rec["milestones"])
        self.assertEqual(len(rec["entries"]), 1)
        self.assertEqual(self.store.get_bot_recurrence_count(rec, reference_at=now), 1)

    async def test_bot_recurrence_fuera_de_ventana_no_cuenta(self) -> None:
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        await self.store.record_milestone(
            client_id="1013634958", conversation_id="c1", milestone="entered_op4", at=old
        )
        rec = await self.store.get_case("1013634958")
        self.assertEqual(self.store.get_bot_recurrence_count(rec, months=6, reference_at=now), 0)

    async def test_milestones_no_se_duplican_y_guarda_snapshot(self) -> None:
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        await self.store.record_milestone(
            client_id="x", conversation_id="c", milestone="entered_op4", at=now
        )
        await self.store.record_milestone(
            client_id="x", conversation_id="c", milestone="reached_block",
            snapshot={"desenlace": "devolucion"}, outcome="devolucion", at=now,
        )
        rec = await self.store.get_case("x")
        self.assertEqual(rec["milestones"], ["entered_op4", "reached_block"])
        self.assertEqual(rec["outcome"], "devolucion")
        self.assertEqual(rec["trx_case_state_snapshot"], {"desenlace": "devolucion"})
        # entered_op4 solo una vez -> 1 entry
        self.assertEqual(len(rec["entries"]), 1)

    async def test_get_case_sin_ttl(self) -> None:
        # sin registro -> None; no hay expiración por fecha.
        self.assertIsNone(await self.store.get_case("nope"))


if __name__ == "__main__":
    unittest.main()
