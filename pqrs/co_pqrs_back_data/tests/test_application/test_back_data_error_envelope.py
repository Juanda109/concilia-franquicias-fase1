"""Tests: back_data ALWAYS records a control-table envelope, incl. on ASO error.

This is the regression guard for the false "no tienes reportes negativos" bug:
when the ASO fails (e.g. 409), the background task must write a status=error
envelope (no data), so the agent never serves a stale/empty "no reports".
"""

from __future__ import annotations

import unittest

import pandas as pd
from pandas import DataFrame

from application.customer.consultar_service import (
    process_consultar_customer_request,
)
from domain.customer.models import CustomerIdentity
from infrastructure.entrypoint.api.errors.exceptions import DataSourceError


class StubIdentityRepository:
    def read_customer_identity_df(self, customer_id: str | None = None) -> DataFrame:
        return pd.DataFrame(
            [{"customer_id": customer_id or "123", "personal_id": "1", "personal_type": "01"}]
        )

    def find_by_customer_id_in_df(self, *, customer_id, customer_identity_df):
        return CustomerIdentity(
            customer_id=customer_id,
            personal_id="1",
            personal_type="01",
            customer_name="TITULAR PRUEBA",
        )


class RaisingCommercialInfoClient:
    """Simulates the ASO returning a 409 (DataSourceError with status_code)."""

    def get_commercial_info(self, identity):
        raise DataSourceError("Commercial info API request failed.", details={"status_code": 409})


class PassiveIdentityRepository(StubIdentityRepository):
    def read_customer_identity_df(self, customer_id: str | None = None) -> DataFrame:
        return pd.DataFrame(
            [
                {
                    "customer_id": customer_id or "123",
                    "personal_id": "1",
                    "personal_type": "01",
                    "key_id": "456",
                    "origin_flag": "PASIVE",
                    "contract_id": "00131234567890",
                }
            ]
        )


class SuccessfulCommercialInfoClient:
    def get_commercial_info(self, identity):
        return {
            "data": {
                "customer": {
                    "fullname": "TITULAR PRUEBA",
                    "identityDocument": {
                        "documentNumber": "1",
                        "documentType": {"description": "01"},
                    },
                },
                "history": {"score": []},
            }
        }


class RaisingEmbargoRepository:
    def read_embargo_join_by_contract_id(self, *, contract_id: str):
        raise DataSourceError("DEM query failed.", details={"status_code": 503})


class RecordingOpenSearchClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def update_client_control_data(
        self, *, customer_id, workflow, data=None, status="ok", run_id=None, error=None
    ) -> None:
        self.calls.append(
            {
                "customer_id": customer_id,
                "workflow": workflow,
                "data": data,
                "status": status,
                "run_id": run_id,
                "error": error,
            }
        )


class ErrorEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_aso_error_writes_error_envelope_without_data(self) -> None:
        os_client = RecordingOpenSearchClient()

        await process_consultar_customer_request(
            customer_id="123",
            workflow="centrales_de_riesgo",
            identity_repository=StubIdentityRepository(),
            commercial_info_client=RaisingCommercialInfoClient(),
            opensearch_client=os_client,
            correlation_id="123_20260716",
            run_id="run-xyz",
        )

        # Exactly one write, and it MUST be the error envelope (no OK write).
        self.assertEqual(len(os_client.calls), 1)
        call = os_client.calls[0]
        self.assertEqual(call["status"], "error")
        self.assertEqual(call["run_id"], "run-xyz")
        self.assertIsNone(call["data"])
        self.assertIsInstance(call["error"], dict)
        self.assertEqual(call["error"]["status_code"], 409)
        self.assertEqual(call["error"]["type"], "DataSourceError")

    async def test_dem_error_writes_error_envelope_without_no_embargo_data(self) -> None:
        os_client = RecordingOpenSearchClient()

        await process_consultar_customer_request(
            customer_id="123",
            workflow="centrales_de_riesgo",
            identity_repository=PassiveIdentityRepository(),
            commercial_info_client=SuccessfulCommercialInfoClient(),
            embargo_repository=RaisingEmbargoRepository(),
            opensearch_client=os_client,
            correlation_id="123_20260716",
            run_id="run-dem-error",
        )

        self.assertEqual(len(os_client.calls), 1)
        call = os_client.calls[0]
        self.assertEqual(call["status"], "error")
        self.assertEqual(call["run_id"], "run-dem-error")
        self.assertIsNone(call["data"])
        self.assertEqual(call["error"]["status_code"], 503)
        self.assertEqual(call["error"]["type"], "DataSourceError")


if __name__ == "__main__":
    unittest.main()
