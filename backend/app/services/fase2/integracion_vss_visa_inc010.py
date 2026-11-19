from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

from app.services.fase2.parser_vss_visa import parsear_vss110


class ErrorIntegracionVisa(ValueError):
    pass


def diagnosticar_vss110(
    texto: str,
    *,
    id_jornada: int,
    fecha_contable: date,
) -> dict:
    """Diagnostico documental sin persistencia ni conciliacion Host."""

    if type(id_jornada) is not int or id_jornada <= 0:
        raise ErrorIntegracionVisa("Jornada invalida")

    if not isinstance(fecha_contable, date) or isinstance(
        fecha_contable, datetime
    ):
        raise ErrorIntegracionVisa("Fecha contable invalida")

    reporte = parsear_vss110(texto)

    try:
        fecha_reporte = datetime.strptime(
            reporte.report_date, "%d%b%y"
        ).date()
    except ValueError as exc:
        raise ErrorIntegracionVisa("Fecha VSS invalida") from exc

    if fecha_reporte != fecha_contable:
        raise ErrorIntegracionVisa(
            "La fecha del VSS no corresponde a la jornada"
        )

    importe = reporte.simulated_net_settlement
    signo = reporte.simulated_sign

    if importe is None:
        estado = "SIN_IMPORTE_OBSERVADO"
        neto = None
    else:
        if signo not in ("CR", "DB"):
            raise ErrorIntegracionVisa("Signo VSS invalido")
        if not isinstance(importe, Decimal):
            raise ErrorIntegracionVisa("Importe VSS invalido")
        neto = importe if signo == "CR" else -importe
        estado = "IMPORTE_SIMULADO_OBSERVADO"

    return {
        "id_jornada": id_jornada,
        "fecha_contable": fecha_contable.isoformat(),
        "reporte": reporte.report_id,
        "pagina": reporte.page,
        "moneda_liquidacion": reporte.settlement_currency,
        "moneda_compensacion": reporte.clearing_currency,
        "importe_observado": str(importe) if importe is not None else None,
        "signo_observado": signo,
        "neto_observado": str(neto) if neto is not None else None,
        "estado": estado,
        "modo": "SOLO_PRUEBAS",
        "origen_simulado": importe is not None,
        "liquidacion_recalculada": None,
        "componentes_completos": False,
        "conciliado_host": False,
        "certificado": False,
    }
