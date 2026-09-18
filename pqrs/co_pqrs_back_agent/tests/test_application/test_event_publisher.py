"""Tests for the RabbitMQ event publisher and the fire-and-forget emitter."""

from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

# Stub strands so importing chat_service never requires the real package.
sys.modules.setdefault("strands", types.ModuleType("strands"))
if not hasattr(sys.modules["strands"], "Agent"):
    class _FakeAgent:  # noqa: D401 - test stub
        def __init__(self, *args, **kwargs) -> None:
            pass

    sys.modules["strands"].Agent = _FakeAgent

from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from infrastructure.core.config import RabbitMQSettings
from infrastructure.messaging.event_publisher import EventPublisher


def _settings(**overrides) -> RabbitMQSettings:
    base = dict(enabled=True, host="rabbitmq", user="admin", password="secret")
    base.update(overrides)
    return RabbitMQSettings(**base)


class _FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []
        self.raise_on_publish = False

    async def publish(self, message, routing_key=None):
        if self.raise_on_publish:
            raise RuntimeError("broker down")
        self.published.append((routing_key, message.body))


class EventPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_sends_json_with_routing_key(self) -> None:
        publisher = EventPublisher(_settings())
        fake_exchange = _FakeExchange()
        # Inject a ready exchange so aio_pika is never imported/used.
        publisher._exchange = fake_exchange

        await publisher.publish("conversation.turn", {"event": "conversation.turn", "n": 1})

        self.assertEqual(len(fake_exchange.published), 1)
        routing_key, body = fake_exchange.published[0]
        self.assertEqual(routing_key, "conversation.turn")
        self.assertEqual(json.loads(body)["n"], 1)

    async def test_publish_swallows_errors_and_resets(self) -> None:
        publisher = EventPublisher(_settings())
        fake_exchange = _FakeExchange()
        fake_exchange.raise_on_publish = True
        publisher._exchange = fake_exchange

        # Must not raise.
        await publisher.publish("conversation.error", {"event": "conversation.error"})
        # Connection state reset so the next publish reconnects.
        self.assertIsNone(publisher._exchange)


class EmitEventTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        import application.chat.chat_service as cs

        self.cs = cs
        # Reset the cached publisher between tests.
        cs._EVENT_PUBLISHER = None
        cs._EVENT_PUBLISHER_RESOLVED = False

    async def test_emit_is_noop_when_disabled(self) -> None:
        with patch.object(
            self.cs, "load_rabbitmq_settings", return_value=_settings(enabled=False)
        ):
            self.cs._emit_event("conversation.turn", {"event": "x"})
            await asyncio.sleep(0)
            self.assertIsNone(self.cs._get_event_publisher())

    async def test_emit_schedules_publish_when_enabled(self) -> None:
        published: list[tuple[str, dict]] = []

        class _CapturingPublisher:
            def __init__(self, settings=None) -> None:
                self.settings = settings

            async def publish(self, routing_key, payload):
                published.append((routing_key, payload))

        with patch.object(
            self.cs, "load_rabbitmq_settings", return_value=_settings(enabled=True)
        ), patch.object(self.cs, "EventPublisher", _CapturingPublisher):
            self.cs._emit_event("conversation.turn", {"event": "conversation.turn"})
            for _ in range(5):
                await asyncio.sleep(0)

        self.assertEqual(published, [("conversation.turn", {"event": "conversation.turn"})])


class EventBuilderTests(unittest.TestCase):
    def _conversation(self) -> Conversation:
        now = datetime(2026, 6, 19, 15, 0, 0, tzinfo=timezone.utc)
        msg = Message(
            id="m1",
            role=MessageRole.ASSISTANT,
            content="hola",
            tokens=TokenUsage(input_tokens=5, output_tokens=3, total_tokens=8),
            timing=MessageTiming(received_at=now, responded_at=now, total_duration_ms=10),
        )
        conv = Conversation(
            conversation_id="03966512_20260619",
            status=ConversationStatus.CLOSED,
            current_step="1.2",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            user_id="03966512",
            satisfaction_status="ENTERED",
            satisfaction_result=True,
            messages=[msg],
        )
        conv.refresh_message_dates()
        return conv

    def test_build_turn_event(self) -> None:
        import application.chat.chat_service as cs

        conv = self._conversation()
        event = cs._build_turn_event(
            conv, turn_usage=TokenUsage(input_tokens=5, output_tokens=3, total_tokens=8), duration_ms=42
        )
        self.assertEqual(event["event"], "conversation.turn")
        self.assertEqual(event["workflow"], "centrales_de_riesgo")
        self.assertEqual(event["tokens"]["total_tokens"], 8)
        self.assertEqual(event["duration_ms"], 42)

    def test_build_closed_event(self) -> None:
        import application.chat.chat_service as cs

        event = cs._build_closed_event(self._conversation())
        self.assertEqual(event["event"], "conversation.closed")
        self.assertEqual(event["satisfaction_status"], "ENTERED")
        self.assertIs(event["satisfaction_result"], True)
        self.assertIsNotNone(event["duration_total_ms"])


if __name__ == "__main__":
    unittest.main()
