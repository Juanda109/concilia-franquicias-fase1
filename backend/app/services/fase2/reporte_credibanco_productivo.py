"""Reporte operativo de conciliacion Credibanco.

Construye una matriz de control a partir de los datos persistidos de F1/F2 y de
la plantilla contable documentada. No aprueba reglas ni inventa escala/signo.
La salida distingue valor de origen, valor Host por fuente y homologacion.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import json

from app.services.fase2.cierre_credibanco_pg_v67 import ejecutar as ejecutar_v67

CATALOGO = Path(__file__).resolve().parents[4] / "catalogo_credibanco_inc44.json"


def _decimal(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _host_neto(row):
    debe = _decimal(row.get("debe")) or Decimal(0)
    haber = _decimal(row.get("haber")) or Decimal(0)
    return debe - haber


def _cargar_catalogo():
    return json.loads(CATALOGO.read_text(encoding="utf-8-sig"))


def _claves_concepto_totales(concepto: str) -> list[str]:
    """Claves exactas y alias funcionales documentados para TOTALES.

    TOTALES agrupa por el concepto persistido de Canje, mientras la matriz
    contable puede conservar un sufijo descriptivo (por ejemplo, PAGOS).
    Solo se elimina ese sufijo cuando la clave base existe realmente en
    TOTALES; no se inventan homologaciones de cuentas ni importes.
    """
    concepto = str(concepto).strip()
    claves = [concepto]
    for sufijo in (" PAGOS", " REVERSIONES"):
        if concepto.endswith(sufijo):
            base = concepto[:-len(sufijo)].strip()
            if base and base not in claves:
                claves.append(base)
    return claves


def _totales_origen_por_concepto(regla, totales):
    concepto = str(regla["concepto"])
    claves = _claves_concepto_totales(concepto)
    coincidencias = [t for t in totales if str(t.get("A") or "").strip() in claves]
    if not coincidencias:
        # Replica la semantica de los VLOOKUP de la plantilla:
        # cuando no existe la clave, el resultado funcional es 0.
        # El cero no implica homologacion ni certificacion.
        return {
            "encontrado": False,
            "cantidad_operaciones": 0,
            "vl_interc": "0.0000",
            "vl_total": "0.0000",
            "unidad_valor_origen": "TOTALES_VLOOKUP_SIN_COINCIDENCIA_CERO",
        }
    t = coincidencias[0]
    return {
        "encontrado": True,
        "cantidad_operaciones": t.get("B"),
        "vl_interc": str(t.get("C")) if t.get("C") is not None else None,
        "vl_total": str(t.get("D")) if t.get("D") is not None else None,
        "unidad_valor_origen": "TOTALES_CANTIDAD_VL_INTERC_VL_TOTAL",
    }


def _valor_desde_totales(regla, totales):
    fila = int(regla["fila"])
    origen = _totales_origen_por_concepto(regla, totales)
    if not origen["encontrado"]:
        # La plantilla devuelve 0 cuando VLOOKUP no encuentra la clave.
        # Mantenerlo como valor diagnostico, nunca como homologacion.
        if fila in (58, 67, 80, 92):
            return "0", "CANTIDAD_OPERACIONES_CERO_SIN_COINCIDENCIA"
        if fila in (60, 69):
            return "0.0000", "IMPORTE_VL_INTERC_CERO_SIN_COINCIDENCIA"
        return None, "REGLA_FILA_NO_SOPORTADA"

    if fila in (58, 67, 80, 92):
        valor = origen["cantidad_operaciones"]
        unidad = "CANTIDAD_OPERACIONES"
    elif fila in (60, 69):
        valor = origen["vl_interc"]
        unidad = "IMPORTE_VL_INTERC"
    else:
        return None, "REGLA_FILA_NO_SOPORTADA"

    if valor is None:
        return None, "IMPORTE_ORIGEN_NULO"
    return str(valor), unidad


def _derivados_depo(grupos: list[dict]) -> dict:
    tasas = []
    conceptos_tii = []
    conceptos_tii_amex = []
    conceptos_comision_atm = []

    for grupo in grupos:
        tasa = _decimal(grupo.get("tasa_intercambio_calculada_cruda"))
        if tasa is not None:
            tasas.append(tasa)

        for campo, destino in (
            ("concepto_tii", conceptos_tii),
            ("concepto_tii_amex", conceptos_tii_amex),
            ("concepto_comision_atm", conceptos_comision_atm),
        ):
            valor = str(grupo.get(campo) or "").strip()
            if valor and valor not in destino:
                destino.append(valor)

    return {
        "tasa_intercambio_calculada_cruda": (
            str(sum(tasas, Decimal(0)))
            if tasas
            else None
        ),
        "conceptos_tii": conceptos_tii,
        "conceptos_tii_amex": conceptos_tii_amex,
        "conceptos_comision_atm": conceptos_comision_atm,
        "certificado": False,
    }

def construir(informe_v67: dict, catalogo: dict | None = None) -> dict:
    if not isinstance(informe_v67, dict):
        raise ValueError("Informe V67 invalido")
    if informe_v67.get("certificado") is not False:
        raise ValueError("El informe V67 debe ser no certificado")

    catalogo = catalogo or _cargar_catalogo()
    reglas = catalogo.get("reglas") or []
    if not isinstance(reglas, list) or not reglas:
        raise ValueError("Catalogo Credibanco sin reglas documentadas")

    totales = informe_v67.get("totales_diagnosticos") or []
    host_grupos = informe_v67.get("host_por_cuenta_y_fuente") or []

    host_por_cuenta = {}
    for h in host_grupos:
        cuenta = str(h.get("cuenta") or "")
        fuente = str(h.get("fuente") or "").upper()
        if not cuenta or fuente not in ("HA22", "HA26", "HA32"):
            continue
        host_por_cuenta.setdefault(cuenta, {})[fuente] = {
            "debe": h.get("debe"),
            "haber": h.get("haber"),
            "neto": str(_host_neto(h)),
            "cantidad": h.get("cantidad"),
            "sinteticos": h.get("sinteticos"),
        }

    filas = []
    for regla in reglas:
        cuenta = str(regla.get("cuenta") or "")
        origen = _totales_origen_por_concepto(regla, totales)
        valor_origen, unidad_origen = _valor_desde_totales(regla, totales)
        hosts = host_por_cuenta.get(cuenta, {})

        filas.append({
            "insumo": "CAET/CANT",
            "regla_contable": None,
            "concepto": regla["concepto"],
            "cuenta": cuenta,
            "fila_plantilla": regla.get("fila"),
            "formula_plantilla": regla.get("formula_F") or regla.get("formula_G"),
            "valor_origen": valor_origen,
            "unidad_origen": unidad_origen,
            "cantidad_operaciones": origen["cantidad_operaciones"],
            "vl_total": origen["vl_total"],
            "vl_interc": origen["vl_interc"],
            "ha22_neto": hosts.get("HA22", {}).get("neto"),
            "ha26_neto": hosts.get("HA26", {}).get("neto"),
            "ha32_neto": hosts.get("HA32", {}).get("neto"),
            "total_host_homologado": None,
            "diferencia_homologada": None,
            "estado_conciliacion": "PENDIENTE_HOMOLOGACION",
            "motivo": "Falta regla aprobada con campo, escala, signo, moneda, fuente Host y tolerancia.",
            "certificable": False,
        })

    depo = informe_v67.get("depo_agregados_crudos") or []
    for concepto, cuenta in (
        ("017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS", "196095001838"),
        ("017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS", "196095001839"),
    ):
        grupos = [d for d in depo if str(d.get("concepto")) == concepto]
        valor_total = None
        valor_intercambio = None
        cantidad = 0
        if grupos:
            vals_total = [_decimal(g.get("valor_total_crudo")) for g in grupos]
            vals_total = [v for v in vals_total if v is not None]
            if vals_total:
                valor_total = str(sum(vals_total, Decimal(0)))
            vals_intercambio = [_decimal(g.get("valor_intercambio_crudo")) for g in grupos]
            vals_intercambio = [v for v in vals_intercambio if v is not None]
            if vals_intercambio:
                valor_intercambio = str(sum(vals_intercambio, Decimal(0)))
            cantidad = sum(int(g.get("cantidad") or 0) for g in grupos)
        hosts = host_por_cuenta.get(cuenta, {})
        derivados = _derivados_depo(grupos)

        filas.append({
            "insumo": "DEPO",
            "regla_contable": cuenta,
            "concepto": concepto,
            "cuenta": cuenta,
            "fila_plantilla": None,
            "formula_plantilla": None,
            "valor_origen": valor_total,
            "unidad_origen": "IMPORTE_VALOR_TOTAL_CRUDO" if valor_total is not None else "SIN_AGREGADO",
            "cantidad_operaciones": cantidad,
            "vl_total": valor_total,
            "vl_interc": valor_intercambio,
            "tasa_intercambio_calculada_cruda": derivados[
                "tasa_intercambio_calculada_cruda"
            ],
            "conceptos_tii": derivados["conceptos_tii"],
            "conceptos_tii_amex": derivados["conceptos_tii_amex"],
            "conceptos_comision_atm": derivados[
                "conceptos_comision_atm"
            ],
            "derivados_certificados": derivados["certificado"],
            "ha22_neto": hosts.get("HA22", {}).get("neto"),
            "ha26_neto": hosts.get("HA26", {}).get("neto"),
            "ha32_neto": hosts.get("HA32", {}).get("neto"),
            "total_host_homologado": None,
            "diferencia_homologada": None,
            "estado_conciliacion": "PENDIENTE_HOMOLOGACION",
            "motivo": "Clasificacion nacional/internacional y homologacion Host pendientes.",
            "certificable": False,
        })

    # DEPO CNBS: origen diagnostico sin cuenta homologada.
    # No se asigna ninguna cuenta Host ficticia.
    cnbs = [
        d for d in depo
        if str(d.get("concepto") or "").strip() == "017-OP CNBS"
    ]

    if cnbs:
        derivados_cnbs = _derivados_depo(cnbs)

        vals_total_cnb = [
            _decimal(d.get("valor_total_crudo"))
            for d in cnbs
        ]
        vals_total_cnb = [
            v for v in vals_total_cnb
            if v is not None
        ]

        vals_interc_cnb = [
            _decimal(d.get("valor_intercambio_crudo"))
            for d in cnbs
        ]
        vals_interc_cnb = [
            v for v in vals_interc_cnb
            if v is not None
        ]

        valor_total_cnb = (
            str(sum(vals_total_cnb, Decimal(0)))
            if vals_total_cnb
            else None
        )

        valor_interc_cnb = (
            str(sum(vals_interc_cnb, Decimal(0)))
            if vals_interc_cnb
            else None
        )

        cantidad_cnb = sum(
            int(d.get("cantidad") or 0)
            for d in cnbs
        )

        filas.append({
            "insumo": "DEPO",
            "regla_contable": None,
            "concepto": "017-OP CNBS",
            "cuenta": None,
            "fila_plantilla": None,
            "formula_plantilla": None,
            "valor_origen": valor_total_cnb,
            "valor_total": valor_total_cnb,
            "unidad_origen": (
                "IMPORTE_VALOR_TOTAL_CRUDO"
                if valor_total_cnb is not None
                else "SIN_AGREGADO"
            ),
            "cantidad_operaciones": cantidad_cnb,
            "vl_total": valor_total_cnb,
            "vl_interc": valor_interc_cnb,
            "tasa_intercambio_calculada_cruda": derivados_cnbs[
                "tasa_intercambio_calculada_cruda"
            ],
            "conceptos_tii": derivados_cnbs["conceptos_tii"],
            "conceptos_tii_amex": derivados_cnbs["conceptos_tii_amex"],
            "conceptos_comision_atm": derivados_cnbs[
                "conceptos_comision_atm"
            ],
            "derivados_certificados": derivados_cnbs["certificado"],
            "ha22_neto": None,
            "ha26_neto": None,
            "ha32_neto": None,
            "total_host_homologado": None,
            "diferencia_homologada": None,
            "estado_conciliacion": "PENDIENTE_HOMOLOGACION",
            "motivo": "Operacion CNBS sin cuenta Host homologada.",
            "certificable": False,
        })
    l3 = informe_v67.get("control_canje_carta", {}).get("L3_comisiones_canje", {})
    l5 = informe_v67.get("control_canje_carta", {}).get("L5_carta_componente_G", {})
    l6 = informe_v67.get("control_canje_carta", {}).get("L6_evidencia", {})
    posicion = informe_v67.get("carta_posicion_neta", {})

    resumen = {
        "cuentas_documentadas": len(filas),
        "cruces_homologados": 0,
        "diferencias_homologadas": 0,
        "pendientes_homologacion": len(filas),
        "l3": l3,
        "l5": l5,
        "l6": l6,
        "posicion_neta_carta": posicion,
    }

    return {
        "id_jornada": informe_v67["id_jornada"],
        "fecha_contable": informe_v67["fecha_contable"],
        "estado": "CONCILIACION_OPERATIVA_PENDIENTE_HOMOLOGACION",
        "certificado": False,
        "columnas": [
            "insumo", "concepto", "cuenta", "valor_origen", "unidad_origen",
            "cantidad_operaciones", "vl_total", "vl_interc",
            "ha22_neto", "ha26_neto", "ha32_neto", "total_host_homologado",
            "diferencia_homologada", "estado_conciliacion", "motivo", "certificable",
        ],
        "filas": filas,
        "resumen": resumen,
        "fuentes_host": informe_v67.get("host_por_cuenta_y_fuente", []),
        "pendientes_reales": informe_v67.get("pendientes", []),
        "reglas_no_aprobadas": [r.get("id_regla") for r in (informe_v67.get("cruces_host_credibanco_diagnosticos") or []) if r.get("estado") != "PENDIENTE_APROBACION_REGLA"],
        "advertencia": "Los valores de origen y Host se exponen para conciliacion operativa; no se convierten en homologacion sin regla aprobada.",
    }


def consultar(id_jornada: int) -> dict:
    return construir(ejecutar_v67(id_jornada))
