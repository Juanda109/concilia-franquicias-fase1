"""Tests for the fire-and-forget error reporting to the error-handler service."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Stub strands so importing chat_service never requires the real package.
sys.modules.setdefault("strands", types.ModuleType("strands"))
if not hasattr(sys.modules["strands"], "Agent"):
    class _FakeAgent:  # noqa: D401 - test stub
        def __init__(self, *args, **kwargs) -> None:
            pass

    sys.modules["strands"].Agent = _FakeAgent

from infrastructure.persistence import error_handler_client


class _FakeResponse:
    status_code = 201


class _FakeAsyncClient:
    """Records the last POST and optionally raises, mimicking httpx.AsyncClient."""

    last_call: dict | None = None
    raise_on_post = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url, json=None, headers=None):
        type(self).last_call = {"url": url, "json": json, "headers": headers}
        if type(self).raise_on_post:
            raise RuntimeError("network down")
        return _FakeResponse()


class ReportAgentErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_expected_payload(self) -> None:
        _FakeAsyncClient.last_call = None
        _FakeAsyncClient.raise_on_post = False
        with patch.object(error_handler_client.httpx, "AsyncClient", _FakeAsyncClient):
            await error_handler_client.report_agent_error(
                base_url="http://error-handler:8001",
                conversation_id="03966512_20260619",
                error_message="boom",
                error_type="ValueError",
                tags=["agent"],
            )

        call = _FakeAsyncClient.last_call
        self.assertIsNotNone(call)
        self.assertEqual(call["url"], "http://error-handler:8001/v0/error-reports")
        self.assertEqual(call["json"]["conversation_id"], "03966512_20260619")
        self.assertEqual(call["json"]["error_message"], "boom")
        self.assertEqual(call["json"]["error_type"], "ValueError")
        self.assertEqual(call["json"]["error_source"], "co_pqrs_back_agent")

    async def test_swallows_errors(self) -> None:
        _FakeAsyncClient.raise_on_post = True
        try:
            with patch.object(error_handler_client.httpx, "AsyncClient", _FakeAsyncClient):
                # Must NOT raise even when the HTTP call fails.
                await error_handler_client.report_agent_error(
                    base_url="http://error-handler:8001",
                    conversation_id="c1",
                    error_message="boom",
                )
        finally:
            _FakeAsyncClient.raise_on_post = False


class ScheduleErrorReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_url_is_noop(self) -> None:
        import application.chat.chat_service as cs
        import infrastructure.observability.error_audit as audit

        with patch.object(audit, "load_error_handler_service_url", return_value=None), patch.object(
            audit, "report_agent_error", new=AsyncMock()
        ) as mock_report:
            cs._schedule_error_report(conversation_id="c1", error=ValueError("x"))
            await asyncio.sleep(0)
            mock_report.assert_not_called()

    async def test_schedules_report_when_url_configured(self) -> None:
        import application.chat.chat_service as cs
        import infrastructure.observability.error_audit as audit

        mock_report = AsyncMock()
        with patch.object(
            audit, "load_error_handler_service_url", return_value="http://error-handler:8001"
        ), patch.object(audit, "report_agent_error", new=mock_report):
            cs._schedule_error_report(
                conversation_id="03966512_20260619",
                error=ValueError("kaboom"),
            )
            # Let the scheduled task run.
            for _ in range(5):
                await asyncio.sleep(0)

        mock_report.assert_awaited_once()
        kwargs = mock_report.await_args.kwargs
        self.assertEqual(kwargs["conversation_id"], "03966512_20260619")
        self.assertEqual(kwargs["error_type"], "ValueError")
        self.assertEqual(kwargs["error_message"], "kaboom")


if __name__ == "__main__":
    unittest.main()
