"""Cuadre Redeban desde F1 persistida, con la homologacion de la plantilla de cuadre.

La hoja ESTRUCTURA de "Estructura Cuadre Redeban" asigna cada codigo de operacion
PMD a una cuenta contable (catalogos/estructura_redeban.json). Por fila:
N = VLOOKUP(codigo, PMD!C:N, indice_debito), O = VLOOKUP(..., indice_credito) * -1,
P = N + O, Q/R = cantidades (indices 2 y 7). CARGA MASIVA suma P por cuenta y
VALIDADOR compara, por nivel 1, la suma de ESTRUCTURA contra el total PMD.

Cada cuenta se compara contra HA22, HA26 y HA32 por separado (nunca se suman):
diferencia = neto PMD - (debe - haber) de la fuente. Las fuentes obligatorias de
cada cuenta salen del inventario de consultas Host (cuentas_redeban_host.json).
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Mapping, Sequence

from app.core.host_por_cuenta import (CERO, FUENTES_HOST, Celda, a_decimal as _dec, agrupar_host,
                                      comparar_fuente as _comparar_fuente,
                                      estado_cuenta as _estado_cuenta, texto as _txt)

MEDIDA_POR_INDICE = {
    2: "DEBITO_CANTIDAD", 3: "DEBITO_VALOR", 4: "DEBITO_COMISION_INTERCAMBIO",
    5: "DEBITO_COMISION_ADMIN", 6: "DEBITO_NETO", 7: "CREDITO_CANTIDAD", 8: "CREDITO_VALOR",
    9: "CREDITO_COMISION_INTERCAMBIO", 10: "CREDITO_COMISION_ADMIN", 11: "CREDITO_NETO", 12: "TOTAL",
}
SIN_CUENTA = ("", "None", "N/A")
_RE_NIVEL_1 = re.compile(r"^\d+\.\d+$")


class IndicePmd:
    """PMD!C:N indexado por codigo (NIVEL), sin filas de control (R10)."""

    def __init__(self, pmd_filas: Sequence[Mapping]) -> None:
        self.filas: dict[str, Mapping] = {}
        self.duplicados: set[str] = set()
        for fila in pmd_filas:
            if fila.get("ES_CONTROL"):
                continue
            codigo = str(fila.get("NIVEL") or "").strip()
            if not codigo:
                continue
            if codigo in self.filas:
                self.duplicados.add(codigo)
            self.filas.setdefault(codigo, fila)

    def buscar(self, codigo: str, indice: int) -> Celda:
        """IFERROR(VLOOKUP(codigo,PMD!C:N,indice,0),0): ausencia = 0 de Excel (R02)."""
        if codigo in self.duplicados:
            return None, "NIVEL_DUPLICADO"  # R03: no elegir arbitrariamente
        fila = self.filas.get(codigo)
        if fila is None:
            return CERO, "SIN_COINCIDENCIA"
        return _dec(fila.get(MEDIDA_POR_INDICE[indice]))


_SIN_MOVIMIENTO = {"SIN_COINCIDENCIA", "SIN_MOVIMIENTO_PMD"}


def _op(funcion, *celdas: Celda) -> Celda:
    """Si todos los operandos son 'codigo ausente en el PMD', el resultado es el 0 de Excel."""
    for valor, estado in celdas:
        if valor is None:
            return None, estado
    estados = {e for _, e in celdas}
    return funcion(*(v for v, _ in celdas)), ("SIN_MOVIMIENTO_PMD" if estados <= _SIN_MOVIMIENTO else "CALCULADO")


def filas_catalogo(catalogo: Mapping) -> list[dict]:
    columnas = catalogo["columnas"]
    return [dict(zip(columnas, fila)) for fila in catalogo["filas"]]


def evaluar_fila(fila: Mapping, pmd: IndicePmd) -> dict:
    """Columnas N, O, P, Q y R de ESTRUCTURA para una fila del catalogo."""
    base = {"fila": fila["fila"], "cuenta": fila["cuenta"], "codigo_pmd": fila["codigo_pmd"],
            "tipo": fila["tipo"], "nombre_operacion": fila["nombre_operacion"],
            "tipo_inconsistente": bool(fila.get("tipo_inconsistente"))}
    if fila["manual"]:
        return {**base, "debito": None, "credito": None, "neto": None,
                "cantidad_debito": None, "cantidad_credito": None, "estado": "CAPTURA_MANUAL"}
    codigo = fila["codigo_pmd"]
    n = pmd.buscar(codigo, fila["indice_debito"])
    o = _op(lambda v: v * fila["signo_credito"], pmd.buscar(codigo, fila["indice_credito"]))
    p = _op(lambda a, b: a + b, n, o)
    q = pmd.buscar(codigo, 2)
    r = pmd.buscar(codigo, 7)
    return {**base, "debito": _txt(n[0]), "credito": _txt(o[0]), "neto": _txt(p[0]),
            "cantidad_debito": _txt(q[0]), "cantidad_credito": _txt(r[0]), "estado": p[1]}


def _sumar(filas: Sequence[dict], campo: str) -> Decimal:
    return sum((Decimal(f[campo]) for f in filas if f[campo] is not None), CERO)


def _incompleta(fila: dict) -> bool:
    return fila["estado"] != "CAPTURA_MANUAL" and fila["neto"] is None


def _con_movimiento(fila: dict) -> bool:
    """Movimiento monetario; Q/R (cantidades) se repiten en las filas A/B/C del mismo codigo."""
    return any(fila[c] is not None and Decimal(fila[c]) != 0 for c in ("debito", "credito"))


def validador(evaluadas: Sequence[dict], pmd: IndicePmd) -> list[dict]:
    """Hoja VALIDADOR: por nivel 1 (MID(codigo,1,3)), L = suma P de ESTRUCTURA + total PMD."""
    por_nivel: dict[str, list[dict]] = {}
    for f in evaluadas:
        if f["estado"] != "CAPTURA_MANUAL":
            por_nivel.setdefault(f["codigo_pmd"][:3], []).append(f)
    for codigo in pmd.filas:
        if _RE_NIVEL_1.match(codigo):
            por_nivel.setdefault(codigo, [])
    salida = []
    for nivel in sorted(por_nivel):
        filas = por_nivel[nivel]
        incompleta = any(_incompleta(f) for f in filas)
        f_neto = None if incompleta else _sumar(filas, "neto")
        h, i, j = pmd.buscar(nivel, 6), pmd.buscar(nivel, 11), pmd.buscar(nivel, 12)
        l = _op(lambda a, b: a + b, (f_neto, "CALCULADO" if f_neto is not None else "DATO_INCOMPLETO"), j)
        if not filas:
            estado = "SIN_FILAS_ESTRUCTURA"
        elif l[0] is None:
            estado = l[1]
        else:
            estado = "CUADRA" if l[0] == 0 else "DESCUADRE"
        salida.append({
            "nivel_1": nivel, "filas_estructura": len(filas),
            "debito_estructura": None if incompleta else str(_sumar(filas, "debito")),
            "credito_estructura": None if incompleta else str(_sumar(filas, "credito")),
            "neto_estructura": _txt(f_neto),
            "debito_neto_pmd": _txt(h[0]), "credito_neto_pmd": _txt(i[0]), "total_pmd": _txt(j[0]),
            "control": _txt(l[0]), "estado": estado,
        })
    return salida


def codigos_pmd_sin_estructura(pmd: IndicePmd, codigos_estructura: set[str]) -> list[dict]:
    """Operaciones PMD de ultimo nivel con valor que ninguna fila de ESTRUCTURA asigna a cuenta."""
    codigos = list(pmd.filas)
    salida = []
    for codigo in sorted(codigos):
        if codigo in codigos_estructura or any(c.startswith(codigo + ".") for c in codigos):
            continue
        fila = pmd.filas[codigo]
        neto_d, neto_c = _dec(fila.get("DEBITO_NETO")), _dec(fila.get("CREDITO_NETO"))
        if (neto_d[0] or CERO) == 0 and (neto_c[0] or CERO) == 0:
            continue
        salida.append({"codigo_pmd": codigo, "producto_servicio": fila.get("PRODUCTO_SERVICIO"),
                       "debito_neto": _txt(neto_d[0]), "credito_neto": _txt(neto_c[0]),
                       "linea_origen": fila.get("numero_linea")})
    return salida


def codigos_pmd_cobertura_parcial(pmd: IndicePmd, evaluadas: Sequence[dict]) -> list[dict]:
    """Codigos PMD con filas en ESTRUCTURA cuya suma de P no iguala el neto PMD del codigo
    (debito neto - credito neto), p. ej. porque falta la fila de alguna comision (tipo A/B/C)."""
    por_codigo: dict[str, list[dict]] = {}
    for f in evaluadas:
        if f["estado"] != "CAPTURA_MANUAL":
            por_codigo.setdefault(f["codigo_pmd"], []).append(f)
    salida = []
    for codigo in sorted(por_codigo):
        fila = pmd.filas.get(codigo)
        filas = por_codigo[codigo]
        if fila is None or codigo in pmd.duplicados or any(_incompleta(f) for f in filas):
            continue
        debito_neto, credito_neto = _dec(fila.get("DEBITO_NETO")), _dec(fila.get("CREDITO_NETO"))
        if debito_neto[0] is None or credito_neto[0] is None:
            continue
        esperado = debito_neto[0] - credito_neto[0]
        obtenido = _sumar(filas, "neto")
        if obtenido != esperado:
            salida.append({"codigo_pmd": codigo, "producto_servicio": fila.get("PRODUCTO_SERVICIO"),
                           "neto_pmd": str(esperado), "neto_estructura": str(obtenido),
                           "diferencia": str(obtenido - esperado),
                           "tipos_en_estructura": sorted({f["tipo"] for f in filas})})
    return salida


def construir_cuadre_redeban(*, jornada: Mapping, catalogo: Mapping, pmd_filas: Sequence[Mapping],
                             host_filas: Sequence[Mapping], fuentes_procesadas: Sequence[str],
                             inventario_host: Sequence[Mapping]) -> dict:
    fecha = str(jornada["fecha_contable"])
    resultado = {
        "id_jornada": jornada["id_jornada"], "fecha_contable": fecha,
        "catalogo": {"version": catalogo["version_catalogo"], **catalogo["fuente"], "filas": len(catalogo["filas"])},
        "fuentes_host_procesadas": sorted(fuentes_procesadas),
    }
    if not pmd_filas:
        return {**resultado, "estado": "INSUMO_PMD_FALTANTE", "resumen": {}, "cuentas": [], "validador": [],
                "codigos_pmd_sin_estructura": [], "codigos_pmd_cobertura_parcial": [],
                "movimientos_pmd_sin_cuenta": [], "filas_tipo_inconsistente": []}

    pmd = IndicePmd(pmd_filas)
    filas = filas_catalogo(catalogo)
    evaluadas = [evaluar_fila(f, pmd) for f in filas]
    fuentes_por_cuenta: dict[str, set[str]] = {}
    for item in inventario_host:
        fuentes_por_cuenta.setdefault(str(item["cuenta"]), set()).add(item["insumo_host"])
    grupos, otra_fecha = agrupar_host(host_filas, fecha)
    procesadas = set(fuentes_procesadas)

    por_cuenta: dict[str, list[dict]] = {}
    sin_cuenta = []
    for f in evaluadas:
        if f["cuenta"] in SIN_CUENTA:
            if f["estado"] != "CAPTURA_MANUAL" and (_incompleta(f) or _con_movimiento(f)):
                sin_cuenta.append(f)
        else:
            por_cuenta.setdefault(f["cuenta"], []).append(f)

    cuentas = []
    for cuenta in sorted(por_cuenta):
        filas_cuenta = por_cuenta[cuenta]
        calculables = [f for f in filas_cuenta if f["estado"] != "CAPTURA_MANUAL"]
        incompletas = [f for f in calculables if _incompleta(f)]
        neto_pmd = None if incompletas else _sumar(calculables, "neto")
        obligatorias = fuentes_por_cuenta.get(cuenta, set())
        host = {fuente: _comparar_fuente(neto_pmd, fuente, cuenta, grupos, procesadas, fuente in obligatorias)
                for fuente in FUENTES_HOST}
        cuentas.append({
            "cuenta": cuenta,
            "filas_estructura": len(filas_cuenta),
            "debito": None if incompletas else str(_sumar(calculables, "debito")),
            "credito": None if incompletas else str(_sumar(calculables, "credito")),
            "neto_pmd": _txt(neto_pmd),
            "operaciones": [f for f in calculables if _con_movimiento(f) or _incompleta(f)],
            "filas_captura_manual": [f["fila"] for f in filas_cuenta if f["estado"] == "CAPTURA_MANUAL"],
            "fuentes_consulta": sorted(obligatorias),
            "host": host,
            "estado": _estado_cuenta(neto_pmd, host),
        })

    resumen: dict[str, int] = {"cuentas": len(cuentas)}
    for c in cuentas:
        resumen[c["estado"]] = resumen.get(c["estado"], 0) + 1
    advertencias = []
    if otra_fecha:
        advertencias.append(f"{otra_fecha} movimientos Host con fecha distinta a {fecha} no entran en el cuadre (T+0).")
    return {
        **resultado,
        "estado": "CUADRE_CALCULADO",
        "resumen": resumen,
        "cuentas": cuentas,
        "validador": validador(evaluadas, pmd),
        "codigos_pmd_sin_estructura": codigos_pmd_sin_estructura(pmd, {f["codigo_pmd"] for f in filas}),
        "codigos_pmd_cobertura_parcial": codigos_pmd_cobertura_parcial(pmd, evaluadas),
        "movimientos_pmd_sin_cuenta": sin_cuenta,
        "filas_tipo_inconsistente": [f for f in evaluadas if f["tipo_inconsistente"]],
        "advertencias": advertencias,
    }
