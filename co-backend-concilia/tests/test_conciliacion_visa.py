"""Conciliacion VISA (Plantilla Maestra filas 5 y 161-181), sin BD ni Excel."""
from decimal import Decimal

import pytest

from app.core.conciliacion_visa import (CapturaInvalida, calcular_liquidacion, construir_conciliacion_visa,
                                        validar_captura)

FECHA = "2026-07-03"
ENTIDAD = "1000804671 SUMM ACQ BBVA"


def reporte(id_rep, report_id, *, entidad=ENTIDAD, moneda="USD", proc=FECHA):
    return {"id_vss_reporte": id_rep, "id_archivo": 50, "report_id": report_id,
            "reporting_for": "1000804673 408573 ACQ BBVA", "funds_xfer_entity": entidad,
            "proc_date": proc, "settlement_currency": moneda}


def det115(concepto, credito, debito, id_rep=2):
    return {"id_vss_reporte": id_rep, "seccion": "ACQUIRER TRANSACTIONS", "concepto": concepto,
            "clearing_currency": None, "clearing_amount": None, "credit_amount": credito,
            "debit_amount": debito, "naturaleza": None}


# VSS-115 de "VSS BBVA 02 JULIO.txt" (FINAL SETTLEMENT NET AMOUNT 363,512.54CR)
DETALLE_MUESTRA = [det115("PURCHASE", "370657.17", "0"), det115("DISPUTE FIN", "0", "223.56"),
                   det115("DISPUTE RESP FIN", "15.52", "0"), det115("REIMBURSEMENT FEES", "4.25", "6940.84"),
                   {"id_vss_reporte": 3, "seccion": "ACQUIRER TRANSACTIONS", "concepto": "DISPUTE FIN",
                    "clearing_currency": "USD", "clearing_amount": "223.56", "credit_amount": None,
                    "debit_amount": "223.56", "naturaleza": "DB"}]
REPORTES_MUESTRA = [reporte(1, "VSS-110"), reporte(2, "VSS-115"), reporte(3, "VSS-120")]
# International SS_Data_2026-07-03.pdf
ISS_MUESTRA = [
    {"id_archivo": 60, "ftsre": "1000804671", "nombre": "Bbva Colombia", "moneda": "USD",
     "monto_neto": "363512.54", "naturaleza": "CR", "fecha_valor": FECHA},
    {"id_archivo": 60, "ftsre": "9000737875", "nombre": "Banco Bilbao Vizcaya Argentaria Colombia",
     "moneda": "USD", "monto_neto": "1606698.17", "naturaleza": "DB", "fecha_valor": FECHA},
]


def cap(**valores):
    return {k: {"valor": Decimal(v), "version": 1, "usuario": "op", "fecha": "2026-07-03"} for k, v in valores.items()}


def conciliar(capturas=None, *, reportes=REPORTES_MUESTRA, detalle=DETALLE_MUESTRA, iss=ISS_MUESTRA, host=(),
              procesadas=("HA22", "HA26", "HA32"), inventario=()):
    return construir_conciliacion_visa(
        jornada={"id_jornada": 9, "fecha_contable": FECHA}, vss_reportes=list(reportes), vss_detalle=list(detalle),
        iss_filas=list(iss), capturas=capturas or {}, host_filas=list(host), fuentes_procesadas=list(procesadas),
        inventario_host=list(inventario))


def test_neto_vss115_de_la_muestra_coincide_con_el_pdf_international_ss():
    r = conciliar()
    assert r["vss"]["liquidaciones"][0]["neto"] == "363512.54"
    control = r["controles"][0]
    assert (control["entidad"], control["iss"], control["diferencia"], control["estado"]) == \
        ("1000804671", "363512.54", "0.00", "COINCIDE")


def test_vss_sin_linea_iss_o_sin_insumo():
    otra = [reporte(2, "VSS-115", entidad="1000999999 OTRA")]
    assert conciliar(reportes=otra)["controles"][0]["estado"] == "SIN_LINEA_ISS"
    assert conciliar(iss=())["controles"][0]["estado"] == "INSUMO_FALTANTE"


def test_diferencia_vss_iss_y_avisos_de_fecha_y_moneda():
    iss = [{**ISS_MUESTRA[0], "monto_neto": "363500.00", "fecha_valor": "2026-07-04"}]
    r = conciliar(iss=iss, reportes=[reporte(2, "VSS-115", moneda="EUR")])
    assert r["controles"][0]["estado"] == "CON_DIFERENCIA" and r["controles"][0]["diferencia"] == "12.54"
    assert any("EUR" in a for a in r["advertencias"]) and any("2026-07-04" in a for a in r["advertencias"])


def test_vss120_agrupa_por_concepto_con_signo():
    fila = next(x for x in conciliar()["vss"]["vss120"] if x["concepto"] == "DISPUTE FIN")
    assert fila["clearing"] == "-223.56" and fila["moneda_clearing"] == "USD"


