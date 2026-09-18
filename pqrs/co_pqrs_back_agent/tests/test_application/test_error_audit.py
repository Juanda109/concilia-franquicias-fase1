"""Tests for the centralized error auditing module."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import infrastructure.observability.error_audit as audit


class ErrorAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_exception_report_noop_without_url(self) -> None:
        with patch.object(audit, "load_error_handler_service_url", return_value=None), patch.object(
            audit, "report_agent_error", new=AsyncMock()
        ) as mock_report:
            audit.schedule_error_report(conversation_id="c1", error=ValueError("x"))
            await asyncio.sleep(0)
            mock_report.assert_not_called()

    async def test_exception_report_includes_traceback_and_type(self) -> None:
        mock_report = AsyncMock()
        with patch.object(
            audit, "load_error_handler_service_url", return_value="http://eh:8001"
        ), patch.object(audit, "report_agent_error", new=mock_report):
            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                audit.schedule_error_report(
                    conversation_id="03966512_20260619", error=exc, source="POST /chat"
                )
            for _ in range(5):
                await asyncio.sleep(0)

        mock_report.assert_awaited_once()
        kwargs = mock_report.await_args.kwargs
        self.assertEqual(kwargs["error_type"], "RuntimeError")
        self.assertEqual(kwargs["agent_context"]["source"], "POST /chat")
        self.assertIn("traceback", kwargs["extra_context"])
        self.assertIn("RuntimeError", kwargs["extra_context"]["traceback"])

    async def test_http_error_report_fields(self) -> None:
        mock_report = AsyncMock()
        with patch.object(
            audit, "load_error_handler_service_url", return_value="http://eh:8001"
        ), patch.object(audit, "report_agent_error", new=mock_report):
            audit.schedule_http_error_report(
                conversation_id=None,
                status_code=404,
                method="POST",
                path="/chat",
                detail="Conversation not found",
            )
            for _ in range(5):
                await asyncio.sleep(0)

        mock_report.assert_awaited_once()
        kwargs = mock_report.await_args.kwargs
        self.assertEqual(kwargs["conversation_id"], "unknown")
        self.assertEqual(kwargs["error_type"], "HTTP404")
        self.assertEqual(kwargs["agent_context"]["status_code"], 404)
        self.assertEqual(kwargs["agent_context"]["error_class"], "client_error")
        self.assertIn("404", kwargs["tags"])

    async def test_http_error_report_noop_without_url(self) -> None:
        with patch.object(audit, "load_error_handler_service_url", return_value=None), patch.object(
            audit, "report_agent_error", new=AsyncMock()
        ) as mock_report:
            audit.schedule_http_error_report(
                conversation_id="c1", status_code=406, method="POST", path="/chat"
            )
            await asyncio.sleep(0)
            mock_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
