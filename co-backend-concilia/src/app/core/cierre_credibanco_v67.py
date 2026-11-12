"""Controles trazables F2 Credibanco sobre F1 persistida, sin dependencias Excel.

CAET/CANT, DEPO, CARTA_COMPENSACION vs HA22/HA26/HA32. Nunca escribe en DB,
ni interpreta cantidades como dinero, ni suma las tres consultas Host.

Los controles exactos se pueden presentar como evidencia pero no certifican una
conciliacion contable: la aprobacion de moneda, escala, naturaleza y fuente
Host por regla no existe en la linea base entregada.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.core.clasificacion_depo_integral import clasificar as clasificar_depo_au

TIPOS = ("CAET", "CANT", "DEPO", "CARTA_COMPENSACION", "HA22", "HA26", "HA32")
FUENTES_HOST = frozenset(("HA22", "HA26", "HA32"))
COMISIONES_L3 = frozenset((
    "017-COMISIONES EXIT. TARJETA DEBITO ONLINE",
    "017-CJE REC VISA NAL VR COM EXIT TC BATC",
))
CONCEPTOS_DEPO = {
    "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS": "196095001838",
    "017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS": "196095001839",
}


def decimal_exacto(v: Any, campo: str, *, admite_nulo: bool = True) -> Decimal | None:
    if v is None or v == "":
        if admite_nulo:
            return None
        raise ValueError(f"{campo}: importe obligatorio ausente")
    if isinstance(v, (float, bool)):
        raise ValueError(f"{campo}: float/bool prohibido; utilizar Decimal")
    try:
        numero = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{campo}: valor no decimal") from exc
    if not numero.is_finite():
        raise ValueError(f"{campo}: importe infinito/NaN")
    return numero


def _entero(v: Any, campo: str) -> int:
    if type(v) is not int or v < 0:
        raise ValueError(f"{campo}: contador invalido")
    return v


def _numero_entero(v: Any, campo: str) -> int:
    if type(v) is not int or v <= 0:
        raise ValueError(f"{campo}: identificador invalido")
    return v


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _resumen_estado(estado: str, **datos: Any) -> dict:
    return {"estado": estado, **datos}


def control_posicion_carta(filas: Sequence[Mapping[str, Any]]) -> dict:
    """Dos controles de reportes diferentes, un unico importe por seccion."""
    resultados = {}
    for seccion in ("CAI0224A", "CAI0228A"):
        candidatos = [f for f in filas if f.get("seccion") == seccion and
                      f.get("motivo_codigo") == "POSICION_NETA" and f.get("es_control") is True]
        if len(candidatos) != 1:
            return _resumen_estado("FALTA_O_DUPLICA_POSICION_NETA", seccion=seccion,
                                   encontrados=len(candidatos), diferencia=None, certificado=False)
        f = candidatos[0]
        if _entero(f.get("cantidad", 0), "cantidad") != 1:
            return _resumen_estado("CONTROL_DUPLICADO", seccion=seccion, diferencia=None, certificado=False)
        n = decimal_exacto(f.get("valor_principal"), "posicion_neta")
        if n is None:
            return _resumen_estado("IMPORTE_NULO", seccion=seccion, diferencia=None, certificado=False)
        resultados[seccion] = n
    diferencia = resultados["CAI0224A"] - resultados["CAI0228A"]
    return _resumen_estado("CUADRA" if diferencia == 0 else "DESCUADRE",
        cai0224a=str(resultados["CAI0224A"]), cai0228a=str(resultados["CAI0228A"]),
        diferencia=str(diferencia), certificado=False,
        aclaracion="Control interno de Carta, no certificacion Host-Franquicia")


def calcular_l3_canje(filas: Sequence[Mapping[str, Any]], archivos_validos: set[int]) -> dict:
    """SUMIF de dos categorias, nunca la columna B/cantidad del pivote."""
    seleccion = []
    for f in filas:
        if _texto(f.get("cuentas_comisiones")) not in COMISIONES_L3:
            continue
        if f.get("id_archivo") not in archivos_validos:
            continue
        tx = _texto(f.get("tx"))
        if tx.casefold() == "totales" or (tx.isdigit() and int(tx) % 2):
            return _resumen_estado("CONTROL_INCLUIDO_EN_COMISIONES", valor=None,
                                   certificado=False)
        if _texto(f.get("cod_error")) != "00":
            return _resumen_estado("COD_ERROR_NO_HOMOLOGADO", valor=None,
                                   certificado=False)
        if _entero(f.get("cantidad", 0), "cantidad") <= 0:
            raise ValueError("Cantidad de comisiones invalida")
        if _entero(f.get("nulos_comision", 0), "nulos_comision"):
            return _resumen_estado("COMISION_INCOMPLETA", valor=None,
                                   certificado=False)
        valor = decimal_exacto(f.get("total_comision"), "total_comision", admite_nulo=False)
        seleccion.append((f, valor))
    if not seleccion:
        return _resumen_estado("SIN_CONCEPTOS_L3", valor=None, grupos=0,
                               certificado=False,
                               aclaracion="Ausencia de conceptos no equivale a cero contable")
    total = sum((n for _, n in seleccion), Decimal(0))
    return _resumen_estado("CALCULADO_SIN_ESCALA_HOMOLOGADA", valor=str(total),
        unidad="UNIDAD_PERSISTIDA_SIN_ESCALA_HOMOLOGADA",
        grupos=len(seleccion),
        archivos=sorted({f["id_archivo"] for f, _ in seleccion}),
        conceptos=sorted({f["cuentas_comisiones"] for f, _ in seleccion}),
        certificado=False)


def calcular_l5_carta(filas: Sequence[Mapping[str, Any]], archivo_id: int | None) -> dict:
    """TOTALES A CARGO / valor_red = columna G; nunca valor_total/columna I."""
    if archivo_id is None:
        return _resumen_estado("SIN_CARTA", valor=None, certificado=False)
    candidatos = [f for f in filas if
        f.get("id_archivo") == archivo_id and
        f.get("seccion") == "CAI0224A" and
        f.get("motivo_codigo") == "TOTAL_CANJE_RECIBIDO" and
        f.get("lado") == "A_CARGO" and f.get("es_control") is True]
    if len(candidatos) != 1:
        return _resumen_estado("FALTA_O_DUPLICA_TOTAL_CARGO", valor=None,
                               encontrados=len(candidatos), certificado=False)
    fila = candidatos[0]
    if _entero(fila.get("cantidad", 0), "cantidad") != 1:
        return _resumen_estado("CONTROL_DUPLICADO", valor=None, certificado=False)
    n = decimal_exacto(fila.get("valor_red"), "valor_red")
    if n is None:
        return _resumen_estado("VALOR_RED_NULO", valor=None, certificado=False)
    return _resumen_estado("CALCULADO_COMPONENTE_G", valor=str(n),
        campo_persistido="valor_red", campo_excel_referencia="CARTA!G",
        id_archivo=archivo_id, unidad="UNIDAD_CARTA_SIN_ESCALA_HOMOLOGADA",
        certificado=False)


def validar_evidencia_l6(
    filas: Sequence[Mapping[str, Any]],
    archivo_id: int | None,
    fecha_contable: str,
) -> dict:
    """Valida la trazabilidad documental de L6 sin aprobarla ni homologar unidades.

    Se exigen exactamente dos registros del mismo archivo y fecha:
    CAI0228A línea 9 como control, y CAI0224A línea 18 como respaldo.
    """
    if archivo_id is None:
        return _resumen_estado("SIN_CARTA_PARA_EVIDENCIA_L6", valor=None, certificado=False)

    especificaciones = (
        {
            "clave": "control_cai0228a",
            "seccion": "CAI0228A",
            "linea": 9,
            "motivo_codigo": "CONCEPTO_CONTROL_CAI228A",
            "es_control": True,
            "lado": "A_FAVOR",
            "concepto": "DEPOSITOS ELECTRONICOS",
            "campo": "valor_principal",
        },
        {
            "clave": "respaldo_cai0224a",
            "seccion": "CAI0224A",
            "linea": 18,
            "motivo_codigo": "CONCEPTO_CANJE_ENVIADO",
            "es_control": False,
            "lado": "A_FAVOR",
            "concepto": "CLASICA BBVA",
            "campo": "valor_depositos_electronicos",
        },
    )

    encontrados: dict[str, dict] = {}
    for spec in especificaciones:
        candidatos = [
            f for f in filas
            if f.get("id_archivo") == archivo_id
            and f.get("seccion") == spec["seccion"]
            and f.get("linea_origen") == spec["linea"]
        ]
        if not candidatos:
            return _resumen_estado(
                "FUENTE_L6_FALTANTE", valor=None,
                fuente_faltante=spec["clave"], certificado=False,
            )
        if len(candidatos) != 1:
            return _resumen_estado(
                "FUENTE_L6_DUPLICADA", valor=None,
                fuente_duplicada=spec["clave"], encontrados=len(candidatos),
                certificado=False,
            )

        fila = candidatos[0]
        if (
            str(fila.get("fecha_contable")) != str(fecha_contable)
            or fila.get("motivo_codigo") != spec["motivo_codigo"]
            or fila.get("es_control") is not spec["es_control"]
            or fila.get("lado") != spec["lado"]
            or fila.get("concepto") != spec["concepto"]
            or not _texto(fila.get("checksum_sha256"))
            or not _texto(fila.get("nombre_archivo"))
        ):
            return _resumen_estado(
                "FUENTE_L6_INCONSISTENTE", valor=None,
                fuente_inconsistente=spec["clave"], certificado=False,
            )

        importe = decimal_exacto(fila.get(spec["campo"]), spec["campo"], admite_nulo=False)
        encontrados[spec["clave"]] = {
            "id_archivo": archivo_id,
            "nombre_archivo": fila["nombre_archivo"],
            "checksum_sha256": fila["checksum_sha256"],
            "fecha_contable": str(fila["fecha_contable"]),
            "linea_origen": spec["linea"],
            "seccion": spec["seccion"],
            "motivo_codigo": spec["motivo_codigo"],
            "concepto": spec["concepto"],
            "campo": spec["campo"],
            "valor": str(importe),
        }

    control = encontrados["control_cai0228a"]
    respaldo = encontrados["respaldo_cai0224a"]
    if control["checksum_sha256"] != respaldo["checksum_sha256"]:
        return _resumen_estado(
            "CHECKSUM_L6_NO_COINCIDE", valor=None, certificado=False,
        )

    valor_control = decimal_exacto(control["valor"], "valor_control_l6", admite_nulo=False)
    valor_respaldo = decimal_exacto(respaldo["valor"], "valor_respaldo_l6", admite_nulo=False)
    diferencia = valor_control - valor_respaldo
    if diferencia != 0:
        return _resumen_estado(
            "IMPORTES_L6_NO_COINCIDEN", valor=None,
            valor_control=str(valor_control), valor_respaldo=str(valor_respaldo),
            diferencia=str(diferencia),
            control=control, respaldo=respaldo, certificado=False,
        )

    return _resumen_estado(
        "EVIDENCIA_L6_COINCIDENTE_PENDIENTE_APROBACION",
        valor=str(valor_control),
        unidad="UNIDAD_CARTA_SIN_ESCALA_HOMOLOGADA",
        diferencia="0",
        fuente_control=control,
        fuente_respaldo=respaldo,
        aprobacion_funcional="PENDIENTE",
        certificado=False,
    )


def control_l8(l3: Mapping[str, Any], l5: Mapping[str, Any], aprobacion: Mapping[str, Any] | None = None) -> dict:
    """Requiere L6 explicito y unidad homologada. Sin aprobacion: NULO."""
    if not aprobacion:
        return _resumen_estado("PENDIENTE_L6_Y_HOMOLOGACION_UNIDADES", l8=None,
                               l3=l3.get("valor"), l5=l5.get("valor"), l6=None,
                               certificado=False)
    # Un diccionario tecnico no sustituye la autorizacion de negocio; este
    # calculo nunca certifica automaticamente un resultado contable.
    if (aprobacion.get("estado") != "APROBADA" or
        not _texto(aprobacion.get("version")) or
        not _texto(aprobacion.get("evidencia")) or
        not _texto(aprobacion.get("moneda")) or
        not _texto(aprobacion.get("fuente_l6"))):
        return _resumen_estado("HOMOLOGACION_NO_APROBADA", l8=None, certificado=False)
    if l3.get("estado") != "CALCULADO_SIN_ESCALA_HOMOLOGADA" or l5.get("estado") != "CALCULADO_COMPONENTE_G":
        return _resumen_estado("COMPONENTES_L3_L5_NO_DISPONIBLES", l8=None,
                               certificado=False)
    esc3 = decimal_exacto(aprobacion.get("escala_canje"), "escala_canje", admite_nulo=False)
    esc5 = decimal_exacto(aprobacion.get("escala_carta"), "escala_carta", admite_nulo=False)
    l6 = decimal_exacto(aprobacion.get("l6"), "l6", admite_nulo=False)
    if esc3 <= 0 or esc5 <= 0:
        raise ValueError("Escalas deben ser positivas")
    v3 = decimal_exacto(l3["valor"], "l3", admite_nulo=False) / esc3
    v5 = decimal_exacto(l5["valor"], "l5", admite_nulo=False) / esc5
    return _resumen_estado("CALCULADO_DIAGNOSTICO_VERSIONADO", l3=str(v3),
        l5=str(v5), l6=str(l6), l8=str(v5-v3-l6), moneda=aprobacion["moneda"],
        version_regla=aprobacion["version"], evidencia=aprobacion["evidencia"],
        certificado=False)


def agrupar_depo(filas: Sequence[Mapping[str, Any]], archivos_validos: set[int]) -> list[dict]:
    """Clasifica con AU sobre campos F1; conserva el concepto persistido.

    La salida es diagnostica: nunca homologa unidades monetarias ni certifica
    una cuenta Host. No altera datos F1 ni reinterpreta campos vacios como hechos.
    """
    resultado = []
    for f in filas:
        if f.get("id_archivo") not in archivos_validos:
            continue
        concepto_persistido = _texto(f.get("concepto"))
        tipo = _texto(f.get("tipo_movimiento"))
        indicador = _texto(f.get("indicador_cash_back"))
        oficina = _texto(f.get("cod_oficina"))
        amex = _texto(f.get("amex_nacional"))
        # Los campos estan presentes en el SELECT del adaptador de este cierre.
        # Para clientes legacy sin dichos campos, mantenemos comportamiento previo.
        if "indicador_cash_back" in f and "cod_oficina" in f:
            concepto_au = clasificar_depo_au(tipo, oficina, indicador, amex)
        else:
            concepto_au = concepto_persistido or "SIN_CLASIFICACION_AU"
        discrepancia = bool(concepto_persistido and concepto_persistido != concepto_au
                            and concepto_au != "CONTROL_RESUMEN_EXCLUIDO")
        concepto = concepto_au if concepto_au not in ("SIN_CLASIFICACION_AU",
                                                    "CONTROL_RESUMEN_EXCLUIDO") else ""
        cantidad = _entero(f.get("cantidad", 0), "cantidad")
        invalidos = _entero(f.get("valores_invalidos", 0), "valores_invalidos")
        nulos_tasa = _entero(f.get("nulos_tasa", 0), "nulos_tasa")
        nulos_intercambio = _entero(f.get("nulos_valor_intercambio", 0), "nulos_valor_intercambio")
        tiene_intercambio = ("valor_intercambio_crudo" in f or "nulos_valor_intercambio" in f)
        crudo = decimal_exacto(f.get("valor_total_crudo"), "valor_total_crudo")
        intercambio = decimal_exacto(f.get("valor_intercambio_crudo"), "valor_intercambio_crudo")
        intercambio_2 = decimal_exacto(f.get("valor_intercambio_2_crudo"), "valor_intercambio_2_crudo")
        tasa = decimal_exacto(f.get("tasa_intercambio_cruda"), "tasa_intercambio_cruda")
        completos = (invalidos == 0 and nulos_tasa == 0 and
                     (not tiene_intercambio or (nulos_intercambio == 0 and intercambio is not None)) and
                     crudo is not None and tasa is not None)
        if tipo == "05":
            estado = "CONTROL_NO_TRANSACCIONAL"
        elif discrepancia:
            estado = "DIVERGENCIA_CONCEPTO_PERSISTIDO_VS_REGLA_AU"
        elif not completos:
            # Compatibilidad con consumidores previos que solo entregan el
            # concepto persistido y no los discriminadores AU del registro.
            estado = ("PENDIENTE_DATOS_ORIGEN" if "indicador_cash_back" in f
                      else "PENDIENTE_CLASIFICACION_O_DATOS")
        elif concepto_au == "SIN_CLASIFICACION_AU":
            estado = "PENDIENTE_CLASIFICACION_AU"
        elif concepto == "017-OP CNBS":
            estado = "CLASIFICADO_CNB_SIN_CUENTA_HOST_HOMOLOGADA"
        elif concepto in CONCEPTOS_DEPO:
            estado = "PENDIENTE_ESCALA_SIGNO_Y_FUENTE_HOST"
        else:
            estado = "CLASIFICADO_AU_SIN_CUENTA_HOST_HOMOLOGADA"
        total_crudo = Decimal(str(crudo)) if crudo is not None else None
        intercambio_crudo = (
            Decimal(str(intercambio))
            if intercambio is not None
            else None
        )

        tasa_calculada = None
        if total_crudo is not None and intercambio_crudo is not None:
            tasa_calculada = (
                total_crudo - intercambio_crudo
            ) * (
                Decimal("-1")
                if tipo == "26"
                else Decimal("1")
            )

        concepto_tii = None
        if amex == "AMEX INTERNACIONAL":
            concepto_tii = (
                "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
            )
        elif oficina == "0090" and tipo in {"02", "06", "26"}:
            concepto_tii = (
                "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
            )
        elif tasa_calculada is not None and tasa_calculada != 0:
            concepto_tii = (
                "017-ASC -CANJE ENVI. ADQUIRENTE- "
                "BINES NAL T. I.-MP TII NAL"
            )

        concepto_tii_amex = None
        if (
            concepto_tii
            == "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
            and amex == "AMEX INTERNACIONAL"
        ):
            concepto_tii_amex = "017-TII AMEX INTERNACIONAL"

        concepto_comision_atm = None
        if tipo in {"02", "42"} and oficina != "0090":
            concepto_comision_atm = (
                "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
            )
        resultado.append({
            "id_archivo": f["id_archivo"], "tipo_movimiento": tipo,
            "concepto": concepto or None,
            "concepto_persistido": concepto_persistido or None,
            "regla_clasificacion": "DEPO-AU-PLANTILLA" if "indicador_cash_back" in f and
                                   "cod_oficina" in f else "LEGACY-CONCEPTO-PERSISTIDO",
            "cod_oficina": oficina or None, "indicador_cnb": indicador or None,
            "amex_nacional": amex or None,
            "cuenta_host_candidata": CONCEPTOS_DEPO.get(concepto) if not discrepancia else None,
            "cantidad": cantidad, "valores_invalidos": invalidos,
            "nulos_tasa": nulos_tasa,
            "nulos_valor_intercambio": nulos_intercambio,
            "valor_total_crudo": str(crudo) if crudo is not None else None,
            "valor_intercambio_crudo": str(intercambio) if intercambio is not None else None,
            "valor_intercambio_2_crudo": str(intercambio_2) if intercambio_2 is not None else None,
            "tasa_intercambio_cruda": str(tasa) if tasa is not None else None,            "tasa_intercambio_calculada_cruda": (
                str(tasa_calculada)
                if tasa_calculada is not None
                else None
            ),
            "concepto_tii": concepto_tii,
            "concepto_tii_amex": concepto_tii_amex,
            "concepto_comision_atm": concepto_comision_atm,
            "unidad": "UNIDAD_CRUDA_SIN_ESCALA_HOMOLOGADA",
            "estado": estado, "certificado": False,
        })
    return resultado


def agrupar_host(filas: Sequence[Mapping[str, Any]], archivos_validos: set[int]) -> list[dict]:
    """No suma HA22, HA26 y HA32. Detecta concepto sintetico explicito."""
    grupos = defaultdict(lambda: {"debe": Decimal(0), "haber": Decimal(0),
                                  "cantidad": 0, "incompletos": 0, "sinteticos": 0,
                                  "fechas": set(), "archivos": set()})
    for f in filas:
        if f.get("id_archivo") not in archivos_validos:
            continue
        fuente = _texto(f.get("tx_host")).upper()
        if fuente not in FUENTES_HOST:
            continue
        cuenta = _texto(f.get("cuenta"))
        centro = _texto(f.get("centro"))
        if centro in ("17", "0017"):
            centro = "0017"
        clave = (cuenta, centro, fuente)
        g = grupos[clave]
        cantidad = _entero(f.get("cantidad", 0), "cantidad")
        g["cantidad"] += cantidad
        g["archivos"].add(f["id_archivo"])
        g["fechas"].add(str(f.get("fecha_contable")))
        g["sinteticos"] += cantidad if any(etiqueta in _texto(f.get("concepto")).upper() for etiqueta in ("PRUEBA SINTETICA", "CONTRAPARTIDA SINTETICA")) else 0
        incompletos = _entero(f.get("incompletos", 0), "incompletos")
        g["incompletos"] += incompletos
        if incompletos == 0:
            g["debe"] += decimal_exacto(f.get("debe"), "debe", admite_nulo=False)
            g["haber"] += decimal_exacto(f.get("haber"), "haber", admite_nulo=False)
    salida = []
    for (cuenta, centro, fuente), v in sorted(grupos.items()):
        if v["sinteticos"]:
            estado = "BLOQUEADO_SINTETICO"
        elif v["incompletos"]:
            estado = "DATO_INCOMPLETO"
        else:
            estado = "PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE"
        salida.append({"cuenta": cuenta, "centro": centro, "fuente": fuente,
            "cantidad": v["cantidad"], "debe": str(v["debe"]) if not v["incompletos"] else None,
            "haber": str(v["haber"]) if not v["incompletos"] else None,
            "neto_debe_menos_haber": str(v["debe"]-v["haber"]) if not v["incompletos"] else None,
            "sinteticos": v["sinteticos"], "archivos": sorted(v["archivos"]),
            "fechas": sorted(v["fechas"]), "estado": estado, "certificado": False})
    return salida


def construir_totales_diagnosticos_canje(filas: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Construye el equivalente operativo de TOTALES desde lo persistido.

    A = concepto persistido, B = cantidad, C = VL INTERC, D = VL TOTAL.
    No lee Excel ni aplica escalas, signos u homologaciones contables.
    """
    grupos: dict[str, dict[str, Any]] = {}
    for fila in filas:
        concepto = _texto(fila.get("cuenta")) or _texto(fila.get("cuentas_comisiones"))
        if not concepto:
            continue
        g = grupos.setdefault(concepto, {
            "cantidad": 0,
            "total_valor": Decimal(0),
            "total_intercambio": Decimal(0),
            "nulos_total": 0,
            "nulos_interc": 0,
            "archivos": set(),
            "insumos": set(),
        })
        g["cantidad"] += _entero(fila.get("cantidad", 0), "cantidad")
        g["archivos"].add(fila.get("id_archivo"))
        g["insumos"].add(_texto(fila.get("tipo_archivo")))
        g["nulos_total"] += _entero(fila.get("nulos_total", 0), "nulos_total")
        g["nulos_interc"] += _entero(fila.get("nulos_interc", 0), "nulos_interc")
        if fila.get("total_valor") is not None:
            g["total_valor"] += decimal_exacto(fila["total_valor"], "total_valor", admite_nulo=False)
        if fila.get("total_intercambio") is not None:
            g["total_intercambio"] += decimal_exacto(fila["total_intercambio"], "total_intercambio", admite_nulo=False)

    salida = []
    for concepto in sorted(grupos):
        g = grupos[concepto]
        salida.append({
            "A": concepto,
            "B": g["cantidad"],
            "C": str(g["total_intercambio"]) if g["nulos_interc"] == 0 else None,
            "D": str(g["total_valor"]) if g["nulos_total"] == 0 else None,
            "nulos_total": g["nulos_total"],
            "nulos_interc": g["nulos_interc"],
            "archivos": sorted(x for x in g["archivos"] if x is not None),
            "insumos": sorted(x for x in g["insumos"] if x),
        })
    return salida