def test_formulas_de_la_plantilla():
    liq = calcular_liquidacion(cap(M169="4000", L169="10", L170="-100", L172="2", N179="1", N180="0.5",
                                   M177="-1000", L162="-400000"))
    c = {k: v["valor"] for k, v in liq["celdas"].items()}
    assert c["L171"] == "-90"
    assert c["N169"] == "-40000" and c["N170"] == "400000" and c["N171"] == "360000"
    assert c["N172"] == "8000" and c["F5"] == "400000" and c["L161"] == "400000"
    assert c["M176"] == "-360000" and c["M178"] == "8000" and c["M179"] == "4000" and c["M180"] == "2000.0"
    # M181 = SUM(M176:M180) * -1 balancea el asiento
    assert c["M181"] == "347000.0"
    assert sum(Decimal(l["valor"]) for l in liq["asiento"]) == 0
    assert liq["asiento"][-1]["cuenta"] == "519095145" and liq["asiento"][-1]["naturaleza"] == "DEBITO"
    assert liq["validacion_canje_internacional"]["estado"] == "CUADRA"


def test_pdf_credito_debita_compensacion_y_la_diferencia_en_cambio_balancea():
    # pdf positivo (Visa abona a BBVA) -> M176 = L171*TRM, debito en 196095001063
    liq = calcular_liquidacion(cap(M169="4000", L170="100", M177="-500000"))
    assert liq["asiento"][0]["valor"] == "400000" and liq["asiento"][0]["naturaleza"] == "DEBITO"
    ultima = liq["asiento"][-1]
    assert ultima["valor"] == "100000" and ultima["cuenta"] == "519095145"
    liq = calcular_liquidacion(cap(M169="4000", L170="100", M177="-300000"))
    assert liq["asiento"][-1]["valor"] == "-100000"
    assert liq["asiento"][-1]["cuenta"] == "411595196" and liq["asiento"][-1]["naturaleza"] == "CREDITO"


def test_sin_trm_no_calcula_cop_ni_compara_host():
    r = conciliar(cap(L170="-100"), inventario=[{"cuenta": "196095001829", "insumo_host": "HA32"}])
    assert r["estado"] == "CAPTURA_PENDIENTE"
    assert r["liquidacion"]["celdas"]["N170"]["valor"] is None
    assert r["liquidacion"]["celdas"]["N170"]["estado"] == "FALTA_TRM"
    assert all(c["estado"] == "SIN_INFORMACION" for c in r["cuentas"])
    assert any("M169" in a for a in r["advertencias"])


def test_campo_opcional_sin_capturar_vale_cero_como_celda_vacia():
    liq = calcular_liquidacion(cap(M169="4000", L170="-100"))
    assert liq["celdas"]["L171"]["valor"] == "-100" and liq["celdas"]["L169"]["estado"] == "SIN_CAPTURA"
    assert liq["validacion_canje_internacional"]["estado"] == "SIN_CAPTURA_CARTA"
    # M177 es captura: sin digitar queda vacía (no "0") aunque el asiento la use como 0
    assert liq["celdas"]["M177"]["valor"] is None and liq["celdas"]["M177"]["estado"] == "SIN_CAPTURA"
    con_m177 = calcular_liquidacion(cap(M169="4000", L170="100", M177="-400000"))["celdas"]["M177"]
    assert con_m177["valor"] == "-400000" and con_m177["version"] == 1 and con_m177["usuario"] == "op"


def test_asiento_contra_host_por_fuente():
    capturas = cap(M169="4000", L170="100", M177="-400000")
    host = [{"id_archivo": 7, "tx_host": "HA32", "cuenta": "196095001829", "fecha_contable": FECHA,
             "debe": "0", "haber": "400000"},
            {"id_archivo": 8, "tx_host": "HA22", "cuenta": "196095001063", "fecha_contable": FECHA,
             "debe": "400000", "haber": "0"}]
    r = conciliar(capturas, host=host, inventario=[{"cuenta": "196095001829", "insumo_host": "HA32"}])
    assert r["estado"] == "LIQUIDACION_CALCULADA"
    cuentas = {c["cuenta"]: c for c in r["cuentas"]}
    assert cuentas["196095001829"]["esperado"] == "-400000" and cuentas["196095001829"]["estado"] == "CONCILIADO"
    # 196095001063 no esta en el inventario de consultas Host: se muestra, no se concilia
    assert cuentas["196095001063"]["host"]["HA22"]["estado"] == "COINCIDE"
    assert cuentas["196095001063"]["estado"] == "SIN_CONSULTA_HOST"


def test_validar_captura():
    assert validar_captura({"M169": "4012.3456", "L170": "-1,250.50", "L169": None}) == \
        {"M169": Decimal("4012.3456"), "L170": Decimal("-1250.50"), "L169": None}
    for malo, codigo in [({"M169": "0"}, "TRM_NO_POSITIVA"), ({"M169": "1.12345"}, "DEMASIADOS_DECIMALES"),
                         ({"L170": "1.234"}, "DEMASIADOS_DECIMALES"), ({"X1": "1"}, "CAMPO_NO_CAPTURABLE"),
                         ({"L170": "abc"}, "VALOR_INVALIDO"), ({"L170": 1.5}, "VALOR_INVALIDO"), ({}, "CAPTURA_VACIA")]:
        with pytest.raises(CapturaInvalida, match=codigo):
            validar_captura(malo)
