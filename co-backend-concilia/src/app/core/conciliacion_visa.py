"""Conciliacion VISA: liquidacion internacional de la Plantilla Maestra + controles VSS.

Replica literalmente la fila 5 y las filas 161-181 de la hoja "PLANTILLA (2)" de
Plantilla Maestra.xlsx. En el Excel, la TRM (M169), el total del correo (L169),
el valor del pdf (L170), la TII GOF (L172), las controversias (N179/N180), el
valor de la cuenta 196095001829 (M177) y el valor "carta" (L162) se digitan a
mano; aqui se capturan por pantalla (CON_VISA_CAPTURA_MANUAL) y el resto son las
mismas formulas:

    L171 = L169 + L170              N169 = L169 * M169 * -1
    N170 = L170 * M169 * -1         N171 = L171 * M169 * -1
    N172 = L172 * M169              F5   = N170   (196095001063 VR. COMPENSACION VISA)
    L161 = N170   L163 = L161 + L162   (VALIDACION CANJE INTERNACIONAL: debe ser 0)
    M176 = N171 * -1  M178 = N172  M179 = N179 * M169  M180 = N180 * M169
    M181 = SUM(M176:M180) * -1       (diferencia en cambio: 519095145 d / 411595196 h)

Convencion de la columna M (asiento): positivo = debito, negativo = credito; por
eso M181 lo balancea. El asiento se compara contra Host (debe - haber) por cuenta
y por fuente, sin sumarlas (app.core.host_por_cuenta).

Controles automaticos sin captura: neto VSS-115 (suma del detalle) contra la linea
del PDF International SS de la misma entidad (FUNDS XFER ENTITY = FTSRE), moneda
USD y fechas. El canje internacional (filas 124-208) queda pendiente.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.core.host_por_cuenta import (CERO, FUENTES_HOST, agrupar_host, comparar_fuente, estado_cuenta,
                                      fuentes_por_cuenta, texto)

VERSION_MODELO = "VISA-LIQUIDACION-PLANTILLA-V1"

# Celdas que la Plantilla digita a mano. decimales = maximo admitido.
CAMPOS_CAPTURA: dict[str, dict] = {
    "M169": {"etiqueta": "TRM del correo", "unidad": "COP/USD", "decimales": 4, "requerido": True,
             "plantilla": "M168 'trm correo'"},
    "L170": {"etiqueta": "Valor del pdf", "unidad": "USD", "decimales": 2, "requerido": True,
             "plantilla": "K170 'pdf'"},
    "L169": {"etiqueta": "Total del correo", "unidad": "USD", "decimales": 2, "requerido": False,
             "plantilla": "K169 'total correo'"},
    "L172": {"etiqueta": "TII GOF", "unidad": "USD", "decimales": 2, "requerido": False,
             "plantilla": "K172 'tii gof'"},
    "N179": {"etiqueta": "Controversias (dispute) 1", "unidad": "USD", "decimales": 2, "requerido": False,
             "plantilla": "K179 'CONTROVESIAS (DISPUTE) - 1815'"},
    "N180": {"etiqueta": "Controversias (dispute) 2", "unidad": "USD", "decimales": 2, "requerido": False,
             "plantilla": "K180 'CONTROVESIAS (DISPUTE) - 1815'"},
    "M177": {"etiqueta": "Valor cuenta 196095001829 (h)", "unidad": "COP", "decimales": 2, "requerido": False,
             "plantilla": "K177 '196095001829' L177 'h'"},
    "L162": {"etiqueta": "Valor carta", "unidad": "COP", "decimales": 2, "requerido": False,
             "plantilla": "M162 'carta'"},
}

CUENTA_COMPENSACION = "196095001063"
CUENTA_DIF_CAMBIO_DEBITO = "519095145"
CUENTA_DIF_CAMBIO_CREDITO = "411595196"
# (fila, cuenta, naturaleza en la plantilla, celda M)
LINEAS_ASIENTO = (
    (176, CUENTA_COMPENSACION, "d", "M176"),
    (177, "196095001829", "h", "M177"),
    (178, "411514023", "d", "M178"),
    (179, "196095001815", None, "M179"),
    (180, "196095001815", None, "M180"),
)
CUENTAS_VISA = tuple(sorted({c for _, c, _, _ in LINEAS_ASIENTO}
                            | {CUENTA_DIF_CAMBIO_DEBITO, CUENTA_DIF_CAMBIO_CREDITO}))

_RE_ENTIDAD = re.compile(r"^\s*(\d+)")


class CapturaInvalida(ValueError):
    pass


def _dec(valor: Any) -> Decimal | None:
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def validar_captura(valores: Mapping[str, Any]) -> dict[str, Decimal | None]:
    """Normaliza una captura; None/"" borra el valor del campo. Lanza CapturaInvalida."""
    if not isinstance(valores, Mapping) or not valores:
        raise CapturaInvalida("CAPTURA_VACIA")
    salida: dict[str, Decimal | None] = {}
    for campo, valor in valores.items():
        regla = CAMPOS_CAPTURA.get(campo)
        if regla is None:
            raise CapturaInvalida(f"CAMPO_NO_CAPTURABLE:{campo}")
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            salida[campo] = None
            continue
        if isinstance(valor, (bool, float)):
            raise CapturaInvalida(f"VALOR_INVALIDO:{campo}")  # float pierde precision: se exige texto
        numero = _dec(str(valor).strip().replace(",", ""))
        if numero is None:
            raise CapturaInvalida(f"VALOR_INVALIDO:{campo}")
        if numero.as_tuple().exponent < -regla["decimales"]:
            raise CapturaInvalida(f"DEMASIADOS_DECIMALES:{campo}")
        if campo == "M169" and numero <= 0:
            raise CapturaInvalida("TRM_NO_POSITIVA")
        salida[campo] = numero
    return salida


def _txt(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def entidad(texto_entidad: Any) -> str | None:
    m = _RE_ENTIDAD.match(str(texto_entidad or ""))
    return m.group(1) if m else None


def _con_signo(monto: Any, naturaleza: Any) -> Decimal | None:
    valor = _dec(monto)
    if valor is None:
        return None
    return -valor if str(naturaleza or "").strip().upper() == "DB" else valor


# --------------------------------------------------------------------------- controles VSS / ISS

def resumir_vss(reportes: Sequence[Mapping], detalle: Sequence[Mapping]) -> dict:
    """Neto VSS-115 por reporte (sum credito - sum debito del detalle) y VSS-120 por concepto."""
    por_reporte: dict[Any, list[Mapping]] = {}
    for d in detalle:
        por_reporte.setdefault(d["id_vss_reporte"], []).append(d)
    liquidaciones, conceptos_120 = [], {}
    for r in reportes:
        filas = por_reporte.get(r["id_vss_reporte"], [])
        if r["report_id"] == "VSS-115":
            incompletas = [f for f in filas if _dec(f.get("credit_amount") or 0) is None
                           or _dec(f.get("debit_amount") or 0) is None]
            neto = None if incompletas else sum(
                (_dec(f.get("credit_amount") or 0) - _dec(f.get("debit_amount") or 0) for f in filas), CERO)
            liquidaciones.append({
                "id_archivo": r["id_archivo"], "entidad": entidad(r.get("funds_xfer_entity")),
                "funds_xfer_entity": r.get("funds_xfer_entity"), "reporting_for": r.get("reporting_for"),
                "moneda": r.get("settlement_currency"), "proc_date": _fecha(r.get("proc_date")),
                "lineas": len(filas), "neto": _txt(neto),
                "estado": "DATO_INCOMPLETO" if incompletas else ("SIN_DETALLE" if not filas else "CALCULADO"),
            })
        elif r["report_id"] == "VSS-120":
            for f in filas:
                clave = (f.get("seccion"), f.get("concepto"), f.get("clearing_currency"))
                c = conceptos_120.setdefault(clave, {"seccion": clave[0], "concepto": clave[1],
                                                      "moneda_clearing": clave[2], "lineas": 0,
                                                      "clearing": CERO, "credito": CERO, "debito": CERO})
                c["lineas"] += 1
                c["clearing"] += _con_signo(f.get("clearing_amount") or 0, f.get("naturaleza")) or CERO
                c["credito"] += _dec(f.get("credit_amount") or 0) or CERO
                c["debito"] += _dec(f.get("debit_amount") or 0) or CERO
    vss120 = [{**c, "clearing": str(c["clearing"]), "credito": str(c["credito"]), "debito": str(c["debito"])}
              for c in conceptos_120.values()]
    return {"liquidaciones": liquidaciones, "vss120": vss120}


def _fecha(v: Any) -> str | None:
    return None if v in (None, "") else str(v)


def control_vss_iss(liquidaciones: Sequence[dict], iss_filas: Sequence[Mapping], *, hay_vss: bool,
                    hay_iss: bool) -> list[dict]:
    """Neto VSS-115 de cada entidad contra la(s) linea(s) del PDF International SS con su FTSRE."""
    if not hay_vss or not hay_iss:
        return [{"codigo": "VSS_ISS_NETO", "entidad": None, "vss": None, "iss": None, "diferencia": None,
                 "estado": "INSUMO_FALTANTE",
                 "detalle": ("Falta VSS procesado. " if not hay_vss else "") +
                            ("Falta International SS procesado." if not hay_iss else "")}]
    salida = []
    for liq in liquidaciones:
        lineas = [f for f in iss_filas if str(f.get("ftsre") or "").strip() == liq["entidad"]]
        vss = _dec(liq["neto"])
        if not lineas:
            salida.append({"codigo": "VSS_ISS_NETO", "entidad": liq["entidad"], "vss": liq["neto"], "iss": None,
                           "diferencia": None, "estado": "SIN_LINEA_ISS",
                           "detalle": f"El PDF no trae la FTSRE {liq['entidad']}."})
            continue
        montos = [_con_signo(f.get("monto_neto"), f.get("naturaleza")) for f in lineas]
        iss = None if any(m is None for m in montos) else sum(montos, CERO)
        diferencia = None if vss is None or iss is None else vss - iss
        estado = ("DATO_INCOMPLETO" if diferencia is None
                  else "COINCIDE" if diferencia == 0 else "CON_DIFERENCIA")
        salida.append({"codigo": "VSS_ISS_NETO", "entidad": liq["entidad"], "vss": liq["neto"],
                       "iss": _txt(iss), "diferencia": _txt(diferencia), "estado": estado,
                       "detalle": f"VSS-115 (suma del detalle) vs International SS FTSRE {liq['entidad']}."})
    return salida


def advertencias_documentales(fecha: str, liquidaciones: Sequence[dict], iss_filas: Sequence[Mapping]) -> list[str]:
    avisos = []
    for liq in liquidaciones:
        if liq["moneda"] and liq["moneda"] != "USD":
            avisos.append(f"VSS entidad {liq['entidad']}: moneda de liquidacion {liq['moneda']}, se esperaba USD.")
        if liq["proc_date"] and liq["proc_date"] != fecha:
            avisos.append(f"VSS entidad {liq['entidad']}: PROC DATE {liq['proc_date']} distinta a la jornada {fecha}.")
    for f in iss_filas:
        if f.get("moneda") and str(f["moneda"]).strip() != "USD":
            avisos.append(f"International SS FTSRE {f.get('ftsre')}: moneda {f['moneda']}, se esperaba USD.")
    fechas_iss = sorted({_fecha(f.get("fecha_valor")) for f in iss_filas} - {None})
    if fechas_iss and fechas_iss != [fecha]:
        avisos.append(f"International SS con fecha valor {', '.join(fechas_iss)}; la jornada es {fecha}.")
    return avisos


# --------------------------------------------------------------------------- liquidacion (Plantilla)

def _celda(valor: Decimal | None, formula: str, etiqueta: str, *, captura: bool = False,
           sin_captura: bool = False) -> dict:
    return {"valor": _txt(valor), "formula": formula, "etiqueta": etiqueta,
            "origen": "CAPTURA_MANUAL" if captura else "FORMULA",
            "estado": ("SIN_CAPTURA" if sin_captura else "CALCULADO") if valor is not None or sin_captura
            else "FALTA_TRM"}


def calcular_liquidacion(capturas: Mapping[str, Mapping]) -> dict:
    """Celdas de la Plantilla. Un campo sin capturar vale 0, como la celda vacia en Excel,
    salvo la TRM: sin TRM no se calcula ningun valor en COP."""
    valor = {c: _dec((capturas.get(c) or {}).get("valor")) for c in CAMPOS_CAPTURA}
    falta = [c for c, regla in CAMPOS_CAPTURA.items() if regla["requerido"] and valor[c] is None]
    usd = {c: (valor[c] if valor[c] is not None else CERO) for c in CAMPOS_CAPTURA}
    trm = valor["M169"]

    def cop(f):
        return None if trm is None else f(trm)

    l171 = usd["L169"] + usd["L170"]
    n169 = cop(lambda t: usd["L169"] * t * -1)
    n170 = cop(lambda t: usd["L170"] * t * -1)
    n171 = cop(lambda t: l171 * t * -1)
    n172 = cop(lambda t: usd["L172"] * t)
    m176 = None if n171 is None else n171 * -1
    m177 = usd["M177"]
    m178 = n172
    m179 = cop(lambda t: usd["N179"] * t)
    m180 = cop(lambda t: usd["N180"] * t)
    m181 = (None if None in (m176, m178, m179, m180)
            else (m176 + m177 + m178 + m179 + m180) * -1)
    l161 = n170
    l163 = None if l161 is None else l161 + usd["L162"]

    celdas = {}
    for c, regla in CAMPOS_CAPTURA.items():
        celdas[c] = {"valor": _txt(valor[c]), "formula": "captura manual", "etiqueta": regla["etiqueta"],
                     "unidad": regla["unidad"], "origen": "CAPTURA_MANUAL", "plantilla": regla["plantilla"],
                     "estado": "CAPTURADO" if valor[c] is not None else "SIN_CAPTURA",
                     "version": (capturas.get(c) or {}).get("version"),
                     "usuario": (capturas.get(c) or {}).get("usuario"),
                     "fecha": _fecha((capturas.get(c) or {}).get("fecha"))}
    celdas.update({
        "L171": _celda(l171, "=+L169+L170", "Total USD"),
        "N169": _celda(n169, "=+L169*M169*-1", "Total correo en COP"),
        "N170": _celda(n170, "=+L170*M169*-1", "Pdf en COP"),
        "N171": _celda(n171, "=+L171*M169*-1", "Total en COP"),
        "N172": _celda(n172, "=+L172*M169", "TII GOF en COP"),
        "F5": _celda(n170, "=+N170", "017- VR. COMPENSACION VISA (196095001063, debito)"),
        "L161": _celda(l161, "=+N170", "Validacion canje internacional: cuenta"),
        "L163": _celda(l163, "=+L161+L162", "Validacion canje internacional: diferencia"),
        "M176": _celda(m176, "=+N171*-1", "Asiento 196095001063"),
        "M178": _celda(m178, "=+N172", "Asiento 411514023 TII"),
        "M179": _celda(m179, "=+N179*M169", "Asiento controversias 196095001815"),
        "M180": _celda(m180, "=+(N180*M169)", "Asiento controversias 196095001815"),
        "M181": _celda(m181, "=SUM(M176:M180)*-1", "Diferencia en cambio"),
    })

    asiento = []
    for fila, cuenta, naturaleza, celda in LINEAS_ASIENTO:
        v = {"M176": m176, "M177": m177, "M178": m178, "M179": m179, "M180": m180}[celda]
        asiento.append({"fila": fila, "cuenta": cuenta, "naturaleza_plantilla": naturaleza, "celda": celda,
                        "valor": _txt(v), "naturaleza": None if v is None else ("DEBITO" if v >= 0 else "CREDITO")})
    asiento.append({"fila": 181, "celda": "M181", "naturaleza_plantilla": "d o h",
                    "cuenta": None if m181 is None else (CUENTA_DIF_CAMBIO_DEBITO if m181 >= 0
                                                         else CUENTA_DIF_CAMBIO_CREDITO),
                    "valor": _txt(m181),
                    "naturaleza": None if m181 is None else ("DEBITO" if m181 >= 0 else "CREDITO")})

    validacion = {"codigo": "VALIDACION_CANJE_INTERNACIONAL", "formula": "L163 = L161 + L162",
                  "valor": _txt(l163),
                  "estado": ("FALTA_TRM" if l163 is None else
                             "SIN_CAPTURA_CARTA" if valor["L162"] is None else
                             "CUADRA" if l163 == 0 else "CON_DIFERENCIA")}
    return {"celdas": celdas, "asiento": asiento, "validacion_canje_internacional": validacion,
            "capturas_requeridas_faltantes": falta}


# --------------------------------------------------------------------------- Host

def comparar_asiento_host(asiento: Sequence[dict], *, calculado: bool, host_filas: Sequence[Mapping], fecha: str,
                          fuentes_procesadas: Sequence[str], inventario_host: Sequence[Mapping]) -> tuple[list, int]:
    """Esperado por cuenta = suma del asiento (positivo debito). Cuentas VISA sin linea: esperado 0."""
    esperado: dict[str, Decimal] = {c: CERO for c in CUENTAS_VISA}
    for linea in asiento:
        if linea["cuenta"] and linea["valor"] is not None:
            esperado[linea["cuenta"]] += Decimal(linea["valor"])
    grupos, otra_fecha = agrupar_host(host_filas, fecha)
    procesadas = set(fuentes_procesadas)
    obligatorias = fuentes_por_cuenta(inventario_host)
    cuentas = []
    for cuenta in CUENTAS_VISA:
        valor = esperado[cuenta] if calculado else None
        host = {f: comparar_fuente(valor, f, cuenta, grupos, procesadas, f in obligatorias.get(cuenta, set()))
                for f in FUENTES_HOST}
        cuentas.append({"cuenta": cuenta, "esperado": texto(valor), "fuentes_consulta": sorted(obligatorias.get(cuenta, ())),
                        "host": host, "estado": estado_cuenta(valor, host)})
    return cuentas, otra_fecha


# --------------------------------------------------------------------------- entrada

def construir_conciliacion_visa(*, jornada: Mapping, vss_reportes: Sequence[Mapping], vss_detalle: Sequence[Mapping],
                                iss_filas: Sequence[Mapping], capturas: Mapping[str, Mapping],
                                host_filas: Sequence[Mapping], fuentes_procesadas: Sequence[str],
                                inventario_host: Sequence[Mapping]) -> dict:
    fecha = str(jornada["fecha_contable"])
    vss = resumir_vss(vss_reportes, vss_detalle)
    hay_vss, hay_iss = bool(vss_reportes), bool(iss_filas)
    controles = control_vss_iss(vss["liquidaciones"], iss_filas, hay_vss=hay_vss, hay_iss=hay_iss)
    liquidacion = calcular_liquidacion(capturas)
    calculado = not liquidacion["capturas_requeridas_faltantes"]
    cuentas, otra_fecha = comparar_asiento_host(
        liquidacion["asiento"], calculado=calculado, host_filas=host_filas, fecha=fecha,
        fuentes_procesadas=fuentes_procesadas, inventario_host=inventario_host)

    advertencias = advertencias_documentales(fecha, vss["liquidaciones"], iss_filas)
    if otra_fecha:
        advertencias.append(f"{otra_fecha} movimientos Host con fecha distinta a {fecha} no entran (T+0).")
    if not calculado:
        faltan = ", ".join(f"{c} ({CAMPOS_CAPTURA[c]['etiqueta']})" for c in liquidacion["capturas_requeridas_faltantes"])
        advertencias.append(f"Captura pendiente: {faltan}. Sin ellas no se calcula la liquidacion ni se compara con Host.")

    resumen: dict[str, int] = {"cuentas": len(cuentas)}
    for c in cuentas:
        resumen[c["estado"]] = resumen.get(c["estado"], 0) + 1
    return {
        "id_jornada": jornada["id_jornada"], "fecha_contable": fecha, "modelo": VERSION_MODELO,
        "estado": "LIQUIDACION_CALCULADA" if calculado else "CAPTURA_PENDIENTE",
        "insumos": {"VSS": hay_vss, "ISS": hay_iss, "host": sorted(fuentes_procesadas)},
        "controles": controles,
        "vss": vss,
        "iss": [{"ftsre": f.get("ftsre"), "nombre": f.get("nombre"), "moneda": f.get("moneda"),
                 "monto_neto": _txt(_dec(f.get("monto_neto"))), "naturaleza": f.get("naturaleza"),
                 "fecha_valor": _fecha(f.get("fecha_valor")), "id_archivo": f.get("id_archivo")}
                for f in iss_filas],
        "campos_captura": [{"campo": c, **{k: v for k, v in r.items()}} for c, r in CAMPOS_CAPTURA.items()],
        "liquidacion": liquidacion,
        "resumen": resumen,
        "cuentas": cuentas,
        "pendientes": ["Canje internacional (Plantilla filas 124-208): celdas digitadas por BIN desde VSS-120; "
                       "no se replica en esta version."],
        "advertencias": advertencias,
    }
