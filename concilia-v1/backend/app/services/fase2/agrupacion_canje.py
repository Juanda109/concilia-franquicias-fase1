"""Fase 2 CAET/CANT: agregacion determinista en memoria; sin efectos SQL.

Los importes se reciben en unidades normalizadas por el llamador; NO se
presupone la escala de los enteros presentes en los planos fisicos.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

CAMPOS_IMPORTE = ("vl_total", "vl_interc", "comision_op_exitosas", "tii_recibida")
CLAVES = ("tipo_insumo", "cuenta", "tipo_tarjeta", "canal", "tx")


def _importe(valor, nombre):
    if valor is None or valor == "":
        return Decimal("0")
    if isinstance(valor, bool) or isinstance(valor, float):
        raise ValueError(f"{nombre}: importe debe ser decimal exacto, no float/bool")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{nombre}: importe invalido") from exc
    if not d.is_finite():
        raise ValueError(f"{nombre}: importe no finito")
    return d


def agrupar_canje(movimientos):
    """Devuelve totales, no clasificados y controles; no altera las entradas.

    Contrato de entrada: iterable de dicts con campos logicos normalizados.
    Los TX 'Totales' (registros de control) no suman como transacciones.
    Las filas sin cuenta se reportan aparte para evitar cuadre falso.
    """
    grupos = defaultdict(lambda: {"cantidad": 0, **{k: Decimal("0") for k in CAMPOS_IMPORTE}})
    sin_clasificar = []
    controles = []
    vistos = set()
    total_entradas = 0
    for fila in movimientos:
        total_entradas += 1
        if not isinstance(fila, dict):
            raise ValueError("Cada movimiento debe ser un diccionario")
        tipo = str(fila.get("tipo_insumo", "")).upper().strip()
        if tipo not in ("CAET", "CANT"):
            raise ValueError("tipo_insumo debe ser CAET o CANT")
        archivo = fila.get("id_archivo")
        linea = fila.get("linea_origen")
        if archivo is None or linea is None:
            raise ValueError("Se requieren id_archivo y linea_origen para trazabilidad")
        identidad = (archivo, linea)
        if identidad in vistos:
            raise ValueError(f"Movimiento duplicado: {identidad}")
        vistos.add(identidad)
        tx = str(fila.get("tx", "")).strip()
        if tx == "Totales" or (tx.isdigit() and int(tx) % 2 == 1):
            controles.append({"id_archivo": archivo, "linea_origen": linea, "tx": tx})
            continue
        cuenta = str(fila.get("cuenta", "") or "").strip()
        if not cuenta:
            sin_clasificar.append({"id_archivo": archivo, "linea_origen": linea,
                                   "tx": tx, "motivo": "SIN_CUENTA_F2"})
            continue
        llave = (tipo, cuenta, str(fila.get("tipo_tarjeta", "") or "").strip(),
                 str(fila.get("canal", "") or "").strip(), tx)
        grupo = grupos[llave]
        importes = {campo: _importe(fila.get(campo), campo) for campo in CAMPOS_IMPORTE}
        grupo["cantidad"] += 1
        for campo, importe in importes.items():
            grupo[campo] += importe
    resultados = []
    for llave in sorted(grupos):
        grupo = grupos[llave]
        resultados.append({**dict(zip(CLAVES, llave)), "cantidad": grupo["cantidad"],
                           **{campo: str(grupo[campo]) for campo in CAMPOS_IMPORTE}})
    return {"grupos": resultados, "sin_clasificar": sin_clasificar,
            "controles": controles, "cantidad_entradas": total_entradas,
            "cantidad_agrupada": sum(g["cantidad"] for g in resultados)}
