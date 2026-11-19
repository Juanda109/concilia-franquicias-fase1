"""INC021: elegibilidad documental de evidencia Host."""

from dataclasses import dataclass
from typing import Optional


SINTETICO = "SINTETICO"
ORIGEN_NO_VERIFICADO = "ORIGEN_NO_VERIFICADO"
ELEGIBLE_REVISION = "ELEGIBLE_REVISION"


@dataclass(frozen=True)
class ResultadoElegibilidad:
    estado: str
    motivo: str
    puede_homologar: bool = False
    certificado: bool = False
    conciliado_host: bool = False
    homologado_contablemente: bool = False


def clasificar_movimiento(
    movimiento,
    procedencia_verificada=False,
):
    if not isinstance(movimiento, dict):
        raise TypeError("Movimiento Host invalido")

    concepto = str(
        movimiento.get("concepto") or ""
    ).strip().upper()

    referencia = str(
        movimiento.get("referencia") or ""
    ).strip().upper()

    if (
        "PRUEBA SINTETICA" in concepto
        or "NO CONCILIAR" in concepto
        or referencia == "S"
    ):
        return ResultadoElegibilidad(
            estado=SINTETICO,
            motivo="INDICADOR_EXPLICITO_PRUEBA",
        )

    if procedencia_verificada is not True:
        return ResultadoElegibilidad(
            estado=ORIGEN_NO_VERIFICADO,
            motivo="PROCEDENCIA_NO_ACREDITADA",
        )

    return ResultadoElegibilidad(
        estado=ELEGIBLE_REVISION,
        motivo="PROCEDENCIA_DOCUMENTADA",
    )


def evaluar_lote(movimientos):
    resultados = []

    for movimiento in movimientos:
        resultado = clasificar_movimiento(movimiento)

        resultados.append({
            "tx_host": movimiento.get("tx_host"),
            "cuenta": movimiento.get("cuenta"),
            "linea_origen": movimiento.get("linea_origen"),
            "estado": resultado.estado,
            "motivo": resultado.motivo,
            "puede_homologar": False,
        })

    return {
        "incremento": "INC021",
        "modo": "DIAGNOSTICO_SOLO_LECTURA",
        "movimientos": resultados,
        "certificado": False,
        "conciliado_host": False,
        "homologado_contablemente": False,
    }
