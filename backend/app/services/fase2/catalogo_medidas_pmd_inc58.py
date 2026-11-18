"""Catalogo de medidas PMD Fase 2.

Distingue columnas del archivo PMDGeneralEntidad
de las posiciones de la hoja PMD de la plantilla.
"""

MEDIDAS_ORIGEN = {
    "C": "DEBITO_CANTIDAD",
    "D": "DEBITO_VALOR",
    "E": "DEBITO_COMISION_INTERCAMBIO",
    "F": "DEBITO_COMISION_ADMINISTRATIVA",
    "G": "DEBITO_NETO",
    "H": "CREDITO_CANTIDAD",
    "I": "CREDITO_VALOR",
    "J": "CREDITO_COMISION_INTERCAMBIO",
    "K": "CREDITO_COMISION_ADMINISTRATIVA",
    "L": "CREDITO_NETO",
    "M": "TOTAL",
}

# Indices VLOOKUP sobre PMD!C:N.
# Sin homologacion automatica a campos de origen.

INDICES_PLANTILLA = {
    2: "D",
    3: "E",
    6: "H",
    7: "I",
    8: "J",
    11: "M",
    12: "N",
}

MEDIDAS_PLANTILLA = {
    2: "DEBITO_CANTIDAD",
    3: "DEBITO_VALOR",
    6: "DEBITO_NETO",
    7: "CREDITO_CANTIDAD",
    8: "CREDITO_VALOR",
    11: "CREDITO_NETO",
    12: "TOTAL",
}


def columna_plantilla(indice):
    if type(indice) is not int or indice not in INDICES_PLANTILLA:
        raise ValueError("Indice de plantilla no reconocido")

    return INDICES_PLANTILLA[indice]


def medida_origen(columna):
    if columna not in MEDIDAS_ORIGEN:
        raise ValueError("Columna de origen no reconocida")

    return MEDIDAS_ORIGEN[columna]


def medida_plantilla(indice):
    if type(indice) is not int or indice not in MEDIDAS_PLANTILLA:
        raise ValueError("Indice VLOOKUP no homologado")

    return MEDIDAS_PLANTILLA[indice]
