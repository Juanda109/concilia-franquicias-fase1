from datetime import date
from decimal import Decimal

from app.services.fase2.integracion_vss_visa_inc010 import (
    diagnosticar_vss110,
)


def test_paridad_vss110_12nov26():
    """Reproduce el registro documental observado de jornada 6606."""

    registro = {
        "reporte": "VSS-110",
        "pagina": 1,
        "moneda_liquidacion": "COP",
        "moneda_compensacion": "COP",
        "fecha_reporte": "12NOV26",
        "concepto": "SIMULATED NET SETTLEMENT",
        "valores": ["1250.00"],
        "signos": ["CR"],
        "texto_original": (
            "SIMULATED NET SETTLEMENT 1,250.00CR"
        ),
    }

    texto = (
        f"REPORT ID: {registro['reporte']} "
        f"PAGE: {registro['pagina']}\n"
        f"SETTLEMENT CURRENCY: "
        f"{registro['moneda_liquidacion']}\n"
        f"CLEARING CURRENCY: "
        f"{registro['moneda_compensacion']}\n"
        f"REPORT DATE: {registro['fecha_reporte']}\n"
        f"{registro['texto_original']}\n"
        "END OF VSS-110\n"
    )

    resultado = diagnosticar_vss110(
        texto,
        id_jornada=6606,
        fecha_contable=date(2026, 11, 12),
    )

    assert resultado["reporte"] == registro["reporte"]
    assert resultado["moneda_liquidacion"] == "COP"
    assert resultado["moneda_compensacion"] == "COP"
    assert Decimal(resultado["importe_observado"]) == Decimal(
        registro["valores"][0]
    )
    assert resultado["signo_observado"] == "CR"
    assert resultado["neto_observado"] == "1250.00"
    assert resultado["estado"] == "IMPORTE_SIMULADO_OBSERVADO"
    assert resultado["origen_simulado"] is True
    assert resultado["componentes_completos"] is False
    assert resultado["liquidacion_recalculada"] is None
    assert resultado["conciliado_host"] is False
    assert resultado["certificado"] is False
