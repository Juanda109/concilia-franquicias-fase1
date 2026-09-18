import unittest

from application.trx.aso_rules import paginar_movimientos


def _movs(n: int) -> list[dict]:
    return [{"id": f"TX{i:03d}", "descripcion": f"m{i}", "valor": i} for i in range(n)]


class PaginarMovimientosTests(unittest.TestCase):
    def test_primera_pagina_llena(self) -> None:
        r = paginar_movimientos(_movs(12), page=1, page_size=5)
        self.assertEqual(r["page"], 1)
        self.assertEqual(r["total"], 12)
        self.assertEqual(r["total_pages"], 3)
        self.assertEqual(len(r["movimientos"]), 5)
        self.assertEqual(r["movimientos"][0]["id"], "TX000")
        self.assertFalse(r["has_prev"])
        self.assertTrue(r["has_next"])

    def test_pagina_intermedia(self) -> None:
        r = paginar_movimientos(_movs(12), page=2, page_size=5)
        self.assertEqual([m["id"] for m in r["movimientos"]],
                         ["TX005", "TX006", "TX007", "TX008", "TX009"])
        self.assertTrue(r["has_prev"])
        self.assertTrue(r["has_next"])

    def test_ultima_pagina_parcial(self) -> None:
        r = paginar_movimientos(_movs(12), page=3, page_size=5)
        self.assertEqual(len(r["movimientos"]), 2)
        self.assertTrue(r["has_prev"])
        self.assertFalse(r["has_next"])

    def test_page_sobre_total_se_acota_a_la_ultima(self) -> None:
        r = paginar_movimientos(_movs(12), page=99, page_size=5)
        self.assertEqual(r["page"], 3)
        self.assertEqual(len(r["movimientos"]), 2)
        self.assertFalse(r["has_next"])

    def test_page_menor_que_uno_se_acota_a_uno(self) -> None:
        r = paginar_movimientos(_movs(12), page=0, page_size=5)
        self.assertEqual(r["page"], 1)
        self.assertFalse(r["has_prev"])

    def test_dia_vacio(self) -> None:
        r = paginar_movimientos([], page=1, page_size=5)
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["total_pages"], 1)
        self.assertEqual(r["movimientos"], [])
        self.assertFalse(r["has_prev"])
        self.assertFalse(r["has_next"])

    def test_page_size_invalido_cae_a_cinco(self) -> None:
        r = paginar_movimientos(_movs(7), page=1, page_size=0)
        self.assertEqual(r["page_size"], 5)
        self.assertEqual(r["total_pages"], 2)

    def test_setenta_movimientos_catorce_paginas(self) -> None:
        r = paginar_movimientos(_movs(70), page=14, page_size=5)
        self.assertEqual(r["total_pages"], 14)
        self.assertEqual(len(r["movimientos"]), 5)
        self.assertFalse(r["has_next"])


if __name__ == "__main__":
    unittest.main()
