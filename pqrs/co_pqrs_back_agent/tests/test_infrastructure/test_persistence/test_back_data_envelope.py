"""Tests for the back-data freshness envelope (status + run_id) on the agent side.

Guards the fix for the false "no tienes reportes negativos": the poll must only
accept a FRESH successful result (status=ok AND matching run_id); an error
envelope or a stale run_id must NOT be served as data.
"""

from __future__ import annotations

import types
import unittest
from datetime import datetime, timezone

from application.chat import chat_service
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
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    async def get_document(self, index_name: str, document_id: str):
        return self.documents.get(document_id)

    async def update_document(self, index_name, document_id, document, *, upsert=True):
        self.documents[document_id] = dict(document)

    async def delete_by_term(self, index_name, field_name, value):
        self.documents.pop(value, None)


class WorkflowEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = ControlTableStore(settings=_build_settings())
        self.store.client = FakeOpenSearchClient()
        self.now = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
        self.month = self.store._month_key(self.now)

    def _record(self, wf_bucket: dict) -> dict:
        return {
            "client_id": "123",
            "monthly": {self.month: {"workflows": {"centrales_de_riesgo": wf_bucket}}},
        }

    def test_envelope_ok_returns_data(self) -> None:
        rec = self._record(
            {
                "back_data_status": "ok",
                "back_data_run_id": "r1",
                "back_data_updated_at": "t",
                "data": {"hallazgos": {"validaciones": []}},
            }
        )
        env = self.store.get_workflow_back_data_envelope(
            rec, "centrales_de_riesgo", reference_at=self.now
        )
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["run_id"], "r1")
        self.assertEqual(env["data"], {"hallazgos": {"validaciones": []}})

    def test_envelope_error_has_no_data(self) -> None:
        rec = self._record(
            {
                "back_data_status": "error",
                "back_data_run_id": "r1",
                "back_data_error": {"status_code": 409, "type": "DataSourceError"},
            }
        )
        env = self.store.get_workflow_back_data_envelope(
            rec, "centrales_de_riesgo", reference_at=self.now
        )
        self.assertEqual(env["status"], "error")
        self.assertIsNone(env["data"])
        self.assertEqual(env["error"]["status_code"], 409)

    async def test_clear_sets_pending_and_drops_data_and_run_id(self) -> None:
        await self.store.save_record(
            self._record(
                {"back_data_status": "ok", "back_data_run_id": "r1", "data": {"x": 1}}
            )
        )
        await self.store.clear_workflow_back_data(
            client_id="123", workflow_id="centrales_de_riesgo", reference_at=self.now
        )
        rec = await self.store.get_record("123")
        env = self.store.get_workflow_back_data_envelope(
            rec, "centrales_de_riesgo", reference_at=self.now
        )
        self.assertEqual(env["status"], "pending")
        self.assertIsNone(env["data"])
        self.assertIsNone(env["run_id"])


class _FakeControlStore:
    """Doble del store con la MISMA firma que el real.

    ``expected_run_id`` y ``describe_back_data_envelopes`` se anadieron en C3 y
    Fase 0 (02/09); el doble los refleja para que la prueba falle si la firma de
    produccion vuelve a cambiar sin actualizar aqui.
    """

    def __init__(self, envelope: dict) -> None:
        self.envelope = envelope
        self.run_ids_recibidos: list[str | None] = []

    async def get_record(self, client_id: str):
        return {"present": True}

    def get_workflow_back_data_envelope(
        self, record, workflow_id, *, reference_at=None, expected_run_id=None
    ):
        self.run_ids_recibidos.append(expected_run_id)
        return self.envelope

    def describe_back_data_envelopes(
        self, record, workflow_id, *, reference_at=None
    ) -> dict:
        return {"documento_existe": bool(record), "envelopes": {}}


class PollFreshnessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._orig_attempts = chat_service._BACK_DATA_MAX_POLL_ATTEMPTS
        self._orig_interval = chat_service._BACK_DATA_POLL_INTERVAL_SECONDS
        chat_service._BACK_DATA_MAX_POLL_ATTEMPTS = 2
        chat_service._BACK_DATA_POLL_INTERVAL_SECONDS = 0
        self.conv = types.SimpleNamespace(conversation_id="123_20260716")

    def tearDown(self) -> None:
        chat_service._BACK_DATA_MAX_POLL_ATTEMPTS = self._orig_attempts
        chat_service._BACK_DATA_POLL_INTERVAL_SECONDS = self._orig_interval

    async def test_ok_with_matching_run_id_returns_ok(self) -> None:
        store = _FakeControlStore(
            {"status": "ok", "run_id": "r1", "data": {"hallazgos": {}}, "error": None}
        )
        status, data = await chat_service._load_back_data_from_control_table(
            conversation=self.conv,
            control_store=store,
            user_id="123",
            workflow_id="centrales_de_riesgo",
            expected_run_id="r1",
        )
        self.assertEqual(status, "ok")
        self.assertEqual(data, {"hallazgos": {}})

    async def test_error_envelope_returns_error(self) -> None:
        store = _FakeControlStore(
            {"status": "error", "run_id": "r1", "data": None, "error": {"status_code": 409}}
        )
        status, data = await chat_service._load_back_data_from_control_table(
            conversation=self.conv,
            control_store=store,
            user_id="123",
            workflow_id="centrales_de_riesgo",
            expected_run_id="r1",
        )
        self.assertEqual(status, "error")
        self.assertIsNone(data)

    async def test_stale_run_id_is_rejected_as_timeout(self) -> None:
        # OK status but a DIFFERENT run_id (stale) must NOT be served.
        store = _FakeControlStore(
            {"status": "ok", "run_id": "OLD", "data": {"hallazgos": {}}, "error": None}
        )
        status, data = await chat_service._load_back_data_from_control_table(
            conversation=self.conv,
            control_store=store,
            user_id="123",
            workflow_id="centrales_de_riesgo",
            expected_run_id="r1",
        )
        self.assertEqual(status, "timeout")
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()

