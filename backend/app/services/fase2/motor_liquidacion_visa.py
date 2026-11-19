"""Motor documental Visa Fase 2: reglas VSS-001..004; NO concilia Host.

Entradas explícitas desde VSS-110. No extrae archivos ni persiste datos.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

CENTAVO = Decimal('0.01')
CONCEPTOS = ('interchange', 'reimbursement_fees', 'visa_charges')
IDS = {'interchange': 'VISA-VSS-001', 'reimbursement_fees': 'VISA-VSS-002', 'visa_charges': 'VISA-VSS-003'}


class ErrorLiquidacionVisa(ValueError):
    pass


def importe(valor: str | Decimal) -> Decimal:
    """Importe decimal con precisión de centavos, sin redondeo implícito."""
    if isinstance(valor, bool) or not isinstance(valor, (str, Decimal)):
        raise ErrorLiquidacionVisa('El importe debe ser texto decimal o Decimal')
    try:
        numero = Decimal(valor)
    except (InvalidOperation, ValueError) as exc:
        raise ErrorLiquidacionVisa('Importe inválido') from exc
    if not numero.is_finite() or numero.as_tuple().exponent < -2:
        raise ErrorLiquidacionVisa('Importe no finito o con más de dos decimales')
    if numero < 0:
        raise ErrorLiquidacionVisa('Crédito/débito debe ser no negativo')
    return numero.quantize(CENTAVO)


@dataclass(frozen=True)
class MovimientoVSS:
    credito: Decimal
    debito: Decimal

    @classmethod
    def desde_valores(cls, credito: str | Decimal, debito: str | Decimal):
        return cls(importe(credito), importe(debito))

    @property
    def neto(self) -> Decimal:
        return self.credito - self.debito

    @property
    def signo(self) -> str:
        return 'CR' if self.neto > 0 else 'DB' if self.neto < 0 else 'CERO'


def liquidar_vss110(*, entidad: str, moneda: str, conceptos: Mapping[str, MovimientoVSS],
                   credito_total: str | Decimal | None = None,
                   debito_total: str | Decimal | None = None) -> dict:
    """Evalúa reglas documentales; exige entidad, moneda y tres conceptos.

    El control de totales es opcional y, si se suministra, debe incluir ambos.
    No equipara entidades distintas ni monedas distintas.
    """
    if not entidad or not entidad.isdigit():
        raise ErrorLiquidacionVisa('Entidad de liquidación inválida')
    if moneda != 'USD':
        raise ErrorLiquidacionVisa('Esta versión solo admite VSS-110 USD')
    if set(conceptos) != set(CONCEPTOS):
        raise ErrorLiquidacionVisa('Conceptos incompletos o adicionales')
    if any(not isinstance(v, MovimientoVSS) for v in conceptos.values()):
        raise ErrorLiquidacionVisa('Tipo de movimiento inválido')
    for v in conceptos.values():
        importe(v.credito)
        importe(v.debito)
    if (credito_total is None) != (debito_total is None):
        raise ErrorLiquidacionVisa('Se requieren ambos totales o ninguno')
    credito = sum((v.credito for v in conceptos.values()), Decimal('0.00'))
    debito = sum((v.debito for v in conceptos.values()), Decimal('0.00'))
    if credito_total is not None and (credito != importe(credito_total) or debito != importe(debito_total)):
        raise ErrorLiquidacionVisa('Totales VSS-110 inconsistentes')
    neto = credito - debito
    return {
        'entidad': entidad, 'moneda': moneda, 'modo': 'VALIDACION_DOCUMENTAL',
        'certificado': False, 'conciliado_host': False,
        'reglas': [
            {'id': IDS[c], 'concepto': c, 'credito': str(conceptos[c].credito),
             'debito': str(conceptos[c].debito), 'neto': str(conceptos[c].neto),
             'signo': conceptos[c].signo}
            for c in CONCEPTOS
        ],
        'total': {'id': 'VISA-VSS-004', 'credito': str(credito), 'debito': str(debito),
                  'neto': str(neto), 'signo': 'CR' if neto > 0 else 'DB' if neto < 0 else 'CERO'},
    }
