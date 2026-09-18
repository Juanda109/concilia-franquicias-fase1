"""Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados.

Regresión del incidente en QA: el flujo listaba las tarjetas mock 4979/4567
cuando Postgres no devolvía filas (o fallaba la conexión).
"""

import os
import unittest
from unittest.mock import patch

from application.trx.analysis_service import TrxAnalysisService
from domain.trx.models import TrxCase

_MOCK_LAST4 = {"4979", "4567"}


class _EnvMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = {
            k: os.environ.get(k)
            for k in ("TRX_PRODUCTS_SOURCE", "TRX_ALLOW_MOCKS", "ASO_SOURCE", "TRX_SALESFORCE_SOURCE")
        }
        os.environ["TRX_PRODUCTS_SOURCE"] = "postgres"
        os.environ["TRX_ALLOW_MOCKS"] = "false"
        os.environ["ASO_SOURCE"] = "real"
        self.service = TrxAnalysisService()

    def tearDown(self) -> None:
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ProductosSinFallbackMockTests(_EnvMixin):
    def test_postgres_sin_filas_devuelve_not_found_sin_mocks(self) -> None:
        with patch.object(
            self.service, "_load_products_from_postgres", return_value=([], None)
        ):
            result = self.service.consultar_productos_activos(TrxCase(customer_id="123"))
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.data["products"], [])

    def test_postgres_error_devuelve_error_no_not_found(self) -> None:
        with patch.object(
            self.service, "_load_products_from_postgres", return_value=([], "db_error:OperationalError")
        ):
            result = self.service.consultar_productos_activos(TrxCase(customer_id="123"))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["products"], [])
        self.assertIn("db_error", result.data["error"])

    def test_nunca_aparecen_las_tarjetas_mock_4979_4567(self) -> None:
        for rows, err in (([], None), ([], "db_error:X")):
            with patch.object(self.service, "_load_products_from_postgres", return_value=(rows, err)):
                result = self.service.consultar_productos_activos(TrxCase(customer_id="123"))
            last4 = {
                str(p.get("last_four") or p.get("last_four_pan_id") or "")
                for p in result.data.get("products", [])
            }
            self.assertFalse(last4 & _MOCK_LAST4, f"se filtraron mocks: {last4}")

    def test_postgres_con_filas_reales_las_devuelve(self) -> None:
        real_row = {
            "contract_id": "00130067000200943399",
            "last_four_pan_id": "3399",
            "contract_status_type_desc": "ACTIVO",
            "card_type": "M",
            "origin_flag": "TDC",
            "card_flag": True,
            "card_brand": "VISA",
            "commercial_product_desc": "Tarjeta de Credito",
        }
        with patch.object(self.service, "_load_products_from_postgres", return_value=([real_row], None)):
            result = self.service.consultar_productos_activos(TrxCase(customer_id="98787954"))
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [p.get("last_four") or p.get("last_four_pan_id") for p in result.data["products"]],
            ["3399"],
        )

    def test_source_mock_con_mocks_deshabilitados_da_error(self) -> None:
        os.environ["TRX_PRODUCTS_SOURCE"] = "mock"
        result = self.service.consultar_productos_activos(TrxCase(customer_id="123"))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["error"], "mocks_disabled")
        self.assertEqual(result.data["products"], [])


class RecurrenciaRealTests(_EnvMixin):
    def test_usa_aso_real_no_el_mock(self) -> None:
        with patch.object(
            self.service, "_real_salesforce_recurrence",
            return_value={"has_recurrence": False, "target_user_id": "01-123", "matched_total": 0, "recent_total": 0},
        ) as real, patch.object(self.service, "_mock_salesforce_recurrence") as mock_fn:
            result = self.service.consultar_recurrencia_salesforce(TrxCase(customer_id="123"))
        real.assert_called_once()
        mock_fn.assert_not_called()
        self.assertEqual(result.status, "ok")

    def test_aso_caido_devuelve_error_no_asume_sin_recurrencia(self) -> None:
        with patch.object(
            self.service, "_real_salesforce_recurrence",
            return_value={"has_recurrence": False, "error": "aso_unavailable", "target_user_id": "01-123"},
        ):
            result = self.service.consultar_recurrencia_salesforce(TrxCase(customer_id="123"))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["error"], "aso_unavailable")


if __name__ == "__main__":
    unittest.main()
