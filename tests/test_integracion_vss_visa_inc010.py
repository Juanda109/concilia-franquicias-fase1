from datetime import date
import pytest

from app.services.fase2.integracion_vss_visa_inc010 import (
    diagnosticar_vss110,
    ErrorIntegracionVisa,
)

VSS = """REPORT ID: VSS-110 PAGE: 1
SETTLEMENT CURRENCY: COP
CLEARING CURRENCY: COP
REPORT DATE: 12NOV26
SIMULATED NET SETTLEMENT 1250.00CR
END OF VSS-110
"""


def ejecutar(texto=VSS):
    return diagnosticar_vss110(
        texto,
        id_jornada=6606,
        fecha_contable=date(2026, 11, 12),
    )


def test_importe_simulado():
    r = ejecutar()
    assert r["neto_observado"] == "1250.00"
    assert r["moneda_liquidacion"] == "COP"
    assert r["estado"] == "IMPORTE_SIMULADO_OBSERVADO"


def test_no_certifica():
    r = ejecutar()
    assert r["certificado"] is False
    assert r["conciliado_host"] is False
    assert r["liquidacion_recalculada"] is None
    assert r["componentes_completos"] is False


def test_debito():
    r = ejecutar(VSS.replace("1250.00CR", "1250.00DB"))
    assert r["neto_observado"] == "-1250.00"


def test_sin_importe():
    texto = VSS.replace(
        "SIMULATED NET SETTLEMENT 1250.00CR\n", ""
    )
    r = ejecutar(texto)
    assert r["neto_observado"] is None
    assert r["estado"] == "SIN_IMPORTE_OBSERVADO"


def test_fecha_incorrecta():
    with pytest.raises(ErrorIntegracionVisa):
        diagnosticar_vss110(
            VSS,
            id_jornada=6606,
            fecha_contable=date(2026, 11, 13),
        )


def test_jornada_invalida():
    with pytest.raises(ErrorIntegracionVisa):
        diagnosticar_vss110(
            VSS,
            id_jornada=0,
            fecha_contable=date(2026, 11, 12),
        )