class TimeoutLlevaDiagnosticoTests(unittest.IsolatedAsyncioTestCase):
    """Fase 0: el timeout tiene que dejar el diagnostico EN LA TRAZA.

    Es la pieza en la que se confia para no volver a diagnosticar a ciegas: si el
    sondeo agota su presupuesto, la traza que llega al bucket de auditoria debe
    decir que habia en el registro (meses, estados, run_id truncado), no solo
    "attempts".
    """

    def setUp(self) -> None:
        self._orig_attempts = chat_service._BACK_DATA_MAX_POLL_ATTEMPTS
        self._orig_interval = chat_service._BACK_DATA_POLL_INTERVAL_SECONDS
        chat_service._BACK_DATA_MAX_POLL_ATTEMPTS = 1
        chat_service._BACK_DATA_POLL_INTERVAL_SECONDS = 0
        self.conv = types.SimpleNamespace(conversation_id="777_20260902")
        self.eventos: list[dict] = []
        self._orig_trace = chat_service.schedule_trace_event
        chat_service.schedule_trace_event = lambda **kw: self.eventos.append(kw)

    def tearDown(self) -> None:
        chat_service._BACK_DATA_MAX_POLL_ATTEMPTS = self._orig_attempts
        chat_service._BACK_DATA_POLL_INTERVAL_SECONDS = self._orig_interval
        chat_service.schedule_trace_event = self._orig_trace

    async def test_el_timeout_emite_el_diagnostico(self) -> None:
        class _StoreConDiagnostico(_FakeControlStore):
            def describe_back_data_envelopes(
                self, record, workflow_id, *, reference_at=None
            ) -> dict:
                return {
                    "documento_existe": True,
                    "mes_actual": "2026-09",
                    "meses_en_el_registro": ["2026-08", "2026-09"],
                    "meses_con_el_workflow": ["2026-08"],
                    "envelopes": {"2026-08": {"status": "ok", "run_id": "35fbd471"}},
                }

        store = _StoreConDiagnostico(
            {"status": "pending", "run_id": None, "data": None, "error": None}
        )
        status, data = await chat_service._load_back_data_from_control_table(
            conversation=self.conv,
            control_store=store,
            user_id="777",
            workflow_id="centrales_de_riesgo",
            expected_run_id="fresco",
        )
        self.assertEqual(status, "timeout")
        self.assertIsNone(data)

        timeouts = [
            e for e in self.eventos
            if e.get("operation") == "back_data_control_table"
            and e.get("outcome") == "timeout"
        ]
        self.assertEqual(len(timeouts), 1, "debe emitirse UNA traza de timeout")
        resumen = timeouts[0].get("response_summary") or {}
        self.assertTrue(resumen, "la traza de timeout ya no puede ir vacia")
        self.assertEqual(resumen["meses_con_el_workflow"], ["2026-08"])
        self.assertEqual(resumen["mes_actual"], "2026-09")
        self.assertIn("2026-08", resumen["envelopes"])

    async def test_si_el_diagnostico_falla_el_turno_no_se_rompe(self) -> None:
        """Fail-open: la observabilidad nunca puede tumbar el turno."""

        class _StoreQueExplota(_FakeControlStore):
            def describe_back_data_envelopes(self, *a, **kw) -> dict:
                raise RuntimeError("opensearch caido")

        store = _StoreQueExplota(
            {"status": "pending", "run_id": None, "data": None, "error": None}
        )
        status, data = await chat_service._load_back_data_from_control_table(
            conversation=self.conv,
            control_store=store,
            user_id="777",
            workflow_id="centrales_de_riesgo",
            expected_run_id="fresco",
        )
        self.assertEqual(status, "timeout", "el turno tiene que terminar igual")
        timeouts = [
            e for e in self.eventos
            if e.get("outcome") == "timeout"
        ]
        self.assertEqual(len(timeouts), 1, "la traza se emite aunque sin diagnostico")

