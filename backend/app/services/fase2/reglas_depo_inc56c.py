"""INC56-C: evaluacion funcional DEPO sin escrituras ni homologacion monetaria.

No sustituye el filtro de persistencia de Fase 1. Campos crudos y evidencia
se mantienen separados de cuentas, signos y montos certificados.
"""
from __future__ import annotations

MOVIMIENTOS = frozenset({"02", "06", "26", "42"})
CNB_PERMITIDOS = frozenset({"010", "011", "012", "110", "111", "112"})


def _texto(valor):
    return "" if valor is None else str(valor).strip().upper()


def _numero_crudo(valor):
    if valor is None or _texto(valor) == "":
        return None
    s = _texto(valor)
    if s.lstrip("+-").isdigit():
        return int(s)
    return None


def evaluar(row: dict, *, indicador_cnb=None, clasificacion_amex=None) -> dict:
    """Devuelve decision diagnóstica, nunca un asiento contable.

    Los indicadores no se infieren de BIN ni de campos sin correspondencia
    demostrada; deben suministrarse expresamente desde una fuente validada.
    """
    tipo = _texto(row.get("TIPO_MOVIMIENTO"))
    tasa = _numero_crudo(row.get("TASA_DE_INTERCAMBIO"))
    cnb = _texto(indicador_cnb)
    amex = _texto(clasificacion_amex)
    motivos = []
    pendientes = []
    if tipo == "05":
        decision = "NO_PERSISTIR_CONTROL_RESUMEN"
    else:
        if tipo in MOVIMIENTOS:
            motivos.append("TIPO_MOVIMIENTO_PERMITIDO")
        if cnb in CNB_PERMITIDOS:
            motivos.append("INDICADOR_CNB_PERMITIDO")
        elif not cnb:
            pendientes.append("INDICADOR_CNB_SIN_HOMOLOGACION")
        if amex == "AMEX INTERNACIONAL":
            motivos.append("AMEX_INTERNACIONAL")
        elif not amex:
            pendientes.append("CLASIFICACION_AMEX_SIN_HOMOLOGACION")
        if tasa is not None and tasa != 0:
            motivos.append("TASA_INTERCAMBIO_NO_CERO")
        elif tasa is None:
            pendientes.append("TASA_INTERCAMBIO_NO_INTERPRETABLE")
        decision = ("PERSISTIR_REGLA_VERIFICADA" if motivos
                    else "PENDIENTE_EVIDENCIA" if pendientes
                    else "NO_PERSISTIR_SIN_REGLA")
    return {
        "tipo_movimiento": tipo,
        "decision_diagnostica": decision,
        "reglas_activadas": motivos,
        "pendientes": pendientes,
        "indicador_cnb_proporcionado": cnb or None,
        "clasificacion_amex_proporcionada": amex or None,
        "numero_linea": row.get("numero_linea"),
        "cuenta_contable": None,
        "debe": None,
        "haber": None,
        "neto": None,
        "estado_monetario": "NO_HOMOLOGADO",
    }
