"""Tests for the chat hardening: RUNNING watchdog + background turn hard cap."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# Stub `strands` so importing chat_service does not require the dependency.
fake_strands_module = types.ModuleType("strands")


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        pass


fake_strands_module.Agent = _FakeAgent
sys.modules.setdefault("strands", fake_strands_module)

import application.chat.chat_service as chat_service
from application.chat.chat_service import (
    _is_running_stuck,
    get_conversation_snapshot,
)
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    TokenUsage,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list] = {}
        self.save_conversation_reference_call_count = 0
        self.refresh_call_count = 0

    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def save_conversation_reference(self, conversation: Conversation) -> None:
        self.save_conversation_reference_call_count += 1
        self.conversations[conversation.conversation_id] = conversation

    async def save_message(self, conversation_id: str, message) -> None:
        self.messages.setdefault(conversation_id, []).append(message)

    async def refresh(self) -> None:
        self.refresh_call_count += 1


def _running_conversation(*, seconds_ago: float | None) -> Conversation:
    running_since = (
        None
        if seconds_ago is None
        else datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    )
    return Conversation(
        conversation_id="10482895_20260622",
        status=ConversationStatus.RUNNING,
        current_step="1",
        user_id="10482895",
        messages=[],
        running_since=running_since,
    )


class IsRunningStuckTests(unittest.TestCase):
    def test_stuck_when_running_past_threshold(self) -> None:
        conv = _running_conversation(seconds_ago=chat_service._RUNNING_WATCHDOG_SECONDS + 10)
        self.assertTrue(_is_running_stuck(conv))

    def test_not_stuck_when_recent(self) -> None:
        conv = _running_conversation(seconds_ago=5)
        self.assertFalse(_is_running_stuck(conv))

    def test_not_stuck_when_no_running_since(self) -> None:
        conv = _running_conversation(seconds_ago=None)
        self.assertFalse(_is_running_stuck(conv))

    def test_not_stuck_when_not_running(self) -> None:
        conv = _running_conversation(seconds_ago=999)
        conv.status = ConversationStatus.ACTIVE
        self.assertFalse(_is_running_stuck(conv))

    def test_naive_running_since_is_tolerated(self) -> None:
        conv = _running_conversation(seconds_ago=None)
        conv.running_since = datetime.now() - timedelta(
            seconds=chat_service._RUNNING_WATCHDOG_SECONDS + 10
        )  # naive
        self.assertTrue(_is_running_stuck(conv))


class WatchdogSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_recovers_stuck_running(self) -> None:
        store = InMemoryStore()
        conv = _running_conversation(seconds_ago=chat_service._RUNNING_WATCHDOG_SECONDS + 30)
        store.conversations[conv.conversation_id] = conv

        result = await get_conversation_snapshot(
            conversation_id=conv.conversation_id, store=store
        )

        self.assertEqual(result.status, ConversationStatus.ACTIVE)
        self.assertIsNone(result.running_since)
        self.assertGreaterEqual(store.save_conversation_reference_call_count, 1)

    async def test_snapshot_leaves_recent_running(self) -> None:
        store = InMemoryStore()
        conv = _running_conversation(seconds_ago=3)
        store.conversations[conv.conversation_id] = conv

        result = await get_conversation_snapshot(
            conversation_id=conv.conversation_id, store=store
        )

        self.assertEqual(result.status, ConversationStatus.RUNNING)
        self.assertIsNotNone(result.running_since)
        self.assertEqual(store.save_conversation_reference_call_count, 0)


class TurnHardCapTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_exceeding_cap_finalizes_as_error(self) -> None:
        store = InMemoryStore()
        conv = _running_conversation(seconds_ago=1)
        store.conversations[conv.conversation_id] = conv

        async def _slow_turn(**kwargs):
            await asyncio.sleep(1.0)
            return kwargs["conversation"]

        with patch.object(chat_service, "_TURN_HARD_CAP_SECONDS", 0.05), patch.object(
            chat_service, "_process_message_turn", new=_slow_turn
        ), patch.object(
            chat_service, "_schedule_error_report"
        ) as mock_report, patch.object(chat_service, "_emit_event"):
            result = await chat_service._run_chat_turn_in_background(
                content="hola",
                conversation_id=conv.conversation_id,
                store=store,
                workflow_engine=object(),
                strands_agent=object(),
            )

            # The TimeoutError flowed into the existing error handling.
            self.assertEqual(result.status, ConversationStatus.ERROR)
            mock_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class TurnClearsRunningTests(unittest.IsolatedAsyncioTestCase):
    """Un turno que termina no puede dejar la conversacion en RUNNING.

    Hasta ahora solo salian de RUNNING los caminos del motor que avanzan de
    paso. Una opcion no reconocida devolvia su mensaje sin tocar el estado, asi
    que /polling respondia 201 durante los 150 s del watchdog y el cliente
    esperaba por una respuesta que estaba lista en decimas de segundo.
    """

    async def _turno(
        self,
        salida_estado: ConversationStatus | None = None,
        *,
        limite_agotado: bool = False,
    ):
        store = InMemoryStore()
        conv = _running_conversation(seconds_ago=1)
        if limite_agotado:
            conv.captured_data[chat_service._SESSION_LIMIT_CLOSED_KEY] = "true"
        store.conversations[conv.conversation_id] = conv

        async def _resolver(**kwargs):
            if salida_estado is not None:
                kwargs["conversation"].status = salida_estado
            return (
                "No pude identificar una opcion valida para el paso 1.",
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )

        with patch.object(chat_service, "_resolve_assistant_content", new=_resolver):
            return await chat_service._process_message_turn(
                conversation=conv,
                content="zzz_no_existe",
                store=store,
                workflow_engine=object(),
                strands_agent=object(),
            )

    async def test_sin_match_sale_de_running(self) -> None:
        resultado = await self._turno()
        self.assertEqual(resultado.status, ConversationStatus.ACTIVE)
        self.assertIsNone(resultado.running_since)

    async def test_no_pisa_un_cierre_por_limite(self) -> None:
        """Una sesion cerrada por limite diario tiene que seguir cerrada."""

        resultado = await self._turno(
            ConversationStatus.CLOSED, limite_agotado=True
        )
        self.assertEqual(resultado.status, ConversationStatus.CLOSED)

    async def test_una_consulta_terminada_reabre_la_sesion(self) -> None:
        """Architecture A: al acabar una consulta se vuelve al inicio, no se cierra.

        Se fija aqui para que quede claro que ese ACTIVE es deliberado y no el
        de esta correccion.
        """

        resultado = await self._turno(ConversationStatus.CLOSED)
        self.assertEqual(resultado.status, ConversationStatus.ACTIVE)
        self.assertEqual(resultado.current_step, "start")

    async def test_no_pisa_un_error(self) -> None:
        resultado = await self._turno(ConversationStatus.ERROR)
        self.assertEqual(resultado.status, ConversationStatus.ERROR)
