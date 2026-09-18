"""Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado)."""

import os
import unittest

from guardrail.judge import (
    OUT_OF_SCOPE_MESSAGES,
    judge_enabled,
    judge_user_message,
    verdict_to_block,
)


class VerdictToBlockTests(unittest.TestCase):
    def test_in_scope_allows(self):
        self.assertIsNone(verdict_to_block(True, "banca"))

    def test_out_of_scope_blocks(self):
        self.assertIsNotNone(verdict_to_block(False, "restaurante"))

    def test_out_of_scope_message_comes_from_pool(self):
        self.assertIn(verdict_to_block(False, "restaurante"), OUT_OF_SCOPE_MESSAGES)


class JudgeEnabledTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("GUARDRAIL_JUDGE_ENABLED")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("GUARDRAIL_JUDGE_ENABLED", None)
        else:
            os.environ["GUARDRAIL_JUDGE_ENABLED"] = self._old

    def test_enabled_true(self):
        os.environ["GUARDRAIL_JUDGE_ENABLED"] = "true"
        self.assertTrue(judge_enabled())

    def test_disabled_false(self):
        os.environ["GUARDRAIL_JUDGE_ENABLED"] = "false"
        self.assertFalse(judge_enabled())


class JudgeDisabledNoOpTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_returns_none(self):
        os.environ["GUARDRAIL_JUDGE_ENABLED"] = "false"
        try:
            self.assertIsNone(await judge_user_message("quiero una hamburguesa"))
        finally:
            os.environ.pop("GUARDRAIL_JUDGE_ENABLED", None)


if __name__ == "__main__":
    unittest.main()
