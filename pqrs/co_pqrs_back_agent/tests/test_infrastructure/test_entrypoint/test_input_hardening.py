"""Tests for input hardening: 1000-char cap, friendly message, log excerpt."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from infrastructure.entrypoint.api.router.v0.model.chat_models import (
    ChatRequest,
    StartRequest,
)


class ContentMaxLengthTests(unittest.TestCase):
    def test_chat_content_within_limit_ok(self) -> None:
        req = ChatRequest(conversation_id="10482895_20260622", content="A" * 1000)
        self.assertEqual(len(req.content), 1000)

    def test_chat_content_over_limit_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            ChatRequest(conversation_id="10482895_20260622", content="A" * 1001)
        # Pydantic flags it as a too-long string on the `content` field.
        errors = ctx.exception.errors()
        self.assertTrue(
            any(
                err.get("type") == "string_too_long" and err.get("loc")[-1] == "content"
                for err in errors
            )
        )

    def test_start_content_over_limit_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            StartRequest(user_id="10482895", content="A" * 1001)


class TooLongDetectionTests(unittest.TestCase):
    def test_handler_detects_content_too_long(self) -> None:
        from infrastructure.entrypoint.fastapi_app import _has_content_too_long_error

        try:
            ChatRequest(conversation_id="10482895_20260622", content="A" * 1001)
        except ValidationError as exc:
            self.assertTrue(_has_content_too_long_error(exc))
        else:  # pragma: no cover
            self.fail("expected ValidationError")

    def test_handler_ignores_other_validation_errors(self) -> None:
        from infrastructure.entrypoint.fastapi_app import _has_content_too_long_error

        try:
            ChatRequest(conversation_id="bad-id", content="hola")
        except ValidationError as exc:
            self.assertFalse(_has_content_too_long_error(exc))
        else:  # pragma: no cover
            self.fail("expected ValidationError")


class SafeExcerptTests(unittest.TestCase):
    def test_truncates_to_limit_and_strips_newlines(self) -> None:
        from infrastructure.entrypoint.api.router.v0.chat_router import _safe_excerpt

        excerpt = _safe_excerpt("line1\nline2\r\n" + "X" * 50, 30)
        self.assertEqual(len(excerpt), 30)
        self.assertNotIn("\n", excerpt)
        self.assertNotIn("\r", excerpt)

    def test_handles_none_and_empty(self) -> None:
        from infrastructure.entrypoint.api.router.v0.chat_router import _safe_excerpt

        self.assertEqual(_safe_excerpt(None), "")
        self.assertEqual(_safe_excerpt(""), "")


if __name__ == "__main__":
    unittest.main()
