"""INC021: modelo de homologacion VISA pendiente de aprobacion."""

from dataclasses import dataclass
from typing import Optional


CUENTAS_VISA = (
    "259095341",
    "299095888",
    "299095303",
)

CONCEPTOS = {
    "LIQUIDACION_NETA_USD": "USD",
    "LIQUIDACION_NETA_COP": "COP",
    "INTERCHANGE_NETO_USD": "USD",
    "CLEARING_VENTAS_COP": "COP",
}


class HomologacionNoAprobada(ValueError):
    pass


@dataclass(frozen=True)
class ReglaHomologacion:
    concepto: str
    moneda: str
    cuenta_host: Optional[str] = None
    fuente_host: Optional[str] = None
    signo: Optional[str] = None
    formula: Optional[str] = None
    tolerancia: Optional[str] = None
    evidencia: Optional[str] = None
    aprobacion: Optional[str] = None

    @property
    def aprobada(self):
        return False


def matriz_pendiente():
    return [
        ReglaHomologacion(
            concepto=concepto,
            moneda=moneda,
        )
        for concepto, moneda in CONCEPTOS.items()
    ]


def validar_homologacion(regla):
    if not isinstance(regla, ReglaHomologacion):
        raise TypeError("Regla de homologacion invalida")

    if regla.concepto not in CONCEPTOS:
        raise HomologacionNoAprobada(
            "Concepto VISA no reconocido"
        )

    if regla.moneda != CONCEPTOS[regla.concepto]:
        raise HomologacionNoAprobada(
            "Moneda incompatible"
        )

    raise HomologacionNoAprobada(
        "INC021 no dispone de reglas contables aprobadas"
    )


def calcular_diferencia(*args, **kwargs):
    raise HomologacionNoAprobada(
        "Diferencia contable deshabilitada"
    )


def estado_inc021():
    return {
        "incremento": "INC021",
        "estado": "PENDIENTE_VALIDACION_FUNCIONAL",
        "cuentas_candidatas": list(CUENTAS_VISA),
        "reglas": [
            vars(regla)
            for regla in matriz_pendiente()
        ],
        "diferencia_contable": None,
        "certificado": False,
        "conciliado_host": False,
        "homologado_contablemente": False,
    }
