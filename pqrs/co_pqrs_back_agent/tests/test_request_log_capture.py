"""Tests for the per-request full log capturer (buffer + masking + caps)."""

from __future__ import annotations

import logging
import os
import unittest

from infrastructure.observability import request_log_capture as cap


def _make_handler() -> cap.RequestLogCaptureHandler:
    handler = cap.RequestLogCaptureHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    return handler


class RequestLogCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["REQUEST_LOG_CAPTURE_ENABLED"] = "true"

    def tearDown(self) -> None:
        os.environ.pop("REQUEST_LOG_CAPTURE_ENABLED", None)
        os.environ.pop("REQUEST_LOG_MAX_LINES", None)

    def _emit(self, handler: logging.Handler, level: int, msg: str) -> None:
        record = logging.LogRecord("t", level, __file__, 1, msg, None, None)
        handler.emit(record)

    def test_capture_masks_pii_and_counts_lines(self) -> None:
        handler = _make_handler()
        token = cap.start_request_capture("req-1")
        self.assertIsNotNone(token)

        self._emit(handler, logging.INFO, "correo juan.perez@test.com doc 1234567890")
        self._emit(handler, logging.WARNING, "segunda linea")

        buffer = cap.finish_request_capture(token)
        self.assertIsNotNone(buffer)
        assert buffer is not None
        self.assertEqual(len(buffer.lines), 2)
        joined = "\n".join(buffer.lines)
        self.assertIn("***@***", joined)
        self.assertIn("****7890", joined)
        self.assertNotIn("juan.perez@test.com", joined)
        self.assertNotIn("1234567890", joined)

    def test_line_cap_marks_truncated(self) -> None:
        os.environ["REQUEST_LOG_MAX_LINES"] = "2"
        handler = _make_handler()
        token = cap.start_request_capture("req-2")

        for i in range(5):
            self._emit(handler, logging.INFO, f"line {i}")

        buffer = cap.finish_request_capture(token)
        assert buffer is not None
        self.assertEqual(len(buffer.lines), 2)
        self.assertTrue(buffer.truncated)
        self.assertEqual(buffer.dropped, 3)

    def test_disabled_is_noop(self) -> None:
        os.environ["REQUEST_LOG_CAPTURE_ENABLED"] = "false"
        handler = _make_handler()
        token = cap.start_request_capture("req-3")
        self.assertIsNone(token)
        # No active buffer -> emit is a silent no-op.
        self._emit(handler, logging.INFO, "ignored")
        self.assertIsNone(cap.finish_request_capture(token))


if __name__ == "__main__":
    unittest.main()
