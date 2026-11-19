"""RECON_F2_017 Lote 4: adaptador documental de fuente TRM.

No realiza conexiones HTTP ni escribe en PostgreSQL.
La fuente debe ser verificada antes de utilizarse.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.fase2.trm_visa_inc017 import validar_trm


FUENTE = "SUPERFINANCIERA_DATOS_ABIERTOS"
REFERENCIA = (
    "https://www.datos.gov.co/resource/32sa-8pi3.json"
)


class ErrorFuenteTRM(ValueError):
    pass


def interpretar_fecha(valor: Any) -> date:
    if isinstance(valor, datetime):
        raise ErrorFuenteTRM("Fecha con hora no admitida")

    if isinstance(valor, date):
        return valor

    if not isinstance(valor, str):
        raise ErrorFuenteTRM("Fecha invalida")

    try:
        return date.fromisoformat(valor[:10])
    except ValueError as exc:
        raise ErrorFuenteTRM("Fecha invalida") from exc


def sin_fuente(fecha_contable: date) -> dict:
    return {
        "fecha_referencia": fecha_contable.isoformat(),
        "estado": "SIN_FUENTE_OFICIAL",
        "trm_propuesta": None,
        "fuente": None,
        "referencia_fuente": None,
        "confirmada": False,
        "certificado": False,
        "conciliado_host": False,
    }


def validar_respuesta_oficial(
    *,
    fecha_contable: date,
    registros: list[dict],
    procedencia_verificada: bool = False,
) -> dict:
    """Valida registros previamente obtenidos.

    procedencia_verificada debe establecerla una capa confiable
    despues de comprobar el origen de los datos.
    """

    if type(fecha_contable) is not date:
        raise ErrorFuenteTRM("Fecha contable invalida")

    if not isinstance(registros, list):
        raise ErrorFuenteTRM("Respuesta invalida")

    if not procedencia_verificada:
        return sin_fuente(fecha_contable)

    candidatos = []

    for registro in registros:
        if not isinstance(registro, dict):
            raise ErrorFuenteTRM("Registro invalido")

        if not all(
            campo in registro
            for campo in (
                "valor", "unidad",
                "vigenciadesde", "vigenciahasta"
            )
        ):
            raise ErrorFuenteTRM("Campos TRM incompletos")

        desde = interpretar_fecha(registro["vigenciadesde"])
        hasta = interpretar_fecha(registro["vigenciahasta"])

        if desde > hasta:
            raise ErrorFuenteTRM("Intervalo TRM invalido")

        if desde <= fecha_contable <= hasta:
            if registro["unidad"] != "COP":
                raise ErrorFuenteTRM("Unidad TRM incompatible")

            valor = validar_trm(str(registro["valor"]))
            candidatos.append(valor)

    if not candidatos:
        return sin_fuente(fecha_contable)

    if len(candidatos) != 1:
        raise ErrorFuenteTRM(
            "Multiples tasas vigentes: requiere revision"
        )

    return {
        "fecha_referencia": fecha_contable.isoformat(),
        "estado": "TRM_OFICIAL_PROPUESTA",
        "trm_propuesta": str(candidatos[0]),
        "fuente": FUENTE,
        "referencia_fuente": REFERENCIA,
        "confirmada": False,
        "certificado": False,
        "conciliado_host": False,
    }
