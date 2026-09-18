"""Tests for the ``source`` field on the analytics events (``benchmark`` | ``live``).

A conversation opened by the benchmark/canary (``POST /start`` with the
``X-Benchmark-Mode`` header) is marked persistently in ``captured_data`` and
EVERY ``conversation.*`` event of that conversation must carry
``source="benchmark"``; any other conversation carries ``source="live"``.
"""

import sys
import types
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
    TokenUsage,
)
from infrastructure.observability import benchmark_context  # noqa: E402
from infrastructure.persistence.conversation_store import (  # noqa: E402
    ConversationStore,
)


def _conv(marked: bool = False) -> Conversation:
    conversation = Conversation(
        conversation_id="10482895_20260701",
        status=ConversationStatus.ACTIVE,
        current_step="start",
        user_id="10482895",
        messages=[],
    )
    if marked:
        conversation.captured_data[cs._EVENT_SOURCE_KEY] = cs._EVENT_SOURCE_BENCHMARK
    return conversation


def _usage() -> TokenUsage:
    return TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2)


def _all_events(conversation: Conversation) -> dict[str, dict[str, object]]:
    """Build one payload of every conversation.* event type."""

    return {
        "started": cs._build_started_event(conversation),
        "turn": cs._build_turn_event(conversation, turn_usage=_usage(), duration_ms=1),
        "trace": cs._build_trace_event(conversation, turn_usage=_usage(), duration_ms=1),
        "closed": cs._build_closed_event(conversation),
        "cap_reached": cs._build_cap_reached_event(
            conversation,
            limit_key="doble_cobro",
            limit_label="Doble cobro",
            limit_scope="case",
        ),
        "error": cs._build_error_event(
            conversation.conversation_id, RuntimeError("boom"), conversation
        ),
    }


class InMemoryConversationStore:
    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list] = {}
        self.save_conversation_reference_call_count = 0

    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def save_conversation_reference(self, conversation: Conversation) -> None:
        self.save_conversation_reference_call_count += 1
        self.conversations[conversation.conversation_id] = conversation

    async def save_message(self, conversation_id: str, message) -> None:
        self.messages.setdefault(conversation_id, []).append(message)

    async def refresh(self) -> None:
        return None

    async def delete_conversation_messages(self, conversation_id: str) -> None:
        self.messages[conversation_id] = []


class EventSourceHelperTests(unittest.TestCase):
    def test_live_when_no_mark_and_no_context(self) -> None:
        self.assertFalse(benchmark_context.is_active())
        self.assertEqual(cs._event_source(_conv()), "live")

    def test_benchmark_when_marked(self) -> None:
        self.assertEqual(cs._event_source(_conv(marked=True)), "benchmark")

    def test_live_when_conversation_is_none(self) -> None:
        self.assertEqual(cs._event_source(None), "live")

    def test_fallback_to_active_benchmark_context(self) -> None:
        token = benchmark_context.start_capture()
        try:
            self.assertTrue(benchmark_context.is_active())
            self.assertEqual(cs._event_source(_conv()), "benchmark")
            self.assertEqual(cs._event_source(None), "benchmark")
        finally:
            benchmark_context.finish_capture(token)
        self.assertFalse(benchmark_context.is_active())
        self.assertEqual(cs._event_source(_conv()), "live")

    def test_mark_is_idempotent(self) -> None:
        conversation = _conv()
        self.assertTrue(cs._mark_benchmark_conversation(conversation))
        self.assertFalse(cs._mark_benchmark_conversation(conversation))
        self.assertEqual(conversation.captured_data["source"], "benchmark")


