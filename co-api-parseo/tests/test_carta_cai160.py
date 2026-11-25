"""Hoja CAI 160 A de la Carta de Compensacion (listado sumario por codigo y BIN)."""
from openpyxl import Workbook

from app.ingestion.result import IngestionResult
from app.parsers.carta_compensacion import CartaCompensacionParser


def _pagina(bin_, nombre, lineas):
    return [
        " CAI0160A    LISTADO SUMARIO DEL INTERCAMBIO CLASIFICADO POR CODIGO DE TRANSACCION",
        "0             ENTIDAD FINANCIERA: BBVA",
        f"              {bin_}    {nombre}",
        " CD   ---DESCRIPCION----",
        *lineas,
    ]


def _hoja(lineas):
    wb = Workbook()
    ws = wb.active
    ws.title = "CAI 160 A"
    for i, linea in enumerate(lineas, 1):
        ws.cell(i, 1, linea)
    return ws


def _parse(lineas):
    r = IngestionResult("CARTA_COMPENSACION")
    descartes = {}
    CartaCompensacionParser()._parse_cai160(_hoja(lineas), r, lambda m: descartes.__setitem__(m, descartes.get(m, 0) + 1))
    return r, descartes


PAGINA_1 = _pagina("404280", "PLATINUM BBVA", [
    "002  ORIGINAL AVANCES        0                        0           0                    0          0           0   ",
    " 04  ORIGINAL PAGOS         17   114,681,486          0           0   114,681,486       0     17   114,681,486          0          0 114.681.486   ",
    " 08  ORIGINAL REEMBOLSO     17     7,561,210          0     135.321-    7,425,889       0     17     7,561,210          0    135.321   7.425.889   ",
    " 36  REPRESENT VENTAS        1     3,120,340          0           0     3,120,340       0      1     3,120,340          0          0   3.120.340-  ",
    " 99  TOTALES                35   119,122,356          0     135.321-  118,987,035       0     35   119,122,356          0    135.321 118.987.035   ",
])
PAGINA_2 = _pagina("421892", "CREDITO CLASICA BBVA", [
    " 16  DEVOLUCION VENTAS       2       500,000          0           0       500,000       0      2       500,000          0          0     500.000-  ",
    " 99  TOTALES                 2       500,000          0           0       500,000       0      2       500,000          0          0     500.000-  ",
])


def test_lee_valor_total_consolidado_por_bin_y_codigo():
    r, descartes = _parse(PAGINA_1 + PAGINA_2)
    datos = {(x["motivo_codigo"], x["concepto"].split(" - BIN ")[1][:6]): x["valor_total"]
             for x in r.records if not x["es_control"]}
    assert datos == {("CAI160_04", "404280"): 114681486, ("CAI160_08", "404280"): 7425889,
                     ("CAI160_36", "404280"): -3120340, ("CAI160_16", "421892"): -500000}
    assert descartes == {"CAI160_SIN_MOVIMIENTO": 1}
    assert not r.errors
    assert any(c["codigo"] == "CUADRE_CAI160_POR_BIN" and c["estado"] == "OK" for c in r.controls)


def test_descuadre_contra_99_totales_es_error():
    pagina = PAGINA_2[:-1] + [" 99  TOTALES       2   500,000   0   0   500,000   0   2   500,000   0   0   400.000-  "]
    r, _ = _parse(pagina)
    assert [e.code if hasattr(e, "code") else e for e in r.errors] and "DESCUADRE_CAI160" in str(r.errors[0].__dict__)
