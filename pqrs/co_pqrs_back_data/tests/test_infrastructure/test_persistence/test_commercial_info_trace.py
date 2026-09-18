"""Tests for ASO client enrichment: structured logs + trace emission.

Exercises the real HTTP flow of ``_get_commercial_info_from_api`` with a fake
httpx client so we can assert that both success (200) and error paths emit a
trace event, that timing/status are captured, and that secrets (tsec/password)
never leak into the emitted payload.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from domain.customer.models import CustomerIdentity
from infrastructure.core.config import CommercialInfoSettings
from infrastructure.entrypoint.api.errors.exceptions import DataSourceError
from infrastructure.persistence import commercial_info_client as cic_module
from infrastructure.persistence.commercial_info_client import CommercialInfoClient


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict | None = None,
        json_data=None,
        text: str = "",
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "http error",
                request=httpx.Request("GET", "https://aso/x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        if self._json is None:
            raise json.JSONDecodeError("no json", "", 0)
        return self._json


class _FakeClient:
    def __init__(self, tsec_response: _FakeResponse, get_response: _FakeResponse) -> None:
        self._tsec_response = tsec_response
        self._get_response = get_response
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def post(self, url, **_kwargs) -> _FakeResponse:
        self.calls.append(("POST", url))
        return self._tsec_response

    def get(self, url, **_kwargs) -> _FakeResponse:
        self.calls.append(("GET", url))
        return self._get_response


class _PdfFakeClient:
    def __init__(
        self,
        tsec_response: _FakeResponse,
        get_responses: list[_FakeResponse],
    ) -> None:
        self._tsec_response = tsec_response
        self._get_responses = iter(get_responses)
        self.get_headers: list[dict] = []

    def __enter__(self) -> "_PdfFakeClient":
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def post(self, _url, **_kwargs) -> _FakeResponse:
        return self._tsec_response

    def get(self, _url, **kwargs) -> _FakeResponse:
        self.get_headers.append(kwargs["headers"])
        return next(self._get_responses)


def _api_settings() -> CommercialInfoSettings:
    return CommercialInfoSettings(
        source="api",
        ticket_url="https://aso/ticket",
        overview_url="https://aso/overview",
        api_user_id="user",
        api_consumer_id="consumer",
        api_password="SECRET_PWD",
        api_customer_id_length=8,
        api_verify_ssl=False,
    )


def _identity() -> CustomerIdentity:
    return CustomerIdentity(
        customer_id="1069759414",
        personal_id="1069759414",
        personal_type="1",
        customer_name="PABLO EDUARDO MOSQUERA GUTIERREZ",
    )


class CommercialInfoTraceTests(unittest.TestCase):
    def _run(self, tsec_response, get_response):
        events: list[dict] = []
        client = CommercialInfoClient(settings=_api_settings())
        with patch.object(
            cic_module.httpx,
            "Client",
            lambda **_kwargs: _FakeClient(tsec_response, get_response),
        ), patch.object(
            cic_module,
            "schedule_trace_event",
            lambda **kwargs: events.append(kwargs),
        ):
            try:
                result = client.get_commercial_info(_identity())
                error = None
            except Exception as exc:  # noqa: BLE001
                result = None
                error = exc
        return result, error, events

    def test_success_emits_ok_traces_and_masks_document(self) -> None:
        tsec = _FakeResponse(status_code=200, headers={"tsec": "SUPER_SECRET_TSEC"})
        overview_payload = {
            "data": {
                "history": {"obligations": [{"number": "1"}, {"number": "2"}]},
                "thirdPartyResponse": {"name": "CONSULTA EXITOSA"},
            }
        }
        overview = _FakeResponse(
            status_code=200,
            json_data=overview_payload,
            content=b'{"data": {}}',
        )
        result, error, events = self._run(tsec, overview)

        self.assertIsNone(error)
        self.assertEqual(result, overview_payload)

        ops = {e["operation"]: e for e in events}
        self.assertIn("tsec", ops)
        self.assertIn("commercial_info_overview", ops)
        self.assertEqual(ops["tsec"]["outcome"], "ok")

        overview_event = ops["commercial_info_overview"]
        self.assertEqual(overview_event["outcome"], "ok")
        self.assertEqual(overview_event["status_code"], 200)
        self.assertIsInstance(overview_event["elapsed_ms"], float)
        self.assertEqual(overview_event["response_summary"]["obligations"], 2)
        # Document number must be masked in the emitted trace.
        self.assertTrue(
            overview_event["request_summary"]["document_number"].startswith("****")
        )
        # No secret leaks anywhere in the emitted events.
        blob = str(events).lower()
        self.assertNotIn("super_secret_tsec", blob)
        self.assertNotIn("secret_pwd", blob)

    def test_overview_http_error_emits_error_trace_and_raises(self) -> None:
        tsec = _FakeResponse(status_code=200, headers={"tsec": "T"})
        overview = _FakeResponse(status_code=500)
        result, error, events = self._run(tsec, overview)

        self.assertIsNone(result)
        self.assertIsInstance(error, DataSourceError)

        overview_events = [
            e
            for e in events
            if e["operation"] == "commercial_info_overview" and e["outcome"] == "error"
        ]
        self.assertEqual(len(overview_events), 1)
        self.assertEqual(overview_events[0]["outcome"], "error")
        self.assertEqual(overview_events[0]["status_code"], 500)
        self.assertIsNotNone(overview_events[0]["error_type"])

    def test_masking_helper(self) -> None:
        self.assertEqual(CommercialInfoClient._mask_document("1069759414"), "****9414")
        self.assertEqual(CommercialInfoClient._mask_document("12"), "***")
        self.assertEqual(CommercialInfoClient._mask_document(""), "***")

    def test_pdf_request_omits_content_type_and_accepts_pdf(self) -> None:
        tsec = _FakeResponse(status_code=200, headers={"tsec": "T"})
        pdf = _FakeResponse(
            status_code=200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 fake",
        )
        fake_client = _PdfFakeClient(tsec, [pdf])
        client = CommercialInfoClient(settings=_api_settings())

        with patch.object(cic_module.httpx, "Client", lambda **_kwargs: fake_client):
            result = client.request_aso_pdf(
                "/cards/v1/cards/ABC/financial-statements/EXT"
            )

        self.assertEqual(result, b"%PDF-1.4 fake")
        self.assertEqual(fake_client.get_headers, [{"Accept": "*/*", "tsec": "T"}])
        self.assertNotIn("Content-Type", fake_client.get_headers[0])

    def test_pdf_request_retries_only_after_406(self) -> None:
        tsec = _FakeResponse(status_code=200, headers={"tsec": "T"})
        rejected = _FakeResponse(status_code=406, text="not acceptable")
        pdf = _FakeResponse(
            status_code=200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 fake",
        )
        fake_client = _PdfFakeClient(tsec, [rejected, pdf])
        client = CommercialInfoClient(settings=_api_settings())

        with patch.object(cic_module.httpx, "Client", lambda **_kwargs: fake_client):
            result = client.request_aso_pdf(
                "/cards/v1/cards/ABC/financial-statements/EXT"
            )

        self.assertEqual(result, b"%PDF-1.4 fake")
        self.assertEqual(
            [headers["Accept"] for headers in fake_client.get_headers],
            ["*/*", "application/pdf"],
        )

    def test_pdf_request_rejects_non_document_success_response(self) -> None:
        tsec = _FakeResponse(status_code=200, headers={"tsec": "T"})
        json_response = _FakeResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            text='{"error": "unexpected"}',
            content=b'{"error": "unexpected"}',
        )
        client = CommercialInfoClient(settings=_api_settings())

        with patch.object(
            cic_module.httpx,
            "Client",
            lambda **_kwargs: _PdfFakeClient(tsec, [json_response]),
        ):
            with self.assertRaises(DataSourceError):
                client.request_aso_pdf(
                    "/cards/v1/cards/ABC/financial-statements/EXT"
                )


if __name__ == "__main__":
    unittest.main()