def construir_cierre(*, jornada: Mapping[str, Any], archivos: Sequence[Mapping[str, Any]],
    canje: Sequence[Mapping[str, Any]], depo: Sequence[Mapping[str, Any]],
    carta: Sequence[Mapping[str, Any]], host: Sequence[Mapping[str, Any]],
    evidencia_l6: Sequence[Mapping[str, Any]] = (),
    aprobacion_l8: Mapping[str, Any] | None = None,
    reglas_cruce: Sequence[Mapping[str, Any]] = ()) -> dict:
    """Resultado puro independiente de Excel, base de datos e interfaz."""
    id_jornada = _numero_entero(jornada.get("id_jornada"), "id_jornada")
    fecha = str(jornada["fecha_contable"])
    por_tipo = defaultdict(list)
    for a in archivos:
        tipo = _texto(a.get("tipo_archivo"))
        if tipo not in TIPOS:
            raise ValueError("Tipo de insumo fuera de Credibanco")
        por_tipo[tipo].append(a)
    pendientes = []
    estado_insumos = []
    validos_por_tipo = {}
    for tipo in TIPOS:
        items = por_tipo.get(tipo, [])
        if len(items) != 1:
            estado = "FALTANTE" if not items else "ARCHIVOS_MULTIPLES"
            pendientes.append({"codigo": f"INSUMO_{tipo}_{estado}", "detalle": str(len(items))})
        else:
            a = items[0]
            if (str(a.get("fecha_contable")) != fecha or a.get("estado_archivo") != "PROCESADO" or
                a.get("estado_insumo") != "PROCESADO"):
                estado = "FECHA_O_ESTADO_INCONSISTENTE"
                pendientes.append({"codigo": f"INSUMO_{tipo}_{estado}", "detalle": str(a.get('id_archivo'))})
            else:
                estado = "PROCESADO_FECHA_VALIDADA"
                validos_por_tipo[tipo] = _numero_entero(a["id_archivo"], "id_archivo")
        estado_insumos.append({"insumo": tipo, "cantidad_archivos": len(items), "estado": estado})
    ids_canje = {validos_por_tipo[t] for t in ("CAET", "CANT") if t in validos_por_tipo}
    ids_depo = {validos_por_tipo[t] for t in ("DEPO",) if t in validos_por_tipo}
    ids_host = {validos_por_tipo[t] for t in FUENTES_HOST if t in validos_por_tipo}
    # Verificacion de integridad de F1: nunca cruzar una fila que pertenezca
    # a una fecha o tipo de insumo distinto del archivo aprobado en jornada.
    tipo_por_archivo = {ident: tipo for tipo, ident in validos_por_tipo.items()}
    canje_ok = []
    for f in canje:
        identificador = f.get("id_archivo")
        if identificador not in ids_canje:
            continue
        if (f.get("tipo_archivo") != tipo_por_archivo.get(identificador) or
            (f.get("fecha_contable") is not None and str(f["fecha_contable"]) != fecha)):
            pendientes.append({"codigo": "CANJE_FILA_INCONSISTENTE", "detalle": str(identificador)})
            continue
        canje_ok.append(f)
    depo_ok = []
    for f in depo:
        identificador = f.get("id_archivo")
        if identificador not in ids_depo:
            continue
        if f.get("fecha_contable") is not None and str(f["fecha_contable"]) != fecha:
            pendientes.append({"codigo": "DEPO_FILA_FECHA_INCONSISTENTE", "detalle": str(identificador)})
            continue
        depo_ok.append(f)
    carta_ok = []
    for f in carta:
        identificador = f.get("id_archivo")
        if identificador != validos_por_tipo.get("CARTA_COMPENSACION"):
            continue
        if f.get("fecha_contable") is not None and str(f["fecha_contable"]) != fecha:
            pendientes.append({"codigo": "CARTA_FILA_FECHA_INCONSISTENTE", "detalle": str(identificador)})
            continue
        carta_ok.append(f)
    host_ok = []
    for f in host:
        identificador = f.get("id_archivo")
        if identificador not in ids_host:
            continue
        if _texto(f.get("tx_host")).upper() != tipo_por_archivo[identificador]:
            pendientes.append({"codigo": "HOST_FUENTE_INCONSISTENTE", "detalle": str(identificador)})
            continue
        host_ok.append(f)
    if len(ids_canje) != 2:
        l3 = _resumen_estado("FALTAN_CAET_CANT_PROCESADOS", valor=None, certificado=False)
    else:
        l3 = (calcular_l3_canje(canje_ok, ids_canje) if len(canje_ok) == len([x for x in canje if x.get("id_archivo") in ids_canje])
              else _resumen_estado("CANJE_ORIGEN_INCONSISTENTE", valor=None, certificado=False))
    id_carta = validos_por_tipo.get("CARTA_COMPENSACION")
    filas_carta = [f for f in carta_ok if f.get("id_archivo") == id_carta] if id_carta else []
    posicion = (control_posicion_carta(filas_carta) if id_carta else
                _resumen_estado("FALTA_CARTA", diferencia=None, certificado=False))
    l5 = calcular_l5_carta(filas_carta, id_carta)
    evidencia_l6_resultado = validar_evidencia_l6(evidencia_l6, id_carta, fecha)
    if evidencia_l6_resultado["estado"] != "EVIDENCIA_L6_COINCIDENTE_PENDIENTE_APROBACION":
        pendientes.append({"codigo": "CANJE_L6_EVIDENCIA_NO_VALIDADA",
                           "detalle": evidencia_l6_resultado["estado"]})
    l8 = control_l8(l3, l5, aprobacion_l8)
    control_depo = agrupar_depo(depo_ok, ids_depo)
    movimientos_host = agrupar_host(host_ok, ids_host)
    # La muestra Host disponible en V67 incluye HA32 sin concepto explicito:
    # no inferir procedencia real de un registro por ausencia de etiqueta.
    for g in movimientos_host:
        if g["sinteticos"]:
            pendientes.append({"codigo": "HOST_SINTETICO", "detalle": f"{g['cuenta']} {g['fuente']}"})
    if posicion["estado"] != "CUADRA":
        pendientes.append({"codigo": "CARTA_POSICION_SIN_CUADRE", "detalle": posicion["estado"]})
    if l5["estado"] != "CALCULADO_COMPONENTE_G":
        pendientes.append({"codigo": "CARTA_L5_NO_DISPONIBLE", "detalle": l5["estado"]})
    if l3["estado"] != "CALCULADO_SIN_ESCALA_HOMOLOGADA":
        pendientes.append({"codigo": "CANJE_L3_NO_DISPONIBLE", "detalle": l3["estado"]})
    if l8.get("l8") is None:
        pendientes.append({"codigo": "CANJE_L8_SIN_VALOR_VALIDADO", "detalle": l8["estado"]})
    pendientes.append({"codigo": "DEPO_F1_FILTROS_CNBS_AMEX_PENDIENTES",
                        "detalle": "Parser F1 actual no aplica todas las condiciones 3 y 4 de DEPO-F1-001"})
    pendientes.append({"codigo": "CARTA_SECCIONES_PILOTO_PENDIENTES",
                        "detalle": "Verificar extraccion KAI160/BY483/BY485 observada en reunion 2026-11-03"})
    pendientes.append({"codigo": "HOMOLOGACION_HOST_POR_CUENTA_PENDIENTE",
                        "detalle": "Fuente HA22/HA26/HA32, signo, escala y referencia requieren regla aprobada"})
    if any(_texto(f.get("cod_error")) not in ("", "00") for f in canje_ok):
        pendientes.append({"codigo": "CANJE_COD_ERROR_NO_HOMOLOGADO",
                            "detalle": "No convertir codigo S u otros a 00 de manera automatica"})
    cruces_diagnosticos = evaluar_reglas_cruce(reglas_cruce,
        canje=canje_ok, depo=depo_ok, carta=carta_ok, host=movimientos_host,
        ids_validos=validos_por_tipo)
    for r in cruces_diagnosticos:
        if r["estado"] not in ("COINCIDE_DIAGNOSTICO_NO_CERTIFICADO", "DIFERENCIA_DIAGNOSTICA_NO_CERTIFICADA"):
            pendientes.append({"codigo":"CRUCE_REGLADO_PENDIENTE", "detalle":f"{r['id_regla']}: {r['estado']}"})
    return {"id_jornada": id_jornada, "fecha_contable": fecha,
        "alcance": list(TIPOS), "estado": "CIERRE_FUNCIONAL_PENDIENTE_VALIDACIONES",
        "certificado": False, "ejecucion": "SOLO_LECTURA_SIN_EXCEL",
        "insumos": estado_insumos, "carta_posicion_neta": posicion,
        "control_canje_carta": {"L3_comisiones_canje": l3, "L5_carta_componente_G": l5,
                                "L6_evidencia": evidencia_l6_resultado,
                                "L6_fuente_aprobada": l8.get("l6"), "L8_diferencia": l8},
        "depo_agregados_crudos": control_depo,
        # TOTALES diagnosticos derivados de la persistencia de CAET/CANT.
        # No implica homologacion contable ni certificacion.
        "totales_diagnosticos": construir_totales_diagnosticos_canje(canje_ok),
        "host_por_cuenta_y_fuente": movimientos_host,
        "cruces_host_credibanco_diagnosticos": cruces_diagnosticos,
        "cruces_host_credibanco_certificados": [],
        "pendientes": pendientes,
        "nota": "No se suman las tres fuentes Host ni se certifican importes sin homologacion."}