class EventPayloadSourceTests(unittest.TestCase):
    def test_every_event_type_carries_source_live(self) -> None:
        for name, payload in _all_events(_conv()).items():
            with self.subTest(event=name):
                self.assertIn("source", payload)
                self.assertEqual(payload["source"], "live")
                self.assertEqual(payload["event"], f"conversation.{name}")

    def test_every_event_type_carries_source_benchmark_when_marked(self) -> None:
        for name, payload in _all_events(_conv(marked=True)).items():
            with self.subTest(event=name):
                self.assertEqual(payload["source"], "benchmark")

    def test_error_event_without_conversation_defaults_to_live(self) -> None:
        payload = cs._build_error_event("10482895_20260701", RuntimeError("x"))
        self.assertEqual(payload["source"], "live")

    def test_existing_fields_are_untouched(self) -> None:
        turn = cs._build_turn_event(_conv(), turn_usage=_usage(), duration_ms=5)
        for field in (
            "event", "conversation_id", "user_id", "workflow", "status",
            "tokens", "duration_ms", "llm_used", "routing_outcome", "ts",
        ):
            self.assertIn(field, turn)
        closed = cs._build_closed_event(_conv())
        self.assertIn("resolution", closed)
        self.assertIn("duration_total_ms", closed)


class MarkPersistenceTests(unittest.TestCase):
    def test_reroute_reset_preserves_the_mark(self) -> None:
        conversation = _conv(marked=True)
        conversation.workflow = "doble_cobro"
        conversation.captured_data["routing_outcome"] = "matched"
        cs._reset_conversation_for_reroute(conversation)
        self.assertEqual(conversation.captured_data, {"source": "benchmark"})
        self.assertIsNone(conversation.workflow)

    def test_reroute_reset_keeps_live_conversation_unmarked(self) -> None:
        conversation = _conv()
        conversation.captured_data["routing_outcome"] = "matched"
        cs._reset_conversation_for_reroute(conversation)
        self.assertEqual(conversation.captured_data, {})

    def test_mark_survives_opensearch_serialization_roundtrip(self) -> None:
        store = ConversationStore.__new__(ConversationStore)
        conversation = _conv(marked=True)
        serialized = store._serialize_conversation(conversation)
        self.assertEqual(serialized["captured_data"]["source"], "benchmark")
        restored = store._deserialize_conversation(serialized, messages=[])
        self.assertEqual(cs._event_source(restored), "benchmark")


class StartMarksConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._name_patch = patch(
            "application.chat.chat_service._resolve_customer_given_name",
            new=AsyncMock(return_value=""),
        )
        self._name_patch.start()
        self._emitted: list[tuple[str, dict[str, object]]] = []
        self._emit_patch = patch.object(
            cs, "_emit_event", side_effect=lambda key, payload: self._emitted.append((key, payload))
        )
        self._emit_patch.start()

    def tearDown(self) -> None:
        self._emit_patch.stop()
        self._name_patch.stop()

    async def test_start_with_benchmark_mode_marks_and_persists(self) -> None:
        store = InMemoryConversationStore()

        conversation = await cs.process_start_message(
            user_id="03966512", store=store, benchmark_mode=True
        )

        self.assertEqual(conversation.captured_data["source"], "benchmark")
        persisted = store.conversations[conversation.conversation_id]
        self.assertEqual(persisted.captured_data["source"], "benchmark")
        self.assertEqual(len(self._emitted), 1)
        key, payload = self._emitted[0]
        self.assertEqual(key, "conversation.started")
        self.assertEqual(payload["source"], "benchmark")

    async def test_start_without_benchmark_mode_is_live(self) -> None:
        store = InMemoryConversationStore()

        conversation = await cs.process_start_message(user_id="03966512", store=store)

        self.assertNotIn("source", conversation.captured_data)
        key, payload = self._emitted[0]
        self.assertEqual(key, "conversation.started")
        self.assertEqual(payload["source"], "live")

    async def test_start_falls_back_to_active_benchmark_context(self) -> None:
        store = InMemoryConversationStore()
        token = benchmark_context.start_capture()
        try:
            conversation = await cs.process_start_message(
                user_id="03966512", store=store
            )
        finally:
            benchmark_context.finish_capture(token)

        self.assertEqual(conversation.captured_data["source"], "benchmark")

    async def test_idempotent_start_marks_resumed_session(self) -> None:
        store = InMemoryConversationStore()
        first = await cs.process_start_message(user_id="03966512", store=store)
        self.assertNotIn("source", first.captured_data)
        saves_before = store.save_conversation_reference_call_count

        resumed = await cs.process_start_message(
            user_id="03966512", store=store, benchmark_mode=True
        )

        self.assertIs(resumed, first)
        self.assertEqual(resumed.captured_data["source"], "benchmark")
        self.assertEqual(store.save_conversation_reference_call_count, saves_before + 1)

    async def test_end_without_header_emits_closed_with_benchmark_source(self) -> None:
        # Cierre posterior SIN cabecera (p.ej. /end disparado por mantenimiento):
        # el evento closed debe leer la marca persistida.
        store = InMemoryConversationStore()
        conversation = await cs.process_start_message(
            user_id="03966512", store=store, benchmark_mode=True
        )
        self._emitted.clear()
        self.assertFalse(benchmark_context.is_active())

        with patch.object(cs, "_notify_end_conversation_callback", new=AsyncMock()):
            closed = await cs.process_end_conversation(
                conversation_id=conversation.conversation_id, store=store
            )

        self.assertEqual(closed.status, ConversationStatus.CLOSED)
        self.assertEqual(len(self._emitted), 1)
        key, payload = self._emitted[0]
        self.assertEqual(key, "conversation.closed")
        self.assertEqual(payload["source"], "benchmark")

    async def test_end_of_live_conversation_emits_closed_with_live_source(self) -> None:
        store = InMemoryConversationStore()
        conversation = await cs.process_start_message(user_id="03966512", store=store)
        self._emitted.clear()

        with patch.object(cs, "_notify_end_conversation_callback", new=AsyncMock()):
            await cs.process_end_conversation(
                conversation_id=conversation.conversation_id, store=store
            )

        key, payload = self._emitted[0]
        self.assertEqual(key, "conversation.closed")
        self.assertEqual(payload["source"], "live")


