"""Tests for Layer B: per-category daily cap + repeat-flow re-checks."""

import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

# Stub the optional 'strands' dependency before importing chat_service.
_fake_strands = types.ModuleType("strands")


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        pass


_fake_strands.Agent = _FakeAgent
sys.modules.setdefault("strands", _fake_strands)

import application.chat.chat_service as cs  # noqa: E402
from domain.conversation.models import (  # noqa: E402
    Conversation,
    ConversationStatus,
    MessageRole,
    TokenUsage,
)
from domain.workflow.general_messages import load_general_messages  # noqa: E402
from domain.workflow.workflow_engine import WorkflowEngine  # noqa: E402


class FakeCapControlStore:
    """Fake control store exposing the per-category and recheck counter APIs."""

    def __init__(
        self,
        *,
        category_counts: dict | None = None,
        recheck_count: int = 0,
        category_labels: dict | None = None,
    ) -> None:
        self._category_counts = dict(category_counts or {})
        self._recheck_count = recheck_count
        self._recheck_counts: dict[str, int] = {}
        self._category_labels = dict(category_labels or {})
        self.record_recheck_calls = 0
        self.record_category_calls: list[tuple[str, str]] = []
        self.blocked_for_day = False

    def is_blocked_for_day(self, record, *, reference_at=None) -> bool:
        return self.blocked_for_day

    async def set_blocked_for_day(self, client_id: str, *, interaction_at=None) -> None:
        self.blocked_for_day = True

    async def get_record(self, client_id: str):
        return {"client_id": client_id}

    def get_category_day_count(self, record, category, *, reference_at=None) -> int:
        return int(self._category_counts.get(category, 0))

    def get_category_last_flow_label(self, record, category, *, reference_at=None):
        return self._category_labels.get(category)

    def get_recheck_count(self, record, category, *, reference_at=None) -> int:
        if category in self._recheck_counts:
            return self._recheck_counts[category]
        return self._recheck_count

    async def record_recheck(
        self, client_id: str, category: str, *, interaction_at=None
    ) -> None:
        self.record_recheck_calls += 1
        self._recheck_counts[category] = (
            self._recheck_counts.get(category, self._recheck_count) + 1
        )

    async def record_category_interaction(
        self, *, client_id: str, category: str, workflow_label: str, interaction_at=None
    ) -> None:
        self.record_category_calls.append((category, workflow_label))
        self._category_counts[category] = (
            int(self._category_counts.get(category, 0)) + 1
        )


def _conversation() -> Conversation:
    return Conversation(
        conversation_id="10482895_20260701",
        status=ConversationStatus.ACTIVE,
        current_step="start",
        user_id="10482895",
        messages=[],
    )


