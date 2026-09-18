"""Unit tests for the fire-and-forget trace emitter (schedule_trace_event)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from infrastructure.observability import trace_audit


class _SyncThread:
    """Thread stub that runs the target synchronously on start()."""

    def __init__(self, target, args=(), **_kwargs) -> None:
        self._target = target
        self._args = args

    def start(self) -> None:
        self._target(*self._args)


class ScheduleTraceEventTests(unittest.TestCase):
    def test_noop_when_error_handler_url_unset(self) -> None:
        with patch.object(
            trace_audit, "load_error_handler_service_url", return_value=None
        ), patch.object(trace_audit, "_post_trace_event") as post:
            trace_audit.schedule_trace_event(event_type="aso", operation="tsec")
        post.assert_not_called()

    def test_posts_expected_payload_when_url_set(self) -> None:
        captured: dict = {}

        def fake_post(base_url: str, payload: dict) -> None:
            captured["base_url"] = base_url
            captured["payload"] = payload

        with patch.object(
            trace_audit,
            "load_error_handler_service_url",
            return_value="http://error-handler:8002",
        ), patch.object(trace_audit, "_post_trace_event", fake_post), patch.object(
            trace_audit.threading, "Thread", _SyncThread
        ):
            trace_audit.schedule_trace_event(
                event_type="aso",
                operation="commercial_info_overview",
                outcome="ok",
                status_code=200,
                elapsed_ms=12.3,
                target="https://aso/overview",
                conversation_id="c1",
                customer_id="cust1",
                response_summary={"bytes": 100, "obligations": 2},
                tags=["aso", "overview"],
            )

        self.assertEqual(captured["base_url"], "http://error-handler:8002")
        payload = captured["payload"]
        self.assertEqual(payload["event_type"], "aso")
        self.assertEqual(payload["operation"], "commercial_info_overview")
        self.assertEqual(payload["outcome"], "ok")
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["conversation_id"], "c1")
        self.assertEqual(payload["trace_id"], "c1")
        self.assertEqual(payload["customer_id"], "cust1")
        self.assertEqual(payload["component"], "co_pqrs_back_data")
        # No secrets must ever be present in a trace payload.
        self.assertNotIn("tsec", str(payload).lower())
        self.assertNotIn("password", str(payload).lower())

    def test_error_outcome_carries_error_fields(self) -> None:
        captured: dict = {}

        with patch.object(
            trace_audit,
            "load_error_handler_service_url",
            return_value="http://error-handler:8002",
        ), patch.object(
            trace_audit,
            "_post_trace_event",
            lambda base_url, payload: captured.update(payload=payload),
        ), patch.object(trace_audit.threading, "Thread", _SyncThread):
            trace_audit.schedule_trace_event(
                event_type="postgres",
                operation="read_customer_identity",
                outcome="error",
                error_type="DataSourceError",
                error_message="connection refused",
            )

        payload = captured["payload"]
        self.assertEqual(payload["outcome"], "error")
        self.assertEqual(payload["error_type"], "DataSourceError")
        self.assertEqual(payload["error_message"], "connection refused")

    def test_never_raises_even_if_config_fails(self) -> None:
        with patch.object(
            trace_audit,
            "load_error_handler_service_url",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise: observability can never break the flow.
            trace_audit.schedule_trace_event(event_type="aso", operation="tsec")


if __name__ == "__main__":
    unittest.main()