class StartRouteHeaderTests(unittest.TestCase):
    """``POST /start`` reads ``X-Benchmark-Mode`` and forwards ``benchmark_mode``."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from infrastructure.entrypoint import fastapi_app
        from infrastructure.entrypoint.api import dependencies as deps

        self.app = fastapi_app.app
        self.app.dependency_overrides[deps.get_conversation_store] = lambda: object()
        self.app.dependency_overrides[deps.get_control_table_store] = lambda: None
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def _post_start(self, headers: dict[str, str]) -> AsyncMock:
        from infrastructure.entrypoint.api.router.v0 import chat_router

        conversation = _conv()
        now = datetime.now(UTC)
        conversation.add_message(
            cs._build_assistant_message("Hola", received_at=now, responded_at=now)
        )
        fake_start = AsyncMock(return_value=conversation)
        with patch.object(chat_router, "process_start_message", new=fake_start):
            response = self.client.post(
                "/start", json={"user_id": "10482895"}, headers=headers
            )
        self.assertEqual(response.status_code, 201, response.text)
        return fake_start

    def test_header_present_forwards_benchmark_mode_true(self) -> None:
        fake_start = self._post_start({"X-Benchmark-Mode": "true"})
        fake_start.assert_awaited_once()
        self.assertTrue(fake_start.call_args.kwargs["benchmark_mode"])

    def test_header_absent_forwards_benchmark_mode_false(self) -> None:
        fake_start = self._post_start({})
        fake_start.assert_awaited_once()
        self.assertFalse(fake_start.call_args.kwargs["benchmark_mode"])


if __name__ == "__main__":
    unittest.main()


class MarkIsNotBusinessDataTests(unittest.TestCase):
    """La marca es un metadato: no cuenta como dato resuelto ni llega al LLM."""

    def test_marked_conversation_has_no_resolved_guide_data(self) -> None:
        self.assertFalse(cs._has_resolved_guide_data(_conv(marked=True)))
        conversation = _conv(marked=True)
        conversation.captured_data["numero_radicado"] = "PQR-123"
        self.assertTrue(cs._has_resolved_guide_data(conversation))

    def test_business_captured_data_drops_the_mark_only(self) -> None:
        from infrastructure.genai.llm import strands_workflow_agent as swa

        conversation = _conv(marked=True)
        conversation.captured_data["numero_radicado"] = "PQR-123"
        self.assertEqual(
            swa._business_captured_data(conversation), {"numero_radicado": "PQR-123"}
        )
        self.assertEqual(swa._business_captured_data(_conv()), {})

    def test_local_summary_never_shows_the_mark_to_the_client(self) -> None:
        from infrastructure.genai.llm import strands_workflow_agent as swa

        agent = swa.StrandsWorkflowAgent.__new__(swa.StrandsWorkflowAgent)
        conversation = _conv(marked=True)
        for closure_mode in ("default", "opt_out", "privacy_guidance"):
            summary = agent._build_local_summary(
                conversation, "Gracias por comunicarte.", closure_mode=closure_mode
            )
            self.assertNotIn("benchmark", summary.lower(), closure_mode)


class FinalStepHeaderTests(unittest.TestCase):
    """El paso final viaja en X-Benchmark-Data para los datasets de bypass."""

    def test_final_step_recorded_when_capture_is_active(self) -> None:
        token = benchmark_context.start_capture()
        try:
            conversation = _conv()
            conversation.current_step = "3.4.0.6"
            benchmark_context.mark_routing_done(conversation, None)
            conversation.current_step = "3.4.0.8.pendiente"
            benchmark_context.mark_final_step(conversation)
            data = benchmark_context.finish_capture(token)
        finally:
            token = None
        self.assertEqual(data["current_step"], "3.4.0.8.pendiente")

    def test_final_step_is_noop_without_capture(self) -> None:
        conversation = _conv()
        conversation.current_step = "3.4.0.6"
        benchmark_context.mark_final_step(conversation)  # no lanza, no hay contexto
        self.assertFalse(benchmark_context.is_active())

    def test_in_flow_turn_emits_header_with_zero_routing_time(self) -> None:
        """Un turno sin ruteo (dentro del flujo) tambien sale en la cabecera."""

        token = benchmark_context.start_capture()
        conversation = _conv()
        conversation.workflow = "doble_cobro"
        conversation.current_step = "3.4.0.6"
        conversation.captured_data["routing_outcome"] = "in_flow"
        benchmark_context.mark_final_step(conversation)
        data = benchmark_context.finish_capture(token)
        self.assertIsNotNone(data)
        self.assertEqual(data["routing_time_ms"], 0.0)
        self.assertEqual(data["workflow_result"], "doble_cobro")
        self.assertEqual(data["routing_outcome"], "in_flow")
        self.assertEqual(data["current_step"], "3.4.0.6")


class ResponseSourceHeaderTests(unittest.TestCase):
    """La cabecera del benchmark dice quien redacto el ultimo texto (grounding)."""

    def test_final_step_header_reports_the_model_when_it_wrote_the_text(self) -> None:
        conversation = _conv(marked=True)
        conversation.current_step = "satisfaction_si"
        conversation.captured_data["llm_response_source"] = "model"
        token = benchmark_context.start_capture()
        try:
            benchmark_context.mark_final_step(conversation)
        finally:
            data = benchmark_context.finish_capture(token)
        self.assertEqual(data["response_source"], "model")
        self.assertEqual(data["current_step"], "satisfaction_si")

    def test_approved_yaml_text_has_an_empty_response_source(self) -> None:
        conversation = _conv(marked=True)
        token = benchmark_context.start_capture()
        try:
            benchmark_context.mark_routing_done(conversation, _usage())
            benchmark_context.mark_final_step(conversation)
        finally:
            data = benchmark_context.finish_capture(token)
        self.assertEqual(data["response_source"], "")
