"""Tests for back_data error auditing (middleware + scheduler)."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import infrastructure.entrypoint.fastapi_app as fa
import infrastructure.observability.error_audit as audit


def _request(path: str = "/consultar", method: str = "POST", correlation: str | None = None):
    headers = {"X-Correlation-Id": correlation} if correlation else {}
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method=method,
        headers=headers,
        query_params={},
    )


def _response(status_code: int) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code)


class BackDataMiddlewareAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_response_audited(self) -> None:
        async def call_next(_request):
            return _response(404)

        with patch.object(fa, "schedule_http_error_report") as mock_http, patch.object(
            fa, "schedule_error_report"
        ) as mock_exc:
            await fa._correlation_access_middleware(_request(correlation="abc_20260101"), call_next)

        mock_http.assert_called_once()
        self.assertEqual(mock_http.call_args.kwargs["status_code"], 404)
        self.assertEqual(mock_http.call_args.kwargs["conversation_id"], "abc_20260101")
        mock_exc.assert_not_called()

    async def test_success_not_audited(self) -> None:
        async def call_next(_request):
            return _response(200)

        with patch.object(fa, "schedule_http_error_report") as mock_http:
            await fa._correlation_access_middleware(_request(), call_next)
        mock_http.assert_not_called()

    async def test_406_skipped(self) -> None:
        async def call_next(_request):
            return _response(406)

        with patch.object(fa, "schedule_http_error_report") as mock_http:
            await fa._correlation_access_middleware(_request(), call_next)
        mock_http.assert_not_called()

    async def test_exception_audited_and_reraised(self) -> None:
        async def call_next(_request):
            raise RuntimeError("kaboom")

        with patch.object(fa, "schedule_error_report") as mock_exc:
            with self.assertRaises(RuntimeError):
                await fa._correlation_access_middleware(_request(), call_next)
        mock_exc.assert_called_once()
        self.assertIsInstance(mock_exc.call_args.kwargs["error"], RuntimeError)


class BackDataAuditSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_noop_without_url(self) -> None:
        with patch.object(audit, "load_error_handler_service_url", return_value=None), patch.object(
            audit, "_post_error_report"
        ) as mock_post:
            audit.schedule_http_error_report(status_code=500, method="POST", path="/consultar")
            await asyncio.sleep(0)
            mock_post.assert_not_called()

    async def test_schedules_with_component(self) -> None:
        captured: list[dict] = []

        async def fake_post(base_url, payload):
            captured.append(payload)

        with patch.object(
            audit, "load_error_handler_service_url", return_value="http://eh:8002"
        ), patch.object(audit, "_post_error_report", new=fake_post):
            audit.schedule_error_report(
                error=ValueError("db down"), source="POST /consultar", conversation_id="abc_1"
            )
            for _ in range(5):
                await asyncio.sleep(0)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["component"], "co_pqrs_back_data")
        self.assertEqual(captured[0]["error_type"], "ValueError")
        self.assertEqual(captured[0]["conversation_id"], "abc_1")
        self.assertIn("traceback", captured[0]["extra_context"])


if __name__ == "__main__":
    unittest.main()
