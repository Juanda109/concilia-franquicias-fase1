"""INC60: clasificacion conservadora de excepciones ESTRUCTURA."""

import re

INDICES = {
    "A": (3, 8),
    "B": (4, 9),
    "C": (5, 10),
}

PATRON = re.compile(
    r"VLOOKUP\s*\([^,;]+,\s*PMD!\$C:\$N,\s*(\d+)",
    re.IGNORECASE,
)


def indice_formula(valor):
    if not isinstance(valor, str):
        return None

    encontrado = PATRON.search(valor)

    return int(encontrado.group(1)) if encontrado else None


def clasificar(fila):
    """Clasifica por contenido, sin depender solo del numero Excel."""
    tipo = fila["tipo_operacion"]
    categoria = fila["categoria"]
    codigo = fila["codigo_operacion"]

    base = {
        "fila_excel": fila["fila_excel"],
        "codigo_operacion": codigo,
        "categoria": categoria,
        "cuenta_contable": fila["cuenta_contable"],
        "certificado": False,
    }

    if codigo == "N/A" or tipo.startswith("CANCELACIÓN PARTIDA"):
        return {
            **base,
            "estado": "PARTIDA_MANUAL_NO_HOMOLOGADA",
            "indices": None,
        }

    debito = indice_formula(fila["debito_formula"])
    credito = indice_formula(fila["credito_formula"])

    indices = (debito, credito)

    if indices != INDICES[categoria]:
        return {
            **base,
            "estado": "FORMULA_EXCEPCIONAL_PENDIENTE",
            "indices": indices,
        }

    return {
        **base,
        "estado": "FORMULA_ESTANDAR",
        "indices": indices,
    }
