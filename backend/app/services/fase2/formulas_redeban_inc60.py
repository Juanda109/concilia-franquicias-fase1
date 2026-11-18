"""INC60: formulas diagnosticas A/B/C de ESTRUCTURA Redeban."""

from app.services.fase2.motor_pmd_inc58 import (
    buscar_nivel,
    decimal_exacto,
)

MEDIDAS = {
    "A": {
        "debito": "DEBITO_VALOR",
        "credito": "CREDITO_VALOR",
    },
    "B": {
        "debito": "DEBITO_COMISION_INTERCAMBIO",
        "credito": "CREDITO_COMISION_INTERCAMBIO",
    },
    "C": {
        "debito": "DEBITO_COMISION_ADMINISTRATIVA",
        "credito": "CREDITO_COMISION_ADMINISTRATIVA",
    },
}


def proyectar(filas_pmd, codigo, tipo):
    """Proyeccion diagnostica por tipo economico."""
    if tipo not in MEDIDAS:
        raise ValueError("Tipo economico no reconocido")

    medidas = MEDIDAS[tipo]

    debito = buscar_nivel(
        filas_pmd, codigo, medidas["debito"]
    )
    credito = buscar_nivel(
        filas_pmd, codigo, medidas["credito"]
    )

    resultado = {
        "codigo_operacion": codigo,
        "tipo": tipo,
        "debito": debito,
        "credito": credito,
        "credito_firmado": None,
        "neto_diagnostico": None,
        "estado": "OPERANDOS_NO_RESUELTOS",
        "certificado": False,
        "diferencia_certificada": None,
    }

    if (
        debito["estado"] != "ENCONTRADO"
        or credito["estado"] != "ENCONTRADO"
    ):
        return resultado

    if debito["valor"] is None or credito["valor"] is None:
        resultado["estado"] = "VALOR_AUSENTE"
        return resultado

    valor_debito = decimal_exacto(debito["valor"])
    valor_credito = decimal_exacto(credito["valor"])

    resultado["credito_firmado"] = str(-valor_credito)
    resultado["neto_diagnostico"] = str(
        valor_debito - valor_credito
    )
    resultado["estado"] = "CALCULO_DIAGNOSTICO"

    return resultado
