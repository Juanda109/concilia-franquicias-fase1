"""operations() debe recorrer TODAS las paginas del ASO y acumularlas: un dia
con mas de pageSize operaciones ya no se recorta a la primera pagina."""
import unittest
from unittest.mock import patch

import infrastructure.persistence.aso_client as aso_mod
from infrastructure.persistence.aso_client import TrxAsoClient


def _pagina(ops_ids, page, total_pages):
    return {
        "data": [{"operations": [{"id": i, "dateOper": "2026-08-06"} for i in ops_ids]}],
        "pagination": {"page": page, "totalPages": total_pages, "totalElements": 999},
    }


class OperationsPaginadoTests(unittest.TestCase):
    def setUp(self):
        aso_mod._OPERATIONS_CACHE.clear()

    def _ids(self, payload):
        out = []
        for blk in payload.get("data") or []:
            out.extend(op["id"] for op in blk.get("operations") or [])
        return out

    def test_acumula_las_tres_paginas(self):
        paginas = {
            1: _pagina(["a", "b"], 1, 3),
            2: _pagina(["c", "d"], 2, 3),
            3: _pagina(["e"], 3, 3),
        }
        def fake_get(path, params, tsec, operation=""):
            return paginas[params["paginationKey"]]
        with patch.object(TrxAsoClient, "get_tsec", return_value="t"), \
             patch.object(TrxAsoClient, "_get", side_effect=fake_get):
            payload = TrxAsoClient().operations("4912684136504818",
                                                operation_date="2026-08-06")
        self.assertEqual(self._ids(payload), ["a", "b", "c", "d", "e"])

    def test_una_sola_pagina_no_pide_mas(self):
        calls = []
        def fake_get(path, params, tsec, operation=""):
            calls.append(params["paginationKey"])
            return _pagina(["x"], 1, 1)
        with patch.object(TrxAsoClient, "get_tsec", return_value="t"), \
             patch.object(TrxAsoClient, "_get", side_effect=fake_get):
            TrxAsoClient().operations("c1", operation_date="2026-08-06")
        self.assertEqual(calls, [1])  # totalPages=1 -> una sola llamada

    def test_fallo_a_mitad_devuelve_lo_acumulado(self):
        def fake_get(path, params, tsec, operation=""):
            k = params["paginationKey"]
            return _pagina(["a", "b"], 1, 3) if k == 1 else None
        with patch.object(TrxAsoClient, "get_tsec", return_value="t"), \
             patch.object(TrxAsoClient, "_get", side_effect=fake_get):
            payload = TrxAsoClient().operations("c2", operation_date="2026-08-06")
        self.assertEqual(self._ids(payload), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
