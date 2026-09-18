import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from infrastructure.entrypoint.fastapi_app import app
import infrastructure.entrypoint.api.router.v0.trx_router as trx_router


def _ok(n: int) -> dict:
    return {
        "ok": True,
        "movimientos": [{"id": f"TX{i:03d}", "descripcion": f"m{i}", "valor": i}
                        for i in range(n)],
        "fuera_de_rango": 0,
        "total_del_dia": n,
        "monto_min": 0,
        "monto_max": 999999,
    }


class MovimientosPaginaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _get(self, **params):
        base = {"card_id": "4912684136504818", "fecha": "06/08/2026"}
        base.update(params)
        return self.client.get("/v1/trx/movimientos-pagina", params=base)

    @patch.object(trx_router, "_consultar_movimientos_dia")
    def test_primera_pagina(self, mock_c) -> None:
        mock_c.return_value = _ok(12)
        r = self._get(page=1, page_size=5)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["total"], 12)
        self.assertEqual(body["total_pages"], 3)
        self.assertEqual(len(body["movimientos"]), 5)
        self.assertFalse(body["has_prev"])
        self.assertTrue(body["has_next"])

    @patch.object(trx_router, "_consultar_movimientos_dia")
    def test_ultima_pagina(self, mock_c) -> None:
        mock_c.return_value = _ok(12)
        body = self._get(page=3, page_size=5).json()
        self.assertEqual(len(body["movimientos"]), 2)
        self.assertTrue(body["has_prev"])
        self.assertFalse(body["has_next"])

    @patch.object(trx_router, "_consultar_movimientos_dia")
    def test_fallo_aso_es_fail_closed(self, mock_c) -> None:
        mock_c.return_value = {
            "ok": False, "movimientos": [], "fuera_de_rango": 0,
            "total_del_dia": 0, "monto_min": 0, "monto_max": 0,
        }
        body = self._get(page=1).json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["movimientos"], [])
        self.assertFalse(body["has_prev"])
        self.assertFalse(body["has_next"])

    @patch.object(trx_router, "_consultar_movimientos_dia")
    def test_dia_vacio_no_es_error(self, mock_c) -> None:
        mock_c.return_value = _ok(0)
        body = self._get(page=1).json()
        self.assertEqual(body["status"], "not_found")
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["total_pages"], 1)

    def test_page_cero_rechazado_por_validacion(self) -> None:
        # page tiene ge=1: FastAPI responde 422 sin tocar el ASO.
        self.assertEqual(self._get(page=0).status_code, 422)


if __name__ == "__main__":
    unittest.main()
