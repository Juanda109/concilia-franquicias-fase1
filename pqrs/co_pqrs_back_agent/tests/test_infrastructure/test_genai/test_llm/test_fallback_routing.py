"""Tests del ruteo local de respaldo (cuando el LLM remoto no esta disponible)."""

import sys
import types
import unittest

# Stub mínimo de `strands` para poder importar el agente sin el SDK real.
_fake_strands = types.ModuleType("strands")


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        pass


_fake_strands.Agent = _FakeAgent
sys.modules.setdefault("strands", _fake_strands)

from domain.workflow.models import WorkflowRoutingEntry
from infrastructure.genai.llm.strands_workflow_agent import StrandsWorkflowAgent


def _routing_catalog() -> list[WorkflowRoutingEntry]:
    return [
        WorkflowRoutingEntry(
            general_workflow_key="hazlo_tu_mismo",
            general_workflow_label="Hazlo tu mismo",
            workflow="paz_y_salvo",
            workflow_label="Paz y Salvo",
            description="Obtener el paz y salvo de un producto cancelado.",
            examples=["necesito mi paz y salvo"],
            steps_preview=[],
        ),
        WorkflowRoutingEntry(
            general_workflow_key="guia_rapida",
            general_workflow_label="Guia rapida",
            workflow="cuota_de_manejo",
            workflow_label="Cuota de manejo",
            description="Explica el cobro de cuota de manejo y como evitarlo.",
            examples=["por que me cobran cuota de manejo"],
            steps_preview=[],
        ),
    ]


class FallbackRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = StrandsWorkflowAgent(
            api_key="x",
            endpoint="https://example.test/",
            model_id="dummy-model",
        )

    def test_pure_greeting_returns_warm_welcome_not_cold_error(self) -> None:
        decision = self.agent._fallback_workflow_routing(
            user_message="Hola",
            routing_catalog=_routing_catalog(),
        )

        self.assertFalse(decision.is_match)
        self.assertEqual(decision.confidence, "none")
        self.assertNotIn(
            "No pude identificar todavia el flujo correcto",
            decision.clarification_message,
        )
        self.assertIn("Hola", decision.clarification_message)
        self.assertIn("Puedo ayudarte con temas de:", decision.clarification_message)
        self.assertIn("Hazlo tu mismo", decision.clarification_message)
        self.assertIn("Guia rapida", decision.clarification_message)

    def test_greeting_phrase_returns_warm_welcome(self) -> None:
        decision = self.agent._fallback_workflow_routing(
            user_message="Hola buenas, como estas?",
            routing_catalog=_routing_catalog(),
        )

        self.assertFalse(decision.is_match)
        self.assertIn("Puedo ayudarte con temas de:", decision.clarification_message)

    def test_off_topic_returns_warm_scope_message_not_match(self) -> None:
        decision = self.agent._fallback_workflow_routing(
            user_message="quiero una receta para hamburguesas caseras grandes",
            routing_catalog=_routing_catalog(),
        )

        self.assertFalse(decision.is_match)
        self.assertEqual(decision.confidence, "none")
        self.assertIn(
            "solo puedo ayudarte con temas de pqrs",
            decision.clarification_message.casefold(),
        )

    def test_clear_request_still_matches_workflow(self) -> None:
        decision = self.agent._fallback_workflow_routing(
            user_message="necesito mi paz y salvo del credito",
            routing_catalog=_routing_catalog(),
        )

        self.assertTrue(decision.is_match)
        self.assertEqual(decision.workflow, "paz_y_salvo")


if __name__ == "__main__":
    unittest.main()
