"""INC62: evaluacion diagnostica de referencias ESTRUCTURA."""

import re

PATRON_DIRECTO = re.compile(
    r"^=\+?\$M\$(1|2)$",
    re.I,
)

PATRON_PARENTESIS = re.compile(
    r"^=\(\+\$M\$(1|2)\)$",
    re.I,
)

PATRON_PREFIJO = re.compile(
    r'^=\+?"(75|71|67)"&\$M\$2$',
    re.I,
)


def evaluar_referencia(fila, m1, m2, version_catalogo):
    if not version_catalogo:
        raise ValueError("Version de catalogo requerida")

    formula = fila["referencia_contable_formula"]

    resultado = {
        "fila_excel": fila["fila_excel"],
        "codigo_operacion": fila["codigo_operacion"],
        "cuenta_contable": fila["cuenta_contable"],
        "version_catalogo": version_catalogo,
        "formula_original": formula,
        "tipo_original": type(formula).__name__,
        "referencia_diagnostica": None,
        "estado": None,
        "certificado": False,
    }

    if formula is None:
        resultado["estado"] = "REFERENCIA_SIN_VALOR"
        return resultado

    if isinstance(formula, bool):
        resultado["estado"] = "REFERENCIA_TIPO_NO_ADMITIDO"
        return resultado

    if isinstance(formula, int):
        resultado["referencia_diagnostica"] = str(formula)
        resultado["estado"] = "REFERENCIA_LITERAL_NUMERICA"
        return resultado

    if not isinstance(formula, str):
        resultado["estado"] = "REFERENCIA_TIPO_NO_ADMITIDO"
        return resultado

    texto = formula.strip()

    if not texto:
        resultado["estado"] = "REFERENCIA_SIN_VALOR"
        return resultado

    if not texto.startswith("="):
        resultado["referencia_diagnostica"] = texto
        resultado["estado"] = "REFERENCIA_LITERAL_TEXTO"
        return resultado

    directo = PATRON_DIRECTO.fullmatch(texto)
    parentesis = PATRON_PARENTESIS.fullmatch(texto)
    prefijo = PATRON_PREFIJO.fullmatch(texto)

    if directo or parentesis:
        coincidencia = directo or parentesis
        parametro = coincidencia.group(1)

        valor = m1 if parametro == "1" else m2

        if not isinstance(valor, str) or not valor:
            resultado["estado"] = "REFERENCIA_PARAMETRO_INVALIDO"
            return resultado

        resultado["referencia_diagnostica"] = valor
        resultado["estado"] = "REFERENCIA_FORMULA_RECONOCIDA"
        return resultado

    if prefijo:
        if not isinstance(m2, str) or not m2:
            resultado["estado"] = "REFERENCIA_PARAMETRO_INVALIDO"
            return resultado

        resultado["referencia_diagnostica"] = (
            prefijo.group(1) + m2
        )
        resultado["estado"] = "REFERENCIA_FORMULA_RECONOCIDA"
        return resultado

    resultado["estado"] = "REFERENCIA_FORMULA_DESCONOCIDA"
    return resultado
