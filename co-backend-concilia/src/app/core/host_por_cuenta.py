"""Comparacion de un valor esperado por cuenta contra Host HA22/HA26/HA32.

Compartido por los cuadres Redeban y VISA. Cada fuente Host se compara por
separado (nunca se suman): diferencia = esperado - (debe - haber) de la fuente,
solo con movimientos del dia de la jornada (T+0). Las fuentes obligatorias de
cada cuenta salen del inventario de consultas Host (cuentas_redeban_host.json).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

CERO = Decimal(0)
FUENTES_HOST = ("HA22", "HA26", "HA32")

Celda = tuple  # (valor: Decimal | None, estado: str)


def a_decimal(valor: Any) -> Celda:
    """R04/R05: ausente o no convertible no se calcula."""
    if valor is None or valor == "":
        return None, "VALOR_AUSENTE"
    if isinstance(valor, bool):
        return None, "VALOR_INVALIDO"
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None, "VALOR_INVALIDO"
    return (numero, "CALCULADO") if numero.is_finite() else (None, "VALOR_INVALIDO")


def texto(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def agrupar_host(host_filas: Sequence[Mapping], fecha_contable: str) -> tuple[dict, int]:
    """Debe/haber por (cuenta, fuente) del dia de la jornada; nunca suma fuentes entre si."""
    grupos: dict[tuple[str, str], dict] = {}
    otra_fecha = 0
    for h in host_filas:
        if str(h.get("fecha_contable")) != fecha_contable:
            otra_fecha += 1
            continue
        g = grupos.setdefault((str(h["cuenta"]).strip(), h["tx_host"]),
                              {"debe": CERO, "haber": CERO, "movimientos": 0, "incompletos": 0, "archivos": set()})
        g["movimientos"] += 1
        g["archivos"].add(h.get("id_archivo"))
        debe, haber = a_decimal(h.get("debe")), a_decimal(h.get("haber"))
        if debe[0] is None or haber[0] is None:
            g["incompletos"] += 1
            continue
        g["debe"] += debe[0]
        g["haber"] += haber[0]
    return grupos, otra_fecha


def comparar_fuente(esperado: Decimal | None, fuente: str, cuenta: str, grupos: dict,
                    procesadas: set[str], obligatoria: bool) -> dict:
    if fuente not in procesadas:
        return {"obligatoria": obligatoria, "estado": "INSUMO_FALTANTE", "debe": None, "haber": None,
                "neto": None, "movimientos": None, "diferencia": None, "archivos": []}
    g = grupos.get((cuenta, fuente))
    if g is None:
        debe = haber = CERO
        movimientos, estado = 0, "SIN_MOVIMIENTO_HOST"
    elif g["incompletos"]:
        return {"obligatoria": obligatoria, "estado": "DATO_INCOMPLETO", "debe": None, "haber": None,
                "neto": None, "movimientos": g["movimientos"], "diferencia": None,
                "archivos": sorted(x for x in g["archivos"] if x is not None)}
    else:
        debe, haber, movimientos, estado = g["debe"], g["haber"], g["movimientos"], "CALCULADO"
    neto = debe - haber
    diferencia = None if esperado is None else esperado - neto
    if diferencia is not None:
        estado = "COINCIDE" if diferencia == 0 else "CON_DIFERENCIA"
    return {"obligatoria": obligatoria, "estado": estado, "debe": str(debe), "haber": str(haber),
            "neto": str(neto), "movimientos": movimientos, "diferencia": texto(diferencia),
            "archivos": sorted(x for x in (g or {}).get("archivos", ()) if x is not None)}


def estado_cuenta(esperado: Decimal | None, host: dict) -> str:
    """Matriz de clasificacion monetaria (RECON-F2-005)."""
    if esperado is None:
        return "SIN_INFORMACION"
    obligatorias = [h for h in host.values() if h["obligatoria"]]
    if not obligatorias:
        return "SIN_CONSULTA_HOST"
    if any(h["neto"] is None for h in obligatorias):
        return "PENDIENTE_CONCILIACION"
    return "CONCILIADO" if all(Decimal(h["diferencia"]) == 0 for h in obligatorias) else "CON_DIFERENCIA"


def fuentes_por_cuenta(inventario_host: Sequence[Mapping]) -> dict[str, set[str]]:
    salida: dict[str, set[str]] = {}
    for item in inventario_host:
        salida.setdefault(str(item["cuenta"]), set()).add(item["insumo_host"])
    return salida
