"""Evaluador aislado de las cuatro formulas excepcionales de ESTRUCTURA.

Las filas PMD deben representar literalmente las 12 columnas C:N; no se
infieren posiciones desde el esquema de persistencia de PostgreSQL.
"""
from decimal import Decimal, InvalidOperation

INDICES = {1371: (4, 9), 1640: (4, 10), 3110: (5, 10), 3111: (5, 10)}


def _importe(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError("Importe booleano")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Importe invalido") from exc
    if not d.is_finite():
        raise ValueError("Importe no finito")
    return d


def evaluar(fila_excel, codigo, cuenta, version_catalogo, filas_pmd):
    """Evalua VLOOKUP exacto: cada fila PMD es secuencia de C:N (12 valores).

    Un codigo ausente, repetido o con operandos vacios NO equivale a cero.
    """
    if fila_excel not in INDICES:
        raise ValueError("Fila excepcional no reconocida")
    if not version_catalogo:
        raise ValueError("Version obligatoria")
    i_debito, i_credito = INDICES[fila_excel]
    r = dict(fila_excel=fila_excel, codigo_operacion=codigo,
             cuenta_contable=cuenta, version_catalogo=version_catalogo,
             indices_pmd=[i_debito, i_credito], debito=None, credito=None,
             neto_diagnostico=None, certificado=False,
             estado="OPERANDOS_NO_RESUELTOS")
    encontrados = []
    for registro in filas_pmd:
        if len(registro) != 12:
            raise ValueError("PMD debe contener columnas C:N")
        if str(registro[0]).strip() == str(codigo).strip():
            encontrados.append(registro)
    if len(encontrados) > 1:
        r["estado"] = "CODIGO_PMD_DUPLICADO"
        return r
    if not encontrados:
        return r
    registro = encontrados[0]
    n = _importe(registro[i_debito - 1])
    o = _importe(registro[i_credito - 1])
    if n is None or o is None:
        return r
    credito = -o
    r.update(debito=str(n), credito=str(credito),
             neto_diagnostico=str(n + credito),
             estado="CALCULO_DIAGNOSTICO_EXCEPCIONAL")
    return r
