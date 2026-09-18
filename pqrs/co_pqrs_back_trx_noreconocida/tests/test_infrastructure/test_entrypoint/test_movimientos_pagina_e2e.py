"""Fase 3: integracion del endpoint paginado sobre el fixture real de 70
movimientos (tarjeta de Fabian, 06/08). Ejercita el parse + filtro + paginacion
REALES; solo se sustituye el cliente ASO por el fixture (como haria el simulador).
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from infrastructure.entrypoint.fastapi_app import app
import infrastructure.entrypoint.api.router.v0.trx_router as trx_router

_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "co_pqrs_back_trx_aso_simulator" / "data" / "operations"
    / "4912684136504818.json"
)


def _ops_de_la_fecha(day_iso: str) -> dict:
    """Devuelve el fixture recortado a la fecha, como hace el simulador."""
    full = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    data = []
    for blk in full.get("data") or []:
        ops = [op for op in (blk.get("operations") or [])
               if str(op.get("dateOper") or op.get("operationDate") or "")[:10] == day_iso]
        if ops:
            nb = dict(blk); nb["operations"] = ops; data.append(nb)
    return {"data": data}


class _AsoFake:
    def get_tsec(self):
        return "tsec-test"

    def operations(self, card_id, *, operation_date, page_size=100,
                   pagination_key=1, tsec=None):
        return _ops_de_la_fecha(operation_date)


class MovimientosPaginaE2ETests(unittest.TestCase):
    CARD = "4912684136504818"
    FECHA = "06/08/2026"

    def setUp(self):
        self.client = TestClient(app)
        self._patch = patch.object(trx_router, "TrxAsoClient", _AsoFake)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _page(self, page):
        r = self.client.get("/v1/trx/movimientos-pagina", params={
            "card_id": self.CARD, "fecha": self.FECHA, "page": page,
            # sin filtro de importe restrictivo: los 70 del dia
            "from_amount": 0, "to_amount": 99999999,
        })
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_setenta_movimientos_catorce_paginas(self):
        b = self._page(1)
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["total"], 70)
        self.assertEqual(b["total_pages"], 14)
        self.assertEqual(len(b["movimientos"]), 5)
        self.assertFalse(b["has_prev"])
        self.assertTrue(b["has_next"])

    def test_ultima_pagina(self):
        b = self._page(14)
        self.assertEqual(len(b["movimientos"]), 5)
        self.assertTrue(b["has_prev"])
        self.assertFalse(b["has_next"])

    def test_paginas_no_se_solapan_y_los_id_son_estables(self):
        vistos = []
        primera_vez = {}
        for pg in range(1, 15):
            b = self._page(pg)
            ids = [m["id"] for m in b["movimientos"]]
            self.assertTrue(all(ids), f"pagina {pg} con id vacio")
            vistos.extend(ids)
            primera_vez[pg] = ids
        # 70 ids unicos (sin solape entre paginas)
        self.assertEqual(len(vistos), 70)
        self.assertEqual(len(set(vistos)), 70)

    def test_ida_y_vuelta_devuelve_los_mismos_id(self):
        # avanzar a la 3, volver a la 1: la 1 trae exactamente lo mismo (Sabor A,
        # acceso aleatorio por numero de pagina, sin cursor que se pierda).
        ida1 = [m["id"] for m in self._page(1)["movimientos"]]
        self._page(2)
        self._page(3)
        vuelta1 = [m["id"] for m in self._page(1)["movimientos"]]
        self.assertEqual(ida1, vuelta1)


if __name__ == "__main__":
    unittest.main()
