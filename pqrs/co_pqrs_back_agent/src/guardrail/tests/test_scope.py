"""Tests Fase 1: umbral de scope del routing (inyectando decisiones)."""

import unittest
from types import SimpleNamespace

from guardrail import ALLOWED_CONFIDENCE, accepts_routing, routing_scope_prompt_suffix


def _decision(is_match, workflow, confidence):
    return SimpleNamespace(is_match=is_match, workflow=workflow, confidence=confidence)


class AcceptsRoutingTests(unittest.TestCase):
    def test_high_confidence_match_is_accepted(self):
        self.assertTrue(accepts_routing(_decision(True, "certificado_de_cuenta", "high")))

    def test_medium_confidence_match_is_accepted(self):
        self.assertTrue(accepts_routing(_decision(True, "certificado_de_cuenta", "medium")))

    def test_low_confidence_match_is_rejected(self):
        self.assertFalse(accepts_routing(_decision(True, "certificado_de_cuenta", "low")))

    def test_none_confidence_match_is_rejected(self):
        self.assertFalse(accepts_routing(_decision(True, "certificado_de_cuenta", "none")))

    def test_not_match_is_rejected(self):
        self.assertFalse(accepts_routing(_decision(False, "", "high")))

    def test_empty_workflow_is_rejected(self):
        self.assertFalse(accepts_routing(_decision(True, "", "high")))


class ScopePromptTests(unittest.TestCase):
    def test_suffix_enforces_out_of_scope_behavior(self):
        suffix = routing_scope_prompt_suffix()
        self.assertIn("is_match=false", suffix)
        self.assertTrue(suffix.strip())

    def test_suffix_forbids_forcing_faq_for_off_topic(self):
        suffix = routing_scope_prompt_suffix().casefold()
        self.assertIn("faq", suffix)
        self.assertIn("no fuerces", suffix)

    def test_threshold_default(self):
        self.assertEqual(ALLOWED_CONFIDENCE, frozenset({"high", "medium"}))


if __name__ == "__main__":
    unittest.main()