@patch.object(cs, "load_max_daily_category_interactions", return_value=3)
class CategoryCapTests(unittest.IsolatedAsyncioTestCase):
    """Per-CASE daily cap (limit key = workflow). Centrales is skipped here and
    handled per sub-flow at step 1.4.1."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()
        cls.messages = load_general_messages()

    async def test_under_cap_proceeds(self, _max_cat) -> None:
        conv = _conversation()
        # Same case under its own cap (keyed by workflow name).
        store = FakeCapControlStore(category_counts={"impuesto_4x1000": 2})

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="impuesto_4x1000",
        )

        self.assertIsNone(result)
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)
        self.assertEqual(store.record_recheck_calls, 0)

    async def test_centrales_is_skipped_at_start(self, _max_cat) -> None:
        # Centrales is capped per SUB-FLOW at 1.4.1, so the start-time cap must
        # NOT fire even if some "centrales" bucket is high.
        conv = _conversation()
        store = FakeCapControlStore(category_counts={"centrales_de_riesgo": 99})

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="centrales_de_riesgo",
        )

        self.assertIsNone(result)
        self.assertEqual(store.record_recheck_calls, 0)
        self.assertFalse(cs._has_pending_repeat_flow_warning(conv))

    async def test_case_cap_reached_shows_warning_with_label(
        self, _max_cat
    ) -> None:
        conv = _conversation()
        store = FakeCapControlStore(
            category_counts={"impuesto_4x1000": 3},
            category_labels={"impuesto_4x1000": "Impuesto 4x1000"},
        )

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="impuesto_4x1000",
        )

        expected = self.messages.repeated_flow_warning_template.format(
            last_flow_label="Impuesto 4x1000"
        )
        self.assertEqual(result, expected)
        self.assertTrue(cs._has_pending_repeat_flow_warning(conv))

    async def test_case_cap_uses_option_label_fallback(
        self, _max_cat
    ) -> None:
        conv = _conversation()
        store = FakeCapControlStore(
            category_counts={"impuesto_4x1000": 3}, category_labels={}
        )

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="impuesto_4x1000",
        )

        self.assertIn("Impuesto 4x1000", result)

    async def test_only_that_case_blocked_others_free(
        self, _max_cat
    ) -> None:
        # One case is capped, a DIFFERENT case has its own (empty) counter.
        conv = _conversation()
        store = FakeCapControlStore(
            category_counts={"certificado_de_cuenta": 3, "impuesto_4x1000": 0}
        )

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="impuesto_4x1000",
        )

        self.assertIsNone(result)

    async def test_trx_case_capped_shows_warning(self, _max_cat) -> None:
        conv = _conversation()
        store = FakeCapControlStore(category_counts={"trx_no_reconocida": 3})

        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=store,
            workflow_engine=self.engine,
            workflow="trx_no_reconocida",
        )

        self.assertIsNotNone(result)
        self.assertIn("Transaccion no reconocida", result)

    async def test_no_control_store_proceeds(self, _max_cat) -> None:
        conv = _conversation()
        result = await cs._maybe_handle_category_cap(
            conversation=conv,
            control_store=None,
            workflow_engine=self.engine,
            workflow="impuesto_4x1000",
        )
        self.assertIsNone(result)


@patch.object(cs, "load_max_daily_category_interactions", return_value=3)
class CentralesSubflowCapTests(unittest.IsolatedAsyncioTestCase):
    """Per-SUB-FLOW daily cap for centrales de riesgo (key
    ``centrales_de_riesgo:<subflow>``). No global centrales cap."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.messages = load_general_messages()

    def _centrales_conversation(self) -> Conversation:
        conv = _conversation()
        conv.workflow = "centrales_de_riesgo"
        conv.current_step = "1.4.1.2"
        return conv

        def test_new_subflows_have_distinct_limit_labels(self) -> None:
            self.assertEqual(
                cs._CENTRALES_SUBFLOW_LABELS["embargo_o_desembargo"],
                "tu embargo o desembargo",
            )
            self.assertEqual(
                cs._CENTRALES_SUBFLOW_LABELS["cartera_vendida_o_cedida"],
                "la venta o cesión de tu cartera",
            )

    async def test_subflow_under_cap_records_and_proceeds(self, _max_cat) -> None:
        conv = self._centrales_conversation()
        store = FakeCapControlStore(
            category_counts={"centrales_de_riesgo:consulta_sin_permiso": 2}
        )

        result = await cs._maybe_handle_centrales_subflow_cap(
            conversation=conv,
            control_store=store,
            subflow_key="consulta_sin_permiso",
        )

        self.assertIsNone(result)
        self.assertIn(
            "centrales_de_riesgo:consulta_sin_permiso",
            [c[0] for c in store.record_category_calls],
        )
        self.assertEqual(conv.workflow, "centrales_de_riesgo")

    async def test_subflow_cap_reached_resets_and_warns(self, _max_cat) -> None:
        conv = self._centrales_conversation()
        store = FakeCapControlStore(
            category_counts={"centrales_de_riesgo:consulta_sin_permiso": 3}
        )

        result = await cs._maybe_handle_centrales_subflow_cap(
            conversation=conv,
            control_store=store,
            subflow_key="consulta_sin_permiso",
        )

        # Shows the repeat-flow warning and resets to the start phase so the
        # existing Sí/No machinery handles the next turn.
        self.assertIsNotNone(result)
        self.assertIn("consulta", result.lower())
        self.assertTrue(cs._has_pending_repeat_flow_warning(conv))
        self.assertIsNone(conv.workflow)
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)

    async def test_only_that_subflow_blocked_others_free(self, _max_cat) -> None:
        conv = self._centrales_conversation()
        # consulta_sin_permiso is capped; a different sub-flow is still free.
        store = FakeCapControlStore(
            category_counts={
                "centrales_de_riesgo:consulta_sin_permiso": 3,
                "centrales_de_riesgo:reporte_negativo_sin_notificacion": 0,
            }
        )

        result = await cs._maybe_handle_centrales_subflow_cap(
            conversation=conv,
            control_store=store,
            subflow_key="reporte_negativo_sin_notificacion",
        )

        self.assertIsNone(result)
        self.assertEqual(conv.workflow, "centrales_de_riesgo")

    async def test_no_control_store_proceeds(self, _max_cat) -> None:
        conv = self._centrales_conversation()
        result = await cs._maybe_handle_centrales_subflow_cap(
            conversation=conv,
            control_store=None,
            subflow_key="consulta_sin_permiso",
        )
        self.assertIsNone(result)


