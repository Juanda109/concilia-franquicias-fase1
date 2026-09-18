"""Tests for the global HTTP middleware error auditing (E2E coverage)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import infrastructure.entrypoint.fastapi_app as fa


def _request(path: str = "/chat", method: str = "POST") -> SimpleNamespace:
    # headers: el middleware de benchmark (dev, 24/08) los lee para decidir si
    # captura la peticion; vacio = sin captura, el comportamiento clasico.
    return SimpleNamespace(url=SimpleNamespace(path=path), method=method, headers={})


def _response(status_code: int) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code)


class MiddlewareAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_response_is_audited(self) -> None:
        async def call_next(_request):
            return _response(404)

        with patch.object(fa, "schedule_http_error_report") as mock_http, patch.object(
            fa, "schedule_error_report"
        ) as mock_exc:
            await fa._correlation_access_middleware(_request(), call_next)

        mock_http.assert_called_once()
        self.assertEqual(mock_http.call_args.kwargs["status_code"], 404)
        mock_exc.assert_not_called()

    async def test_success_is_not_audited(self) -> None:
        async def call_next(_request):
            return _response(201)

        with patch.object(fa, "schedule_http_error_report") as mock_http:
            await fa._correlation_access_middleware(_request(), call_next)

        mock_http.assert_not_called()

    async def test_validation_406_is_skipped_by_middleware(self) -> None:
        async def call_next(_request):
            return _response(406)

        with patch.object(fa, "schedule_http_error_report") as mock_http:
            await fa._correlation_access_middleware(_request(), call_next)

        # 406 is audited by the validation handler, not the middleware.
        mock_http.assert_not_called()

    async def test_unhandled_exception_is_audited_and_reraised(self) -> None:
        async def call_next(_request):
            raise RuntimeError("kaboom")

        with patch.object(fa, "schedule_error_report") as mock_exc, patch.object(
            fa, "schedule_http_error_report"
        ) as mock_http:
            with self.assertRaises(RuntimeError):
                await fa._correlation_access_middleware(_request(), call_next)

        mock_exc.assert_called_once()
        self.assertIsInstance(mock_exc.call_args.kwargs["error"], RuntimeError)
        mock_http.assert_not_called()

    async def test_excluded_path_not_audited(self) -> None:
        async def call_next(_request):
            return _response(500)

        with patch.object(fa, "schedule_http_error_report") as mock_http:
            await fa._correlation_access_middleware(_request(path="/health"), call_next)

        mock_http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
