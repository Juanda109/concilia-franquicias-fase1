"""INC61: diagnostico de cantidades PMD / ESTRUCTURA."""

import re
from decimal import Decimal

PATRON = re.compile(
    r"^\s*=\s*\+?\s*IFERROR\s*\(\s*"
    r"VLOOKUP\s*\(\s*\$?F\$?(\d+)\s*,\s*"
    r"PMD!\$C:\$N\s*,\s*(\d+)\s*,\s*0\s*\)"
    r"\s*,\s*0\s*\)\s*$",
    re.I,
)

MEDIDAS = {
    "DEBITO": ("cantidad_debito_formula", "DEBITO_CANTIDAD", 2),
    "CREDITO": ("cantidad_credito_formula", "CREDITO_CANTIDAD", 7),
}


def comparar_cantidad(fila_catalogo, fila_pmd, lado):
    if lado not in MEDIDAS:
        raise ValueError("Lado invalido")

    campo, medida, indice = MEDIDAS[lado]
    literal = fila_catalogo[campo]
    cantidad_pmd = fila_pmd.get(medida)

    resultado = {
        "fila_excel": fila_catalogo["fila_excel"],
        "codigo_operacion": fila_catalogo["codigo_operacion"],
        "lado": lado,
        "cantidad_plantilla": None,
        "cantidad_pmd": (
            str(cantidad_pmd)
            if cantidad_pmd is not None else None
        ),
        "estado": None,
        "certificado": False,
    }

    if literal is None:
        resultado["estado"] = "CANTIDAD_VACIA"
        return resultado

    if isinstance(literal, str) and literal.startswith("="):
        encontrado = PATRON.search(literal)

        if (
            encontrado is None
            or int(encontrado.group(1)) != fila_catalogo["fila_excel"]
            or int(encontrado.group(2)) != indice
        ):
            resultado["estado"] = "CANTIDAD_FORMULA_NO_RECONOCIDA"
            return resultado

        if cantidad_pmd is None:
            resultado["estado"] = "CANTIDAD_PMD_AUSENTE"
            return resultado

        resultado["estado"] = "CANTIDAD_PMD"
        resultado["cantidad_plantilla"] = resultado["cantidad_pmd"]
        return resultado

    if isinstance(literal, (bool, float)):
        resultado["estado"] = "CANTIDAD_FIJA_NO_EXACTA"
        resultado["cantidad_plantilla"] = str(literal)
        return resultado

    try:
        fijo = Decimal(str(literal))
        pmd = (
            Decimal(str(cantidad_pmd))
            if cantidad_pmd is not None else None
        )
    except Exception as exc:
        raise ValueError("Cantidad invalida") from exc

    resultado["cantidad_plantilla"] = str(fijo)

    if pmd is None:
        resultado["estado"] = "CANTIDAD_PMD_AUSENTE"
    elif fijo == pmd:
        resultado["estado"] = "CANTIDAD_FIJA_COINCIDENTE"
    else:
        resultado["estado"] = "CANTIDAD_FIJA_DIFERENTE"

    return resultado
