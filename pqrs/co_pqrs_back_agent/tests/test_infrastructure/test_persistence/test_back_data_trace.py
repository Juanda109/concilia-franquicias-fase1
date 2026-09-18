"""Tests for trace emission in the agent -> back_data client."""

import asyncio
import unittest
from unittest.mock import patch

from infrastructure.persistence import back_data_client


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"given_name": "Pablo", "found": True}


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, *args, **kwargs):
        return _FakeResponse()

    async def post(self, *args, **kwargs):
        return _FakeResponse()


class _BoomAsyncClient(_FakeAsyncClient):
    async def get(self, *args, **kwargs):
        raise RuntimeError("connection refused")

    async def post(self, *args, **kwargs):
        raise RuntimeError("connection refused")


class BackDataClientTraceTests(unittest.TestCase):
    def _capture(self, client_cls, coro_factory):
        events: list[dict] = []
        with patch.object(back_data_client.httpx, "AsyncClient", client_cls), patch.object(
            back_data_client, "schedule_trace_event", lambda **kw: events.append(kw)
        ):
            result = asyncio.run(coro_factory())
        return result, events

    def test_customer_name_success_emits_ok_trace(self) -> None:
        result, events = self._capture(
            _FakeAsyncClient,
            lambda: back_data_client.fetch_customer_given_name(
                base_url="http://back-data:8002", customer_id="123"
            ),
        )
        self.assertEqual(result, "Pablo")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["operation"], "customer_name")
        self.assertEqual(events[0]["outcome"], "ok")
        self.assertEqual(events[0]["status_code"], 200)
        self.assertEqual(events[0]["response_summary"]["has_name"], True)

    def test_customer_name_failure_emits_error_trace_and_fails_open(self) -> None:
        result, events = self._capture(
            _BoomAsyncClient,
            lambda: back_data_client.fetch_customer_given_name(
                base_url="http://back-data:8002", customer_id="123"
            ),
        )
        self.assertEqual(result, "")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["operation"], "customer_name")
        self.assertEqual(events[0]["outcome"], "error")
        self.assertEqual(events[0]["error_type"], "RuntimeError")

    def test_trigger_consultar_emits_ok_trace(self) -> None:
        _result, events = self._capture(
            _FakeAsyncClient,
            lambda: back_data_client.trigger_consultar(
                base_url="http://back-data:8002", customer_id="123", workflow="wf"
            ),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["operation"], "consultar")
        self.assertEqual(events[0]["outcome"], "ok")
        self.assertEqual(events[0]["status_code"], 200)

    def test_trigger_failure_emits_error_trace_and_swallows(self) -> None:
        _result, events = self._capture(
            _BoomAsyncClient,
            lambda: back_data_client.trigger_notificacion_centrales(
                base_url="http://back-data:8002", customer_id="123", workflow="wf"
            ),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["operation"], "notificacion_centrales")
        self.assertEqual(events[0]["outcome"], "error")


if __name__ == "__main__":
    unittest.main()
