"""Integracion documental Visa por archivo asociado a jornada.

No consulta archivos arbitrarios, no escribe en PostgreSQL,
no convierte USD sin TRM confirmada y no homologa cuentas.
"""

from decimal import Decimal, ROUND_HALF_UP

from app.services.fase2.parser_vss_integral_inc018 import (
    extraer_resumen,
    ErrorVSSIntegral,
)
from app.services.fase2.monetario_vss120_inc018 import (
    extraer_vss120,
    validar_muestra_vss120,
)


def convertir_cop(importe, trm):
    valor = Decimal(str(importe))
    tasa = Decimal(str(trm))

    if not valor.is_finite():
        raise ValueError("Importe no finito")

    if not tasa.is_finite() or tasa <= 0:
        raise ValueError("TRM invalida")

    return str(
        (valor * tasa).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def integrar_vss(
    *,
    id_jornada,
    id_archivo,
    fecha_contable,
    contenido,
    trm_confirmada=None,
):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("Jornada invalida")

    if type(id_archivo) is not int or id_archivo <= 0:
        raise ValueError("Archivo invalido")

    if not isinstance(contenido, str) or not contenido.strip():
        raise ValueError("Contenido VSS vacio")

    documental = extraer_resumen(contenido)
    evidencias = extraer_vss120(contenido)

    requeridos = {"VSS-110", "VSS-115", "VSS-120"}

    if not requeridos.issubset(documental["reportes"]):
        raise ErrorVSSIntegral(
            "Faltan reportes requeridos en esta integracion"
        )

    if documental["paridad_110_115"] is not True:
        raise ErrorVSSIntegral(
            "Liquidacion VSS-110/VSS-115 inconsistente"
        )

    monetario = validar_muestra_vss120(evidencias)

    neto = Decimal(documental["liquidacion_unica_usd"])
    interchange = Decimal(
        monetario["interchange_neto_usd"]
    )

    if not neto.is_finite() or not interchange.is_finite():
        raise ErrorVSSIntegral("Importes invalidos")

    resumen = {
        "liquidacion_neta_usd": str(neto),
        "interchange_neto_usd": str(interchange),
        "clearing_ventas_cop": monetario[
            "clearing_ventas_cop"
        ],
        "liquidacion_neta_cop": None,
        "trm_aplicada": None,
        "trm_version": None,
        "estado_conversion": "PENDIENTE_TRM_CONFIRMADA",
    }

    if trm_confirmada is not None:
        if (
            trm_confirmada.get("estado") != "TRM_CONFIRMADA"
            or trm_confirmada.get("confirmada") is not True
            or trm_confirmada.get("id_jornada") != id_jornada
            or str(trm_confirmada.get("fecha_referencia"))
                != str(fecha_contable)
            or not isinstance(
                trm_confirmada.get("version"), int
            )
            or trm_confirmada["version"] <= 0
        ):
            raise ValueError("TRM no confirmada para la jornada")

        tasa = trm_confirmada["trm_aplicada"]

        resumen["liquidacion_neta_cop"] = convertir_cop(
            neto, tasa
        )
        resumen["trm_aplicada"] = str(tasa)
        resumen["trm_version"] = trm_confirmada["version"]
        resumen["estado_conversion"] = "CONVERSION_DOCUMENTAL"

    return {
        "id_jornada": id_jornada,
        "id_archivo": id_archivo,
        "fecha_contable": str(fecha_contable),
        "reportes": documental["reportes"],
        "resumen_monetario": resumen,
        "detalle_vss120": evidencias,
        "paridad_110_115": True,
        "certificado": False,
        "conciliado_host": False,
        "homologado_contablemente": False,
    }