# F2: comparacion parametrizada por regla de negocio, sin homologacion implícita.
CAMPOS_ORIGEN = {
    "CAET": frozenset(("total_valor", "total_intercambio", "total_comision")),
    "CANT": frozenset(("total_valor", "total_intercambio", "total_comision")),
    "DEPO": frozenset(("valor_total_crudo", "valor_intercambio_crudo", "valor_intercambio_2_crudo", "tasa_intercambio_cruda")),
    "CARTA_COMPENSACION": frozenset(("valor_principal", "valor_red", "valor_total")),
}


def evaluar_reglas_cruce(reglas: Sequence[Mapping[str, Any]], *,
                         canje: Sequence[Mapping[str, Any]],
                         depo: Sequence[Mapping[str, Any]],
                         carta: Sequence[Mapping[str, Any]],
                         host: Sequence[Mapping[str, Any]],
                         ids_validos: Mapping[str, int]) -> list[dict]:
    """Calcula diferencias solo con parametros explícitos aprobados.

    Una coincidencia es diagnostica, no asiento ni certificacion, pues el
    chequeo final exige corroborar moneda/referencia/poblacion original.
    """
    if not isinstance(reglas, (tuple, list)):
        raise ValueError("Reglas deben ser lista versionada")
    salidas=[]
    ids_reglas=set()
    for r in reglas:
        if not isinstance(r, Mapping):
            raise ValueError("Regla invalida")
        idr=_texto(r.get("id_regla"))
        if not idr or idr in ids_reglas:
            raise ValueError("ID de regla vacio o duplicado")
        ids_reglas.add(idr)
        aprobada = (r.get("estado")=="APROBADA" and bool(_texto(r.get("version")))
                    and bool(_texto(r.get("evidencia_aprobacion"))))
        base={"id_regla":idr,"version":r.get("version"),"cuenta_host":r.get("cuenta_host"),
              "insumo":r.get("insumo"),"valor_franquicia":None,"valor_host":None,
              "diferencia":None,"certificado":False,"aprobada":aprobada}
        # A pedido explicito: el calculo se intenta aunque la regla no este
        # formalmente aprobada (sin version/evidencia firmada). "aprobada"
        # viaja en cada salida para que nada aguas abajo confunda un
        # resultado sin aprobar con uno certificado - certificado sigue
        # False siempre, y cruces_host_credibanco_certificados sigue vacio.
        insumo=r.get("insumo")
        campo=r.get("campo_importe")
        if insumo not in CAMPOS_ORIGEN or campo not in CAMPOS_ORIGEN[insumo]:
            salidas.append({**base,"estado":"CAMPO_ORIGEN_NO_PERMITIDO"});continue
        if insumo not in ids_validos or r.get("fuente_host") not in FUENTES_HOST or r["fuente_host"] not in ids_validos:
            salidas.append({**base,"estado":"FUENTES_NO_DISPONIBLES"});continue
        cuenta=_texto(r.get("cuenta_host")); centro=_texto(r.get("centro_host"))
        fuente=r["fuente_host"]
        if not cuenta.isdigit() or not (9<=len(cuenta)<=12) or centro not in ("0017", "17"):
            salidas.append({**base,"estado":"CUENTA_CENTRO_INCORRECTOS"});continue
        if r.get("moneda")!="COP" or r.get("naturaleza_host") not in ("DEBE", "HABER", "DEBE_MENOS_HABER"):
            salidas.append({**base,"estado":"MONEDA_O_NATURALEZA_NO_APROBADA"});continue
        if r.get("factor_signo") not in (-1,1) or isinstance(r.get("factor_signo"),bool):
            salidas.append({**base,"estado":"SIGNO_NO_APROBADO"});continue
        if not isinstance(r.get("fechas_host_validas"),list) or not r["fechas_host_validas"]:
            salidas.append({**base,"estado":"FECHAS_HOST_NO_HOMOLOGADAS"});continue
        if insumo in ("CAET","CANT"):
            tx=_texto(r.get("tx"))
            if not tx:
                salidas.append({**base,"estado":"FILTRO_TX_NO_APROBADO"});continue
            ff=[x for x in canje if x.get("id_archivo")==ids_validos[insumo] and
                _texto(x.get("cuenta") if campo!="total_comision" else x.get("cuentas_comisiones"))==_texto(r.get("concepto")) and
                _texto(x.get("tx"))==tx and _texto(x.get("cod_error"))=="00"]
            nulidad={"total_valor":"nulos_total","total_intercambio":"nulos_interc",
                     "total_comision":"nulos_comision"}[campo]
        elif insumo=="DEPO":
            tx=_texto(r.get("tipo_movimiento"))
            if not tx:
                salidas.append({**base,"estado":"FILTRO_MOVIMIENTO_NO_APROBADO"});continue
            ff=[x for x in depo if x.get("id_archivo")==ids_validos[insumo] and
                _texto(x.get("concepto"))==_texto(r.get("concepto")) and
                _texto(x.get("tipo_movimiento"))==tx]
            nulidad="valores_invalidos" if campo=="valor_total_crudo" else "nulos_tasa"
        else:
            motivo=_texto(r.get("motivo_codigo"))
            if not motivo:
                salidas.append({**base,"estado":"MOTIVO_CARTA_NO_APROBADO"});continue
            ff=[x for x in carta if x.get("id_archivo")==ids_validos[insumo] and
                _texto(x.get("motivo_codigo"))==motivo and
                x.get("es_control") is True and
                _texto(x.get("lado"))==_texto(r.get("lado"))]
            nulidad={"valor_principal":"nulos_principal","valor_red":"nulos_red",
                     "valor_total":"nulos_total"}[campo]
        if not ff:
            salidas.append({**base,"estado":"SIN_MOVIMIENTOS_FRANQUICIA"});continue
        if any(_entero(x.get(nulidad,0),nulidad) for x in ff) or any(x.get(campo) is None for x in ff):
            salidas.append({**base,"estado":"IMPORTES_FRANQUICIA_INCOMPLETOS"});continue
        # El control de Carta es unico: no sumar repetidos.
        if insumo=="CARTA_COMPENSACION" and (len(ff)!=1 or ff[0].get("cantidad")!=1):
            salidas.append({**base,"estado":"CARTA_CONTROL_MULTIPLE"});continue
        origen=sum((decimal_exacto(x[campo],campo,admite_nulo=False) for x in ff),Decimal(0))
        if insumo=="DEPO" and campo=="valor_total_crudo" and origen<0:
            salidas.append({**base,"estado":"CRUDO_DEPO_NEGATIVO"});continue
        hh=[h for h in host if h.get("cuenta")==cuenta and h.get("centro")=="0017" and h.get("fuente")==fuente]
        if len(hh)!=1 or hh[0]["estado"]!="PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE":
            salidas.append({**base,"estado":"HOST_NO_VALIDADO_O_SINTETICO"});continue
        h=hh[0]
        if not set(h["fechas"]).issubset(set(r["fechas_host_validas"])):
            salidas.append({**base,"estado":"FECHA_HOST_NO_COINCIDE"});continue
        escala=decimal_exacto(r.get("escala_origen"),"escala_origen",admite_nulo=False)
        tolerancia=decimal_exacto(r.get("tolerancia"),"tolerancia",admite_nulo=False)
        if escala<=0 or tolerancia<0:
            raise ValueError("Escala/tolerancia fuera de rango")
        total_origen=origen/escala*r["factor_signo"]
        tipo_naturaleza=r["naturaleza_host"]
        if tipo_naturaleza=="DEBE": total_host=decimal_exacto(h["debe"],"debe",admite_nulo=False)
        elif tipo_naturaleza=="HABER": total_host=decimal_exacto(h["haber"],"haber",admite_nulo=False)
        else: total_host=decimal_exacto(h["neto_debe_menos_haber"],"neto_host",admite_nulo=False)
        dif=total_origen-total_host
        salidas.append({**base,"valor_franquicia":str(total_origen),
            "valor_host":str(total_host),"diferencia":str(dif),
            "fuente_host":fuente,"moneda":r["moneda"],
            "archivos_origen":sorted({x["id_archivo"] for x in ff}),
            "archivo_host":h["archivos"],
            "estado":"COINCIDE_DIAGNOSTICO_NO_CERTIFICADO" if abs(dif)<=tolerancia else
                     "DIFERENCIA_DIAGNOSTICA_NO_CERTIFICADA"})
    return salidas
