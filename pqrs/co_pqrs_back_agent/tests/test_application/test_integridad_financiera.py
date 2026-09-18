"""Idempotencia, concurrencia y aislamiento de las acciones con efecto (KYNS IT 4.4 / 4.5 / IT 3).

Pruebas unitarias sobre las piezas que protegen la integridad financiera:
la huella de las transacciones acumuladas para Tantia, la ficha durable del
caso, el candado del bloqueo, el turno unico por conversacion y la derivacion
del id de conversacion desde el cliente.
"""

import sys
import types
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

fake_strands = types.ModuleType("strands")
fake_strands.Agent = type("Agent", (), {"__init__": lambda self, *a, **k: None})
sys.modules.setdefault("strands", fake_strands)

import application.chat.chat_service as cs  # noqa: E402
from application.chat.trx_state import get_trx_state  # noqa: E402
from domain.conversation.models import Conversation, ConversationStatus  # noqa: E402
from infrastructure.persistence.trx_case_store import TrxCaseStore  # noqa: E402


def _conv(customer="10482895", **kw) -> Conversation:
    base = dict(conversation_id=f"{customer}_20260909", status=ConversationStatus.ACTIVE,
                current_step="2.4.0.1.20", user_id=customer, messages=[])
    base.update(kw)
    return Conversation(**base)


def _payload(statement="S1", movement="M1", valor="120000"):
    return {"detalle": {"statementDetail": {"statementId": statement, "movementId": movement}},
            "fecha_trx": "05/08/2026", "movimiento_valor": valor}


class TantiaAccumulationTests(unittest.TestCase):
    """IT 4.4: doble envio / reintento del paso de abono no duplica la fila."""

    def test_same_transaction_twice_is_one_row(self) -> None:
        conversation = _conv()
        self.assertEqual(cs._trx_append_tantia_item(conversation, _payload()), 1)
        self.assertEqual(cs._trx_append_tantia_item(conversation, _payload()), 1)
        self.assertEqual(len(get_trx_state(conversation)["tantia_items"]), 1)

    def test_a_different_transaction_is_added(self) -> None:
        conversation = _conv()
        cs._trx_append_tantia_item(conversation, _payload())
        self.assertEqual(cs._trx_append_tantia_item(conversation, _payload(movement="M2")), 2)

    def test_fingerprint_prefers_the_aso_identity_over_date_and_amount(self) -> None:
        self.assertEqual(cs._trx_item_fingerprint(_payload()), "S1|M1")
        self.assertEqual(cs._trx_item_fingerprint({"tx_id": "abc"}), "tx:abc")
        # Sin identidad del ASO ni id: la fecha y el valor son lo unico que hay.
        self.assertEqual(cs._trx_item_fingerprint({"fecha_trx": "05/08/2026", "movimiento_valor": "1"}), "05/08/2026|1")


class DurableCaseIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    """IT 4.4: la ficha del caso es una por cliente y flujo; un hito repetido no se duplica."""

    def _store(self, existing=None) -> tuple[TrxCaseStore, list]:
        store = TrxCaseStore.__new__(TrxCaseStore)
        store.index = "trx-no-reconocida-cases"
        calls: list = []

        async def update_document(index, doc_id, record, upsert=False):
            calls.append((index, doc_id, record, upsert))
            self.saved = record

        store.client = types.SimpleNamespace(update_document=update_document)
        store.get_case = AsyncMock(side_effect=lambda cid, tipo_de_notificacion=None: getattr(self, "saved", existing))
        return store, calls

    async def test_milestone_twice_keeps_one_document_and_one_milestone(self) -> None:
        store, calls = self._store()
        for _ in range(2):
            await store.record_milestone(client_id="10482895", conversation_id="10482895_20260909",
                                         milestone="devolucion", outcome="devolucion")
        self.assertEqual({c[1] for c in calls}, {"10482895"})          # mismo documento
        self.assertTrue(all(c[3] for c in calls))                       # upsert, nunca crea otro
        self.assertEqual(self.saved["milestones"].count("devolucion"), 1)

    def test_document_id_isolates_flows_without_renaming_the_historic_one(self) -> None:
        self.assertEqual(TrxCaseStore.document_id("10482895", "trx_no_reconocida"), "10482895")
        self.assertEqual(TrxCaseStore.document_id("10482895", "doble_cobro"), "doble_cobro_10482895")
        self.assertNotEqual(TrxCaseStore.document_id("1", "doble_cobro"), TrxCaseStore.document_id("2", "doble_cobro"))


class BlockReexecutionLockTests(unittest.IsolatedAsyncioTestCase):
    """IT 4.5: accion ejecutada con fallo posterior -> el reintento no vuelve a bloquear."""

    async def test_lock_is_read_from_the_durable_record(self) -> None:
        with patch.object(cs, "TrxCaseStore") as store_cls:
            store_cls.return_value.get_case = AsyncMock(return_value={"milestones": ["reached_block_temporal"]})
            self.assertTrue(await cs._trx_bloqueo_ya_ejecutado(_conv(), "reached_block_temporal"))
            self.assertFalse(await cs._trx_bloqueo_ya_ejecutado(_conv(), "reached_block_permanente"))

    async def test_lock_fails_open_when_the_record_cannot_be_read(self) -> None:
        with patch.object(cs, "TrxCaseStore", side_effect=RuntimeError("opensearch caido")):
            self.assertFalse(await cs._trx_bloqueo_ya_ejecutado(_conv(), "reached_block_temporal"))


class _Store:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation
        self.saves = 0

    async def load_conversation(self, conversation_id: str):
        return self.conversation if conversation_id == self.conversation.conversation_id else None

    async def save_conversation_reference(self, conversation) -> None:
        self.saves += 1

    async def refresh(self) -> None:
        return None


class SingleTurnPerConversationTests(unittest.IsolatedAsyncioTestCase):
    """IT 4.4: dos envios concurrentes -> el segundo no arranca un turno paralelo."""

    async def test_second_turn_while_running_is_ignored(self) -> None:
        conversation = _conv(status=ConversationStatus.RUNNING)
        conversation.running_since = datetime.now(UTC)
        store = _Store(conversation)
        with patch.object(cs.asyncio, "create_task") as create_task:
            result = await cs.process_chat_message_with_timeout(
                content="Confirmo el abono", conversation_id=conversation.conversation_id,
                store=store, workflow_engine=None, strands_agent=None,
            )
        self.assertIsNone(result)
        create_task.assert_not_called()
        self.assertEqual(store.saves, 0)


class ConversationIsolationTests(unittest.TestCase):
    """IT 3: el id de conversacion nace del cliente; dos clientes nunca comparten ficha."""

    def test_conversation_id_is_derived_from_the_customer(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        self.assertEqual(cs._build_conversation_id("10482895"), f"10482895_{today}")
        self.assertNotEqual(cs._build_conversation_id("10482895"), cs._build_conversation_id("10482896"))

    def test_customer_id_is_taken_from_the_conversation_not_from_the_caller(self) -> None:
        # No hay parametro del llamador que pueda apuntar a otra ficha: el cliente
        # sale del propio id. La autenticacion del canal es la que impide que un
        # tercero conozca ese id (ver docs/AUTONOMIA_E_INTEGRIDAD.md).
        self.assertEqual(cs._extract_customer_id("10482895_20260909"), "10482895")