@patch.object(cs, "load_max_daily_category_interactions", return_value=3)
class RepeatFlowYesShortCircuitTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()
        cls.messages = load_general_messages()

    async def _resolve(self, conv, store):
        return await cs._resolve_start_phase(
            conversation=conv,
            user_content="si",
            workflow_engine=self.engine,
            strands_agent=object(),
            control_store=store,
            turn_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )

    async def test_yes_continues_when_under_recheck_budget(
        self, _max_cat
    ) -> None:
        conv = _conversation()
        cs._set_pending_repeat_flow_warning(
            conv, workflow="centrales_de_riesgo", last_flow_label="Centrales de Riesgo"
        )
        store = FakeCapControlStore(recheck_count=1)

        result = await self._resolve(conv, store)

        self.assertEqual(result, self.messages.repeated_flow_continue_message)
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)

    async def test_yes_always_continues(self, _max_cat) -> None:
        conv = _conversation()
        cs._set_pending_repeat_flow_warning(
            conv, workflow="centrales_de_riesgo", last_flow_label="Centrales de Riesgo"
        )
        store = FakeCapControlStore(recheck_count=99)

        result = await self._resolve(conv, store)

        self.assertEqual(result, self.messages.repeated_flow_continue_message)
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)
        self.assertFalse(store.blocked_for_day)

    async def test_no_declines_closes_session(self, _max_cat) -> None:
        conv = _conversation()
        cs._set_pending_repeat_flow_warning(
            conv, workflow="centrales_de_riesgo", last_flow_label="Centrales de Riesgo"
        )
        store = FakeCapControlStore(recheck_count=1)

        result = await cs._resolve_start_phase(
            conversation=conv,
            user_content="no",
            workflow_engine=self.engine,
            strands_agent=object(),
            control_store=store,
            turn_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )

        self.assertEqual(result, self.messages.repeated_flow_decline_message)
        self.assertEqual(conv.status, ConversationStatus.CLOSED)
        # Declining ends the session but is NOT a full-day block.
        self.assertFalse(store.blocked_for_day)


class _FakeTurnStore:
    """Minimal async store to drive _process_message_turn in isolation."""

    def __init__(self) -> None:
        self.saved_messages: list = []
        self.saved_references = 0

    async def save_message(self, conversation_id: str, message) -> None:
        self.saved_messages.append(message)

    async def refresh(self) -> None:
        pass

    async def save_conversation_reference(self, conversation) -> None:
        self.saved_references += 1


class ArchitectureADecoupleTests(unittest.IsolatedAsyncioTestCase):
    """Architecture A: a /chat turn never ends the session; a consultation
    terminal returns to the start phase so the session stays open for more
    consultations. The session closes only via /end or maintenance abandon."""

    async def test_consultation_terminal_returns_to_start_and_keeps_session_open(
        self,
    ) -> None:
        conv = _conversation()
        # Simulate an in-progress workflow that reaches its terminal this turn.
        conv.workflow = "centrales_de_riesgo"
        conv.current_step = "1.4.1"
        store = _FakeTurnStore()

        terminal_message = "Gracias por contactarnos. Que tengas un buen dia."

        async def _fake_resolve(*, conversation, **_kwargs):
            # A workflow terminal closes the consultation and emits its message.
            conversation.status = ConversationStatus.CLOSED
            conversation.current_step = "satisfaction_check"
            return (
                terminal_message,
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )

        with patch.object(cs, "_resolve_assistant_content", _fake_resolve), patch.object(
            cs, "_emit_event", lambda *a, **k: None
        ):
            result = await cs._process_message_turn(
                conversation=conv,
                content="si",
                store=store,
                workflow_engine=object(),
                strands_agent=object(),
                control_store=None,
                back_data_service_url=None,
            )

        # Session kept open and returned to the start phase (not CLOSED).
        self.assertEqual(result.status, ConversationStatus.ACTIVE)
        self.assertEqual(result.current_step, "start")
        self.assertIsNone(result.workflow)
        # The terminal message was still delivered as the last assistant message.
        self.assertEqual(result.messages[-1].role, MessageRole.ASSISTANT)
        self.assertEqual(result.messages[-1].content, terminal_message)

    async def test_limit_terminated_close_is_not_reopened(self) -> None:
        # A close marked as a session limit must STAY closed (no reopen loop).
        conv = _conversation()
        store = _FakeTurnStore()

        async def _fake_resolve(*, conversation, **_kwargs):
            conversation.status = ConversationStatus.CLOSED
            conversation.captured_data[cs._SESSION_LIMIT_CLOSED_KEY] = "true"
            return (
                "Alcanzaste el limite. Intenta mas tarde.",
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )

        with patch.object(cs, "_resolve_assistant_content", _fake_resolve), patch.object(
            cs, "_emit_event", lambda *a, **k: None
        ):
            result = await cs._process_message_turn(
                conversation=conv,
                content="hola",
                store=store,
                workflow_engine=object(),
                strands_agent=object(),
                control_store=None,
                back_data_service_url=None,
            )

        self.assertEqual(result.status, ConversationStatus.CLOSED)

    async def test_turn_on_closed_session_returns_cached_message_without_llm(
        self,
    ) -> None:
        self.skipTest("Guard barato removido: UX permite consultar indefinidamente")


if __name__ == "__main__":
    unittest.main()
