"""Tests for the new analytics fields/events on the metrics pipeline:
llm_used, guardrail_blocked, routing_outcome, subflow_key (turn),
resolution (closed) and the conversation.cap_reached event."""

import sys
import types
import unittest

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


def _conv() -> Conversation:
    return Conversation(
        conversation_id="10482895_20260701",
        status=ConversationStatus.ACTIVE,
        current_step="start",
        user_id="10482895",
        messages=[],
    )


def _usage(total: int) -> TokenUsage:
    return TokenUsage(input_tokens=total, output_tokens=0, total_tokens=total)


class TurnEventFieldsTests(unittest.TestCase):
    def test_llm_used_true_when_tokens(self) -> None:
        ev = cs._build_turn_event(_conv(), turn_usage=_usage(15), duration_ms=100)
        self.assertTrue(ev["llm_used"])

    def test_llm_used_false_when_no_tokens(self) -> None:
        ev = cs._build_turn_event(_conv(), turn_usage=_usage(0), duration_ms=1)
        self.assertFalse(ev["llm_used"])

    def test_guardrail_blocked_flag(self) -> None:
        conv = _conv()
        conv.captured_data["_last_guardrail_blocked"] = "true"
        ev = cs._build_turn_event(conv, turn_usage=_usage(0), duration_ms=1)
        self.assertTrue(ev["guardrail_blocked"])

    def test_guardrail_blocked_default_false(self) -> None:
        ev = cs._build_turn_event(_conv(), turn_usage=_usage(0), duration_ms=1)
        self.assertFalse(ev["guardrail_blocked"])

    def test_routing_outcome_passthrough(self) -> None:
        conv = _conv()
        conv.captured_data["routing_outcome"] = "no_match"
        ev = cs._build_turn_event(conv, turn_usage=_usage(0), duration_ms=1)
        self.assertEqual(ev["routing_outcome"], "no_match")

    def test_subflow_key_only_for_centrales(self) -> None:
        conv = _conv()
        conv.workflow = "centrales_de_riesgo"
        conv.flow_answers[cs._CENTRALES_SUBFLOW_ANSWER] = "consulta_sin_permiso"
        ev = cs._build_turn_event(conv, turn_usage=_usage(0), duration_ms=1)
        self.assertEqual(ev["subflow_key"], "consulta_sin_permiso")

    def test_subflow_key_none_for_other_workflows(self) -> None:
        conv = _conv()
        conv.workflow = "impuesto_4x1000"
        conv.flow_answers[cs._CENTRALES_SUBFLOW_ANSWER] = "consulta_sin_permiso"
        ev = cs._build_turn_event(conv, turn_usage=_usage(0), duration_ms=1)
        self.assertIsNone(ev["subflow_key"])


class ResolutionTests(unittest.TestCase):
    def test_limit_closed(self) -> None:
        conv = _conv()
        conv.captured_data[cs._SESSION_LIMIT_CLOSED_KEY] = "true"
        self.assertEqual(cs._classify_resolution(conv), "limit_closed")

    def test_resolved(self) -> None:
        conv = _conv()
        conv.satisfaction_result = True
        self.assertEqual(cs._classify_resolution(conv), "resolved")

    def test_not_resolved(self) -> None:
        conv = _conv()
        conv.satisfaction_result = False
        self.assertEqual(cs._classify_resolution(conv), "not_resolved")

    def test_abandoned(self) -> None:
        conv = _conv()
        conv.satisfaction_status = "ABANDONED"
        self.assertEqual(cs._classify_resolution(conv), "abandoned")

    def test_closed_default(self) -> None:
        self.assertEqual(cs._classify_resolution(_conv()), "closed")

    def test_closed_event_includes_resolution(self) -> None:
        ev = cs._build_closed_event(_conv())
        self.assertIn("resolution", ev)


class CapReachedEventTests(unittest.TestCase):
    def test_case_scope_shape(self) -> None:
        ev = cs._build_cap_reached_event(
            _conv(),
            limit_key="impuesto_4x1000",
            limit_label="Impuesto 4x1000",
            limit_scope="case",
        )
        self.assertEqual(ev["event"], "conversation.cap_reached")
        self.assertEqual(ev["limit_key"], "impuesto_4x1000")
        self.assertEqual(ev["limit_scope"], "case")

    def test_centrales_subflow_scope_shape(self) -> None:
        conv = _conv()
        conv.workflow = "centrales_de_riesgo"
        ev = cs._build_cap_reached_event(
            conv,
            limit_key="centrales_de_riesgo:consulta_sin_permiso",
            limit_label="la consulta sin autorización",
            limit_scope="centrales_subflow",
        )
        self.assertEqual(ev["limit_scope"], "centrales_subflow")
        self.assertEqual(ev["limit_key"], "centrales_de_riesgo:consulta_sin_permiso")
        self.assertEqual(ev["workflow"], "centrales_de_riesgo")


if __name__ == "__main__":
    unittest.main()
