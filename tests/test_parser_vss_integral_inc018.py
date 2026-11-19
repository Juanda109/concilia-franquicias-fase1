from decimal import Decimal

from app.services.fase2.parser_vss_integral_inc018 import (
    extraer_resumen,
    ultimo_importe,
)


def test_signos():
    assert ultimo_importe("TOTAL 363,512.54CR")[
        "valor_firmado"
    ] == "363512.54"

    assert ultimo_importe("TOTAL 6,936.59DB")[
        "valor_firmado"
    ] == "-6936.59"


def test_reportes_multipagina():
    texto = """
REPORT ID: VSS-110 PAGE: 1
SETTLEMENT CURRENCY: USD
NET SETTLEMENT AMOUNT 363,512.54CR
REPORT ID: VSS-115 PAGE: 1
SETTLEMENT CURRENCY: USD
FINAL SETTLEMENT NET AMOUNT 363,512.54CR
REPORT ID: VSS-120 PAGE: 1
SETTLEMENT CURRENCY: USD
CLEARING CURRENCY: COP
TOTAL ORIGINAL SALE 7,471 1,271,476,045.00CR 370,657.17
REPORT ID: VSS-120 PAGE: 2
SETTLEMENT CURRENCY: USD
CLEARING CURRENCY: USD
TOTAL ACQUIRER INTERCHANGE 3 208.04DB 15.52 223.56
"""

    resultado = extraer_resumen(texto)

    assert resultado["paridad_110_115"] is True
    assert resultado["liquidacion_unica_usd"] == "363512.54"
    assert resultado["reportes"]["VSS-120"]["paginas"] == [1, 2]
    assert resultado["certificado"] is False
    assert resultado["conciliado_host"] is False


def test_paridad_incorrecta():
    texto = """
REPORT ID: VSS-110 PAGE: 1
NET SETTLEMENT AMOUNT 100.00CR
REPORT ID: VSS-115 PAGE: 1
FINAL SETTLEMENT NET AMOUNT 90.00CR
"""
    r = extraer_resumen(texto)
    assert r["paridad_110_115"] is False
    assert r["liquidacion_unica_usd"] is None


def test_decimal():
    assert Decimal(
        ultimo_importe("1,271,476,045.00CR")["valor_firmado"]
    ) == Decimal("1271476045.00")
