"""Parser conservador de VSS-110 para Concilia V1.

Soporta el layout minimo entregado para la jornada 12NOV26 y no inventa
campos no presentes en la evidencia. No persiste ni concilia Host.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


class ErrorVSSVisa(ValueError):
    pass


@dataclass(frozen=True)
class VSS110:
    report_id: str
    page: int
    settlement_currency: str
    clearing_currency: str
    report_date: str
    simulated_net_settlement: Decimal | None
    simulated_sign: str | None


REPORT_ID = re.compile(r"REPORT ID:\s*(VSS-110)\b", re.I)
PAGE = re.compile(r"PAGE:\s*(\d+)", re.I)
SETTLEMENT = re.compile(r"SETTLEMENT CURRENCY:\s*([A-Z]{3})\b", re.I)
CLEARING = re.compile(r"CLEARING CURRENCY:\s*([A-Z]{3})\b", re.I)
REPORT_DATE = re.compile(r"REPORT DATE:\s*(\d{2}[A-Z]{3}\d{2})\b", re.I)
# RECON_F2_011_FORMATO_MILES_VSS
SIMULATED = re.compile(
    r"SIMULATED NET SETTLEMENT\s+"
    r"((?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)\.[0-9]{2})"
    r"(CR|DB)\b",
    re.I,
)


def _decimal(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ErrorVSSVisa("Importe VSS invalido") from exc
    if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2:
        raise ErrorVSSVisa("Importe VSS fuera de formato")
    return value.quantize(Decimal("0.01"))


def parsear_vss110(texto: str) -> VSS110:
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorVSSVisa("Contenido VSS vacio")

    report = REPORT_ID.search(texto)
    page = PAGE.search(texto)
    settlement = SETTLEMENT.search(texto)
    clearing = CLEARING.search(texto)
    report_date = REPORT_DATE.search(texto)
    simulated = SIMULATED.search(texto)

    if not report or not page or not settlement or not clearing or not report_date:
        raise ErrorVSSVisa("Cabecera VSS-110 incompleta")

    simulated_amount = _decimal(simulated.group(1).replace(",", "")) if simulated else None
    simulated_sign = simulated.group(2).upper() if simulated else None

    return VSS110(
        report_id=report.group(1).upper(),
        page=int(page.group(1)),
        settlement_currency=settlement.group(1).upper(),
        clearing_currency=clearing.group(1).upper(),
        report_date=report_date.group(1).upper(),
        simulated_net_settlement=simulated_amount,
        simulated_sign=simulated_sign,
    )
