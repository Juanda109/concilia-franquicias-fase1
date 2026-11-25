"""Plantilla Maestra Credibanco (hoja "PLANTILLA (2)") reproducida desde F1 persistida.

Replica las formulas literales de las filas cuya fuente es la Carta de
Compensacion, la hoja TOTALES (CAET+CANT) o la hoja "td cuadre" (DEPO +
"datos contabilidad", que sale de HA22). El orden de columnas de TOTALES es el
que guarda la cache del vinculo externo de la Plantilla (A=cuenta,
B=suma VL INTERC, C=suma VL TOTAL, E:F comisiones, E:G TII, I:J valores L), no
el de la estructura actual, que tiene una columna de conteo adicional.

Las celdas que en la Plantilla son captura
manual se listan aparte y cuentan como vacias en los subtotales, igual que en
Excel. Cada valor lleva el estado que explica de donde salio.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.core.clasificacion_depo_integral import clasificar as clasificar_depo

CERO = Decimal(0)
# Control de carro ASA en la linea TOTALES de la Carta (" ", "0", "1"): los SUMIF
# de TOTALES A CARGO suman las tres variantes; los de TOTALES A FAVOR solo " ".
VARIANTES_TOTALES = ("", "0", "1")
MULTIPLICADOR_ATM = Decimal(7460)  # td cuadre!O4 = VLOOKUP(N4,G:H,2,0)*7460
TII_INTER = "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
TII_ASC = "017-ASC -CANJE ENVI. ADQUIRENTE- BINES NAL T. I.-MP TII NAL"
TII_AMEX_INT = "017-TII AMEX INTERNACIONAL"
CUENTA_DEPO_NAL = "196095001838"
CUENTA_DEPO_INT = "196095001839"

CALCULADO = "CALCULADO"
_RE_CC = re.compile(r"\[CC=(.)\]")

FILAS_MANUALES = {
    "CUADRE_CANJE_MANUAL": (
        (6, "299095107", "017- PAGOS EFECTUADOS CENTRO 0"),
        (7, "196095001850", "017- CJE ENV AVANCE TC AJENA TF Y MP47 NAL -MP2"),
        (8, "196095001851", "017- CJE ENV DEV AVANC MP47 TC BBVA EN LA RED -MP2"),
        (9, "299095843", "017- VR. COMPENSACION BBVA"),
        (10, "196095001853", "017- CJE ENV REPRESENT MP47 AVANCE TC AJENA OF BBVA -MP2"),
        (11, "196095001854", "017- CJE ENV DEV A ENT ADQUIRENT PGO TC BBVA EN MP47 -MP2"),
        (12, "196095001855", "017- CANJE ENV REV PGOS TC AJENA POR MP47-MP2 COD24"),
        (13, "196095001856", "017- CANJE ENV REPRESENTACIONPGOS POR MP47 -MP2"),
        (14, "196095001847", "017- CANJE ENVIADO AMEX NACIONAL HA32"),
        (15, "196095001857", "017- CANJE ENV VENTAS NAL EN TF Y MP47 HA26"),
        (16, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (17, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (18, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (19, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (20, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (21, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (22, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (23, "196095001859", "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"),
        (24, "196095001860", "017- CJE ENVIADO VISA REV VENTAS 26-MP2"),
        (25, "411514005", "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS"),
        (26, "196095001861", "017- CANJE ENV REPRESENTACION VENTAS 36 -MP2"),
        (27, "196095001864", "017- CJE ENV TX 26 AMEX -MP2"),
        (28, "299095833", "017- CJE ENV REVERSION AVANCE HA26 22"),
        (29, "196095001221", "017- ORIGINAL REEMBOLSO"),
        (30, "299095817", "017- ASC -CANJE ENVI. ADQUIRENTE- BINES NAL T. I.-MP"),
        (31, "196095001847", "017- CANJE ENVIADO AMEX NACIONAL"),
        (32, "196095001848", "017- CANJE ENVIADO AMEX INTERNACIONAL"),
        (33, "196095001814", "017- VR. CANJE ENVIADO AVANCES OTROS BAN"),
        (34, "196095001865", "017- CANJE ENV REPRESENTACION VENTAS 36 -MP2"),
        (35, "299095038", "017-TP 12 DEVO AVANCE"),
        (36, "299095108", "017- ASCR-CNJE ENV.ADQ BNS INTNAL PGOS"),
        (37, "411514003", "017- VR COMISION ADQUIRENCIA"),
    ),
    "CUADRE_CANJE_ELECTRONICO": (
        (43, "196095001221", "017- EXTRACOMPENSACION VISA"),
        (44, "196095001848", "017- VOU AMEX"),
        (45, "299095038", "017- MOV. INCOMING NACIONAL"),
        (46, "411595196", "017- DIF TASA TIPO CAMBIO VISA"),
        (47, "419595025", "017- VR. FINANCIACION POR CANJE ENVIADO"),
        (48, "519095145", "017- DIF TASA DE CAMBIO RED (EXTRACOM)"),
        (49, "511595034", "017- UTILIZACION BINES COBRO VISA INTERN"),
        (51, "411514023", "017-CARGO STANDARD RATE AJUSTE AMEX"),
        (53, "519030011", "017- VR RED, PROCESO CANJE INTERNACIONAL"),
        (54, "196095001839", "DCC ORIGINAL SALE"),
    ),
    "TOTAL_CANJE_RECIBIDO": (
        (63, "299095302", "CANJE RECIBIDO TAR"),
        (64, "411514005", "TII RECIBIDA EMISO"),
        (65, "196095001830", "017-RECH CJE RECIBIDO NAL TC PMPD1322"),
        (76, "299095300", "017-COMISIONES EXIT. TARJETA DEBITO $1800 DIFE CONTA"),
        (77, "196095001814", "017-RECHAZOS CANJE RECIBIDO NACIONAL VTA"),
        (78, "196095001814", "017-RECHAZOS CANJE RECIBIDO NACIONAL PAGO"),
        (86, "511520026", "017-RETIROS ATMS -USO RED - EFIPAGOS-MPP"),
        (88, "411514005", "017- TII CNBS"),
        (91, "299095301", "017-DEBITO CLASSIC-GOLD BBVA"),
    ),
    "TOTAL_DEPOSITOS_ELECTRONICOS": (
        (117, "196095001918", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"),
        (118, "196095001918", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"),
        (119, "196095001918", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"),
        (120, "196095001918", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"),
        (121, "411595191", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"),
    ),
}

Celda = tuple  # (valor: Decimal | None, estado: str)


def _norm(texto: Any) -> str:
    return " ".join(str(texto or "").split()).upper()


def _dec(valor: Any, campo: str) -> Decimal | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (float, bool)):
        raise ValueError(f"{campo}: float/bool prohibido; utilizar Decimal")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{campo}: valor no decimal") from exc
    if not numero.is_finite():
        raise ValueError(f"{campo}: importe infinito/NaN")
    return numero


def _entero(valor: Any) -> int:
    return valor if type(valor) is int and valor >= 0 else 0


def control_impresion(concepto: Any) -> str:
    """Caracter de control ASA que el parser de Carta guarda como "[CC=x]"."""
    m = _RE_CC.search(str(concepto or ""))
    return m.group(1) if m else ""


class _Pivote:
    """Suma por etiqueta, como una tabla dinamica (una celda vacia suma 0).

    Una etiqueta queda incompleta solo si el origen reporta nulos de un campo
    que el parser debia llenar (contadores nulos_*), no por celdas vacias.
    """

    def __init__(self) -> None:
        self.sumas: dict[str, Decimal] = {}
        self.incompletas: set[str] = set()

    def agregar(self, etiqueta: Any, valor: Decimal | None, incompleto: bool = False) -> None:
        clave = _norm(etiqueta)
        if not clave:
            return
        self.sumas.setdefault(clave, CERO)
        if incompleto:
            self.incompletas.add(clave)
        elif valor is not None:
            self.sumas[clave] += valor

    def buscar(self, etiqueta: str) -> Celda:
        clave = _norm(etiqueta)
        if clave in self.incompletas:
            return None, "DATO_INCOMPLETO"
        if clave not in self.sumas:
            return None, "NO_ENCONTRADO"
        return self.sumas[clave], CALCULADO


def _si_na_cero(celda: Celda) -> Celda:
    """IF(ISNA(VLOOKUP(...)),0,VLOOKUP(...))."""
    return (CERO, "SIN_DATO_EXCEL_CERO") if celda[1] == "NO_ENCONTRADO" else celda


def _si_na_vacio(celda: Celda) -> Celda:
    """IF(ISNA(VLOOKUP(...)),"",VLOOKUP(...))."""
    return (None, "SIN_DATO_EXCEL_VACIO") if celda[1] == "NO_ENCONTRADO" else celda


def _directo(celda: Celda) -> Celda:
    """VLOOKUP sin ISNA: si no encuentra, Excel muestra #N/A."""
    return (None, "SIN_DATO_EXCEL_NA") if celda[1] == "NO_ENCONTRADO" else celda


def _op(funcion, *celdas: Celda) -> Celda:
    for valor, estado in celdas:
        if valor is None:
            return None, estado
    valor = funcion(*(v for v, _ in celdas))
    estado = next((e for _, e in celdas if e != CALCULADO), CALCULADO)
    return valor, estado


FIJO_CERO: Celda = (CERO, "VALOR_FIJO_EXCEL")
MANUAL_VACIA: Celda = (CERO, "CELDA_MANUAL_VACIA")


def _faltante(insumo: str) -> Celda:
    return None, f"INSUMO_{insumo}_FALTANTE"


def _fila(fila: int, cuenta: str, concepto: str, *, debito: Celda | None = None,
          credito: Celda | None = None, formula: str, fuente: str, nota: str | None = None) -> dict:
    celdas = [c for c in (debito, credito) if c is not None]
    sin_valor = next((e for v, e in celdas if v is None), None)
    estado = sin_valor or next((e for _, e in celdas if e != CALCULADO), CALCULADO)
    salida = {
        "fila": fila, "cuenta": cuenta, "concepto": concepto,
        "debito": None if debito is None or debito[0] is None else str(debito[0]),
        "credito": None if credito is None or credito[0] is None else str(credito[0]),
        "estado": estado,
        # "" en Excel (SIN_DATO_EXCEL_VACIO) es vacio por diseno: SUM lo ignora.
        "sin_valor": sin_valor is not None and sin_valor != "SIN_DATO_EXCEL_VACIO",
        "formula_excel": formula, "fuente": fuente, }
    if nota:
        salida["nota"] = nota
    return salida


def _bloque(codigo: str, titulo: str, fila_subtotal: int, filas: list[dict]) -> dict:
    debito = sum((Decimal(f["debito"]) for f in filas if f["debito"] is not None), CERO)
    credito = sum((Decimal(f["credito"]) for f in filas if f["credito"] is not None), CERO)
    sin_valor = [f["fila"] for f in filas if f["sin_valor"]]
    calculadas = {f["fila"] for f in filas}
    manuales = [{"fila": n, "cuenta": c, "concepto": t} for n, c, t in FILAS_MANUALES[codigo] if n not in calculadas]
    return {
        "codigo": codigo, "titulo": titulo, "fila_subtotal": fila_subtotal,
        "filas": filas, "filas_captura_manual": manuales,
        "subtotal_debito": str(debito), "subtotal_credito": str(credito),
        "filas_sin_valor": sin_valor,
        "subtotal_completo": not sin_valor,
        "aclaracion": "Subtotal de filas calculables; las de captura manual cuentan como vacias, igual que en Excel.",
        }


# ---------------------------------------------------------------- Carta

def _carta_totales(carta: Sequence[Mapping], lado: str, motivo: str, campo: str,
                   variantes: tuple[str, ...]) -> Celda:
    """SUM de SUMIF(CARTA!B, linea TOTALES con cada control de impresion, columna)."""
    total, encontradas = CERO, 0
    for f in carta:
        if (f.get("motivo_codigo") != motivo or f.get("lado") != lado or f.get("es_control") is not True
                or control_impresion(f.get("concepto")) not in variantes):
            continue
        if _entero(f.get(f"nulos_{campo.removeprefix('valor_')}", 0)):
            return None, "DATO_INCOMPLETO"
        valor = _dec(f.get(campo), campo)
        if valor is None:
            return None, "DATO_INCOMPLETO"
        total += valor
        encontradas += 1
    return (total, CALCULADO) if encontradas else (CERO, "SIN_DATO_EXCEL_CERO")


def _carta_concepto(carta: Sequence[Mapping], prefijo: str) -> Decimal:
    """SUMIF(CARTA!B, prefijo, CARTA!C) sobre reintegros/descuentos de la Carta."""
    clave = _norm(prefijo)
    total = CERO
    for f in carta:
        if f.get("motivo_codigo") in ("REINTEGRO", "DESCUENTO_CARGO") and _norm(f.get("concepto")).startswith(clave):
            valor = _dec(f.get("valor_principal"), "valor_principal")
            total += valor or CERO
    return total


def _signo_carta(carta, prefijo: str, *, invertir: bool) -> tuple[Celda, Celda]:
    """F=IF(s<0, s*k, 0); G=IF(s>0, s*k, 0), con k=-1 si invertir."""
    s = _carta_concepto(carta, prefijo)
    k = Decimal(-1) if invertir else Decimal(1)
    debito = s * k if s < 0 else CERO
    credito = s * k if s > 0 else CERO
    return (debito, CALCULADO), (credito, CALCULADO)


# ------------------------------------------------ Carta: hoja CAI 160 A
# Notas de la columna H del cuadre real ("Se extrae de la carta de
# compensacion hoja CAI160"): el valor es la suma del VALOR TOTAL consolidado
# del codigo de transaccion en todos los BIN. Positivo = debito, negativo =
# credito (asi quedan pagos/reembolsos en F y devoluciones en G, como en el Excel).
SECCION_CAI160 = "CAI0160A"
NOTA_CAI160 = ("Carta hoja CAI 160 A, VALOR TOTAL consolidado. Columna y signo pendientes de validar "
               "contra un cuadre y una Carta del mismo dia.")
CUENTA_DEVOLUCION_VENTAS = "196095001859"
CONCEPTO_DEVOLUCION_VENTAS = "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
FILAS_DEVOLUCION_VENTAS = tuple(range(16, 24))


def _cai160(carta: Sequence[Mapping], codigo: str) -> list[tuple[str, Decimal]]:
    salida = []
    for f in carta:
        if f.get("seccion") != SECCION_CAI160 or f.get("motivo_codigo") != f"CAI160_{codigo}":
            continue
        valor = _dec(f.get("valor_total"), "valor_total")
        if valor:
            salida.append((str(f.get("concepto") or ""), valor))
    return salida


def _por_signo(valor: Decimal) -> dict:
    if valor < 0:
        return {"credito": (-valor, CALCULADO)}
    return {"debito": (valor, CALCULADO)}


def _filas_cai160(carta: Sequence[Mapping] | None) -> list[dict]:
    """Filas 6, 16-23, 26 y 29 del cuadre canje enviado. Si la Carta no trae la
    hoja CAI 160 A, no se generan y quedan como captura manual."""
    if not carta or not any(f.get("seccion") == SECCION_CAI160 for f in carta):
        return []
    formula = "SUM(VALOR TOTAL consolidado, codigo {c}, todos los BIN) de CAI 160 A"
    filas = []
    for fila, cuenta, concepto, codigo in (
        (6, "299095107", "017- PAGOS EFECTUADOS CENTRO 0", "04"),
        (26, "196095001861", "017- CANJE ENV REPRESENTACION VENTAS 36 -MP2", "36"),
        (29, "196095001221", "017- ORIGINAL REEMBOLSO", "08"),
    ):
        total = sum((v for _, v in _cai160(carta, codigo)), CERO)
        filas.append(_fila(fila, cuenta, concepto, **_por_signo(total), formula=formula.format(c=codigo),
                           fuente="CAI160", nota=NOTA_CAI160))
    # Devolucion ventas: el Excel la digita en varias filas (16-23), una por
    # valor; se pone una por BIN con movimiento y lo que no quepa va a la 23.
    devoluciones = _cai160(carta, "16")
    grupos = devoluciones[:len(FILAS_DEVOLUCION_VENTAS) - 1]
    resto = devoluciones[len(FILAS_DEVOLUCION_VENTAS) - 1:]
    if resto:
        grupos.append((f"{len(resto)} BIN adicionales", sum((v for _, v in resto), CERO)))
    for fila, (origen, valor) in zip(FILAS_DEVOLUCION_VENTAS, grupos):
        filas.append(_fila(fila, CUENTA_DEVOLUCION_VENTAS, CONCEPTO_DEVOLUCION_VENTAS, **_por_signo(valor),
                           formula=f"CAI 160 A codigo 16: {origen}", fuente="CAI160", nota=NOTA_CAI160))
    return filas


def _carta_enviado_concepto(carta: Sequence[Mapping], prefijo: str) -> Celda:
    """Valor A FAVOR de un producto del canje enviado de la Carta (hoja 224A)."""
    clave = _norm(prefijo)
    total, encontrado = CERO, False
    for f in carta:
        if f.get("motivo_codigo") == "CONCEPTO_CANJE_ENVIADO" and _norm(f.get("concepto")).startswith(clave):
            valor = _dec(f.get("valor_principal"), "valor_principal")
            if valor is None:
                return None, "DATO_INCOMPLETO"
            total += valor
            encontrado = True
    return (total, CALCULADO) if encontrado else (CERO, "SIN_DATO_EXCEL_CERO")


def _bloques_carta(carta: Sequence[Mapping] | None) -> tuple[dict, dict, dict]:
    hay = carta is not None
    favor = (lambda campo: _carta_totales(carta, "A_FAVOR", "TOTAL_CANJE_ENVIADO", campo, ("",))) if hay else (lambda campo: _faltante("CARTA"))
    sumif = '=SUMIF([1]CARTA!B,"     T O T A L E S   A   F A V O R",[1]CARTA!{c})'
    comision_atm = _carta_enviado_concepto(carta, "COMISION INTEROPERABILI") if hay else _faltante("CARTA")
    manual = [
        *_filas_cai160(carta),
        _fila(9, "299095843", "017- VR. COMPENSACION BBVA", credito=comision_atm, fuente="CARTA",
              formula="Carta 224A: COMISION INTEROPERABILI. ATM (A FAVOR)",
              nota="Nota del cuadre: COMISION INTEROPERABILI. ATM se extrae de la carta de compensacion."),
        _fila(38, "419595021", "017- VR PROCESO CANJE NACIONAL", credito=favor("valor_proceso"),
              formula=sumif.format(c="D"), fuente="CARTA"),
        _fila(39, "519030008", "017- VR. FINANCIACION POR CANJE ENVIADO", credito=favor("valor_financiacion"),
              formula=sumif.format(c="E"), fuente="CARTA"),
        _fila(40, "419595023", "017- VR. CTA FOTOCOPIAS CREDIBANCO", credito=favor("valor_fotocopias"),
              formula=sumif.format(c="F"), fuente="CARTA"),
        _fila(41, "419595022", "017- CTA DE RED CANJE NACIONAL", credito=favor("valor_red"),
              formula=sumif.format(c="G"), fuente="CARTA"),
    ]
    if hay:
        redeban = _signo_carta(carta, "VR A CARGO REDEBA", invertir=True)
        outclear = _signo_carta(carta, "A FAVOR OUTCLEAR", invertir=False)
        doc = _signo_carta(carta, "VR A CARGO DOC DE", invertir=True)
    else:
        redeban = outclear = doc = (_faltante("CARTA"), _faltante("CARTA"))
    electronico = [
        _fila(50, "511595037", "017- VR A CARGO REDEBAN $374 (DOBLE SWCHIT)", debito=redeban[0], credito=redeban[1],
              formula='F=IF(s<0,s*-1,0); G=IF(s>0,s*-1,0); s=SUMIF(CARTA!B,"VR A CARGO REDEBA",CARTA!C)', fuente="CARTA"),
        _fila(52, CUENTA_DEPO_INT, "017- DEPOSITOS ELECTRONICOS AMERICAN EXPRESS", debito=outclear[0], credito=outclear[1],
              formula='F=IF(s<0,s,0); G=IF(s>0,s,0); s=SUMIF(CARTA!B,"A FAVOR OUTCLEAR",CARTA!C)', fuente="CARTA"),
        _fila(55, "519095067", "017- VR. COBRO (DOC DEP )FOTOCO DEP. ELECTR.", debito=doc[0], credito=doc[1],
              formula='F=IF(s<0,s*-1,0); G=IF(s>0,s*-1,0); s=SUMIF(CARTA!B,"VR A CARGO DOC DE",CARTA!C)', fuente="CARTA"),
    ]
    cargo = (lambda campo: _carta_totales(carta, "A_CARGO", "TOTAL_CANJE_RECIBIDO", campo, VARIANTES_TOTALES)) if hay else (lambda campo: _faltante("CARTA"))
    manual.sort(key=lambda f: f["fila"])
    return (_bloque("CUADRE_CANJE_MANUAL", "Cuadre canje manual (enviado)", 42, manual),
            _bloque("CUADRE_CANJE_ELECTRONICO", "Cuadre canje electronico", 56, electronico),
            {"proceso": cargo("valor_proceso"), "financiacion": cargo("valor_financiacion"),
             "principal_favor": (_carta_totales(carta, "A_FAVOR", "TOTAL_CANJE_ENVIADO", "valor_principal", VARIANTES_TOTALES)
                                 if hay else _faltante("CARTA")),
             "total_cargo": cargo("valor_total")})


# ---------------------------------------------------------------- TOTALES (canje)

def _pivotes_canje(canje: Sequence[Mapping]) -> tuple[_Pivote, _Pivote, _Pivote, _Pivote, _Pivote, _Pivote]:
    interc, total, interc_880, total_880, comision, tii = (_Pivote() for _ in range(6))
    for f in canje:
        vi = _dec(f.get("total_intercambio"), "total_intercambio")
        vt = _dec(f.get("total_valor"), "total_valor")
        nulos_i = bool(_entero(f.get("nulos_interc", 0)))
        nulos_t = bool(_entero(f.get("nulos_total", 0)))
        interc.agregar(f.get("cuenta"), vi, nulos_i)
        total.agregar(f.get("cuenta"), vt, nulos_t)
        interc_880.agregar(f.get("cuenta_880"), vi, nulos_i)
        total_880.agregar(f.get("cuenta_880"), vt, nulos_t)
        comision.agregar(f.get("cuentas_comisiones"), _dec(f.get("total_comision"), "total_comision"),
                         bool(_entero(f.get("nulos_comision", 0))))
        tii.agregar(f.get("cuentas_comisiones"), _dec(f.get("total_tii"), "total_tii"),
                    bool(_entero(f.get("nulos_tii", 0))))
    return interc, total, interc_880, total_880, comision, tii


def _bloque_canje_recibido(canje: Sequence[Mapping] | None, carta_cargo: dict,
                           l8: Mapping[str, Any] | None) -> tuple[dict, dict]:
    if canje is None:
        def vl(_columna: int, _concepto: str) -> Celda:
            return _faltante("CAET_CANT")
        def com(_concepto: str) -> Celda:
            return _faltante("CAET_CANT")
        def tii_(_concepto: str) -> Celda:
            return _faltante("CAET_CANT")
    else:
        p_interc, p_total, p_interc_880, p_total_880, p_com, p_tii = _pivotes_canje(canje)

        def vl(columna: int, concepto: str) -> Celda:
            """VLOOKUP(concepto, TOTALES!A:B|A:C, 2|3): columna 2 = VL INTERC, 3 = VL TOTAL.
            A:C abarca tambien la tabla "cuenta 880" (A18:C21) bajo la principal."""
            principal, del_880 = (p_interc, p_interc_880) if columna == 2 else (p_total, p_total_880)
            celda = principal.buscar(concepto)
            return del_880.buscar(concepto) if celda[1] == "NO_ENCONTRADO" else celda

        def com(concepto: str) -> Celda:
            return p_com.buscar(concepto)

        def tii_(concepto: str) -> Celda:
            return p_tii.buscar(concepto)

    def c2(concepto: str) -> Celda:
        return _si_na_cero(vl(2, concepto))

    def c3(concepto: str) -> Celda:
        return _si_na_cero(vl(3, concepto))

    restar = lambda a, b: a - b  # noqa: E731
    sumar = lambda *v: sum(v, CERO)  # noqa: E731

    f57 = _op(sumar, c2("017-CANJE RECIBIDO TARJETA CREDITO"), MANUAL_VACIA, MANUAL_VACIA, MANUAL_VACIA)
    g58 = c2("017-CANJE RECIBIDO TARJETA CREDITO PAGOS")
    g59 = c3("017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL")
    g60 = c3("017-ORIGINAL REEMBOLSOS CREDITO")
    g61 = c2("017-CANJE RECIBIDO TC REVERSION AVANCES 22")
    f62 = c2("017-CANJE RECIBIDO TC REVERSION PAGOS 24")
    f84 = c3("017-CANJE RECIBIDO TARJETA DEBITO REGALO")
    f90 = FIJO_CERO
    f95 = carta_cargo["financiacion"]
    g95 = _op(lambda v: v if v < 0 else CERO, f95)
    g96 = _op(lambda v: -v, g95)

    if l8 and l8.get("l8") is not None:
        cuota_red = (_dec(l8["l8"], "l8"), CALCULADO)
    else:
        cuota_red = (None, "PENDIENTE_APROBACION_L8")
    f97 = _op(restar, cuota_red, MANUAL_VACIA)

    t = "TOTALES"
    filas = [
        _fila(57, "299095302", "017-CANJE RECIBIDO TARJETA CREDITO", debito=f57, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C57,TOTALES!A:B,2,0)+I55),0,VLOOKUP(C57,TOTALES!A:B,2,0)+I55)+G78+G65",
              nota="I55, G78 y G65 son captura manual (rechazos PMPD1322); cuentan como vacias."),
        _fila(58, "299095302", "017-CANJE RECIBIDO TARJETA CREDITO PAGOS", credito=g58, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C58,TOTALES!A:B,2,0)),0,VLOOKUP(C58,TOTALES!A:B,2,0))"),
        _fila(59, "299095302", "017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL", credito=g59,
              fuente=t, formula="=IF(ISNA(VLOOKUP(C59,TOTALES!A:C,3,0)),0,VLOOKUP(C59,TOTALES!A:C,3,0))"),
        _fila(60, "299095302", "017-ORIGINAL REEMBOLSOS CREDITO", credito=g60, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C60,TOTALES!A:C,3,0)),0,VLOOKUP(C60,TOTALES!A:C,3,0))"),
        _fila(61, "299095302", "017-CANJE RECIBIDO TC REVERSION AVANCES 22", credito=g61, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C61,TOTALES!A:B,2,0)),0,VLOOKUP(C61,TOTALES!A:B,2,0))"),
        _fila(62, "299095302", "017-CANJE RECIBIDO TC REVERSION PAGOS 24", debito=f62, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C62,TOTALES!A:B,2,0)),0,VLOOKUP(C62,TOTALES!A:B,2,0))"),
        _fila(66, "299095301", "017-CANJE RECIBIDO TARJETA DEBITO", debito=c2("017-CANJE RECIBIDO TARJETA DEBITO"),
              credito=f84, fuente=t, formula="F=VLOOKUP(C66,TOTALES!A:B,2,0) (0 si #N/A); G=+F84"),
        _fila(67, "299095301", "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES",
              credito=c2("017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C67,TOTALES!A:B,2,0)),0,VLOOKUP(C67,TOTALES!A:B,2,0))"),
        _fila(68, "299095301", "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS",
              debito=c2("017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C68,TOTALES!A:B,2,0)),0,VLOOKUP(C68,TOTALES!A:B,2,0))"),
        _fila(69, "299095301", "017-ORIGINAL REEMBOLSOS DEBITO", credito=c3("017-ORIGINAL REEMBOLSOS DEBITO"),
              fuente=t, formula="=IF(ISNA(VLOOKUP(C69,TOTALES!A:C,3,0)),0,VLOOKUP(C69,TOTALES!A:C,3,0))"),
        _fila(70, "196095001770", "017-OP CNBS", debito=FIJO_CERO, fuente="FIJO", formula="0"),
        _fila(71, "196095001813", "017-NOTAS DEBITO CANJE RECIBIDO",
              debito=c2("017-NOTAS DEBITO CANJE RECIBIDO"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C71,TOTALES!A:B,2,0)),0,VLOOKUP(C71,TOTALES!A:B,2,0))"),
        _fila(72, "259095170", "017-VISA PAGOS", debito=(None, "FUENTE_NO_DISPONIBLE_EN_ESTRUCTURA"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C72,TOTALES!I:J,2,0)),0,VLOOKUP(C72,TOTALES!I:J,2,0))",
              nota="TOTALES!J17 (\"017-VISA PAGOS\") no tiene formula en la estructura entregada."),
        _fila(73, "259095341", "017-CANJE UTILIZACION VISA VALE",
              debito=c2("017-CANJE  UTILIZACION VISA VALE"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C73,TOTALES!A:B,2,0)),0,VLOOKUP(C73,TOTALES!A:B,2,0))"),
        _fila(74, "299095013", "017-ORIGINAL PAGOS A TARJETAS DEBITO",
              credito=c2("017-ORIGINAL PAGOS A TARJETAS DEBITO"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C74,TOTALES!A:B,2,0)),0,VLOOKUP(C74,TOTALES!A:B,2,0))"),
        _fila(75, "299095300", "017-COMISIONES EXIT. TARJETA DEBITO ONLINE",
              debito=_si_na_cero(com("017-COMISIONES EXIT. TARJETA DEBITO ONLINE")), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C75,TOTALES!E:F,2,0)),0,VLOOKUP(C75,TOTALES!E:F,2,0))"),
        _fila(79, "196095001813", "017-DEVOLUCION VTA NAL", debito=c3("017-DEVOLUCION VTA NAL"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C79,TOTALES!A:C,3,0)),0,VLOOKUP(C79,TOTALES!A:C,3,0))"),
        _fila(80, "299095038", "017-REPRESENTACION VENTA NAL (CENTRO 730)",
              debito=c2("017-REPRESENTACION  VENTA NAL (CENTRO 730)"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C80,TOTALES!A:B,2,0)),0,VLOOKUP(C80,TOTALES!A:B,2,0))"),
        _fila(81, "411514023", "017-T.I CONTRACARGOS ADQ", debito=c2("017-T.I CONTRACARGOS ADQ"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C81,TOTALES!A:B,2,0)),0,VLOOKUP(C81,TOTALES!A:B,2,0))"),
        _fila(82, "299095038", "017-SOLICITUD COPIAS", debito=c2("017-SOLICITUD COPIAS"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C82,TOTALES!A:C,2,0)),0,VLOOKUP(C82,TOTALES!A:C,2,0))"),
        _fila(83, "299095843", "017-CJE REC VISA NAL VR COM EXIT TC BATC",
              debito=_si_na_vacio(com("017-CJE REC VISA NAL VR COM EXIT TC BATC")), fuente=t,
              formula='=IF(ISNA(VLOOKUP(C83,TOTALES!E:F,2,0)),"",VLOOKUP(C83,TOTALES!E:F,2,0))'),
        _fila(84, "299095880", "017-CANJE RECIBIDO TARJETA DEBITO REGALO", debito=f84, fuente=t,
              formula="=IF(ISNA(VLOOKUP(C84,TOTALES!A:C,3,0)),0,VLOOKUP(C84,TOTALES!A:C,3,0))"),
        _fila(85, "299095880", "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO",
              credito=c3("017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C85,TOTALES!A:C,3,0)),0,VLOOKUP(C85,TOTALES!A:C,3,0))"),
        _fila(87, "299095303", "017-CJE REC VISA NAL VR COMIS", credito=c2("017-CJE REC VISA NAL VR COMIS"),
              fuente=t, formula="=IF(ISNA(VLOOKUP(C87,TOTALES!A:B,2,0)),0,VLOOKUP(C87,TOTALES!A:B,2,0))"),
        _fila(89, "411514005", "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS",
              debito=_si_na_vacio(tii_("017-TII RECIBIDA EMISOR VISA OP REVER VENTAS")), fuente=t,
              formula='=IF(ISNA(VLOOKUP(C89,TOTALES!E:G,3,0)),"",VLOOKUP(C89,TOTALES!E:G,3,0))'),
        _fila(90, "299095839", "017-COMISIONES NO EXITOSAS TD Y TC (CMI)", debito=f90, fuente="FIJO", formula="0"),
        _fila(92, "299095843", "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO",
              debito=_op(restar, c2("017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO"), f90), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C92,TOTALES!A:B,2,0)),0,VLOOKUP(C92,TOTALES!A:B,2,0)-F90)"),
        _fila(93, "299095843", "017-COMISIONES NO EXITOSAS TD Y TC TIPO 15 Y 16",
              debito=c2("017-COMISIONES NO EXITOSAS TD Y TC  TIPO 15 Y 16"), fuente=t,
              formula="=IF(ISNA(VLOOKUP(C93,TOTALES!A:B,2,0)),0,VLOOKUP(C93,TOTALES!A:B,2,0))"),
        _fila(94, "519030009", "017-CUOTA DE PROCESO CANJE NAL", debito=carta_cargo["proceso"], fuente="CARTA",
              formula='=SUM(SUMIF(CARTA!B,"0|" "|1 T O T A L E S A C A R G O",CARTA!D))'),
        _fila(95, "519030008", "017-CUOTA DE FINANCIACION CANJE NAL", debito=f95, credito=g95, fuente="CARTA",
              formula='F=SUM(SUMIF(CARTA!B,"0|" "|1 T O T A L E S A C A R G O",CARTA!E)); G=IF(F95<0,F95*1,0)'),
        _fila(96, "419595025", "017- VR. FINANCIACION POR CANJE ENVIADO", credito=g96, fuente="CARTA",
              formula="=-G95"),
        _fila(97, "519030010", "017-CUOTA RED CANJE NACIONAL", debito=f97, fuente=t,
              formula="=VLOOKUP(C97,TOTALES!I:J,2,0)-F87  (TOTALES!J8 = L8 = L5-L3-L6)",
              nota="Depende de L8, bloqueado hasta aprobar L6 y escalas (ver control_l8)."),
    ]
    por_fila = {f["fila"]: f for f in filas}

    def valor(n: int, lado: str) -> Celda:
        f = por_fila[n]
        v = f[lado]
        return (Decimal(v), CALCULADO) if v is not None else (None, f["estado"])

    i57 = _op(lambda a, b, c, d, e, g: a - b - c - d - e + g, valor(57, "debito"), valor(58, "credito"),
              valor(59, "credito"), valor(61, "credito"), valor(60, "credito"), valor(62, "debito"))
    i85 = _op(restar, valor(70, "debito"), (CERO, CALCULADO))  # - G102 (literal 0 en depositos)
    controles = {
        "I57_CUENTA_302": {"valor": None if i57[0] is None else str(i57[0]), "estado": i57[1],
                           "formula_excel": "=+F57-G58-G59-G61-G60+F62",
                           "nota": "Plantilla: 'VALI CTA 302 HA 32' (se valida contra HA32)."},
        "I85_OP_CNBS": {"valor": None if i85[0] is None else str(i85[0]), "estado": i85[1],
                        "formula_excel": "=+F70-G102", "nota": "Plantilla: 'SIEMPRE CERO AL TERMINAR EL CUADRE'."},
    }
    return _bloque("TOTAL_CANJE_RECIBIDO", "Total canje recibido", 98, filas), controles


# ---------------------------------------------------------------- td cuadre (DEPO)

def _host(movimientos_host: Sequence[Mapping] | None, cuenta: str, campo: str) -> Celda:
    """'datos contabilidad'!D = SUMIFS(valor, cuenta, naturaleza) sobre HA22 centro 17."""
    if movimientos_host is None:
        return _faltante("HA22")
    grupos = [h for h in movimientos_host
              if h.get("cuenta") == cuenta and h.get("centro") == "0017" and h.get("fuente") == "HA22"]
    if not grupos:
        return CERO, "SIN_MOVIMIENTO_HOST_SUMIFS_CERO"
    total = CERO
    for h in grupos:
        if h.get("estado") != "PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE" or h.get(campo) is None:
            return None, "HOST_NO_VALIDADO_O_SINTETICO"
        total += _dec(h[campo], campo)
    return total, CALCULADO


def _bloque_depositos(depo: Sequence[Mapping] | None, movimientos_host: Sequence[Mapping] | None) -> tuple[dict, dict]:
    if depo is None:
        def total(_c: str) -> Celda:
            return _faltante("DEPO")
        def tasa(_c: str) -> Celda:
            return _faltante("DEPO")
        atm: Celda = _faltante("DEPO")
    else:
        p_total, p_tasa = _Pivote(), _Pivote()
        cantidad_atm = 0
        for f in depo:
            tipo = str(f.get("tipo_movimiento") or "").strip()
            oficina = str(f.get("cod_oficina") or "").strip()
            amex = str(f.get("amex_nacional") or "").strip().upper()
            concepto = clasificar_depo(tipo, oficina, f.get("indicador_cash_back"), amex)
            if concepto not in ("CONTROL_RESUMEN_EXCLUIDO", "SIN_CLASIFICACION_AU"):
                p_total.agregar(concepto, _dec(f.get("valor_total_crudo"), "valor_total_crudo"),
                                bool(_entero(f.get("valores_invalidos", 0))))
            valor_tasa = _dec(f.get("tasa_intercambio_cruda"), "tasa_intercambio_cruda")
            tasa_incompleta = bool(_entero(f.get("nulos_tasa", 0)))
            # Columna TII: INTER si AMEX internacional, u oficina 0090 en tx 02/06/26;
            # si no, ASC solo cuando la tasa es distinta de cero.
            inter = amex == "AMEX INTERNACIONAL" or (oficina == "0090" and tipo in ("02", "06", "26"))
            if inter:
                p_tasa.agregar(TII_INTER, valor_tasa, tasa_incompleta)
            elif tasa_incompleta or valor_tasa is None or valor_tasa != 0:
                p_tasa.agregar(TII_ASC, valor_tasa, tasa_incompleta)
            if amex == "AMEX INTERNACIONAL":
                p_tasa.agregar(TII_AMEX_INT, valor_tasa, tasa_incompleta)
            if tipo in ("02", "42") and oficina != "0090":
                cantidad_atm += _entero(f.get("cantidad", 0))

        def total(c: str) -> Celda:
            return p_total.buscar(c)

        def tasa(c: str) -> Celda:
            return p_tasa.buscar(c)

        atm = ((Decimal(cantidad_atm) * MULTIPLICADOR_ATM, CALCULADO) if cantidad_atm
               else (None, "SIN_DATO_EXCEL_NA"))

    restar = lambda a, b: a - b  # noqa: E731
    debe_nal, haber_nal = _host(movimientos_host, CUENTA_DEPO_NAL, "debe"), _host(movimientos_host, CUENTA_DEPO_NAL, "haber")
    debe_int, haber_int = _host(movimientos_host, CUENTA_DEPO_INT, "debe"), _host(movimientos_host, CUENTA_DEPO_INT, "haber")

    def rechazo(concepto: str, host: Celda) -> Celda:
        """td cuadre!O5..O9 = IF(ISNA(VLOOKUP(concepto,A:B,2,0)-contab),0,VLOOKUP(...)-contab)."""
        base = total(concepto)
        if base[1] == "NO_ENCONTRADO":
            return CERO, "SIN_DATO_EXCEL_CERO"
        return _op(restar, base, host)

    g103 = rechazo("017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS", debe_nal)
    g104 = rechazo("017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS", debe_int)
    f105 = rechazo("017-VR. REVERSIONES D.E. NACIONAL", haber_nal)
    f106 = rechazo("017-VR. REVERSIONES D.E. INTERNACIONAL", haber_int)
    f101 = _op(restar, _si_na_cero(total("017-VR. REVERSIONES D.E. NACIONAL")), f105)
    f112 = _directo(tasa(TII_ASC))
    f113 = _directo(tasa(TII_INTER))
    g115 = _directo(tasa(TII_AMEX_INT))
    h113 = _op(restar, MANUAL_VACIA, MANUAL_VACIA)  # =+I114-H114
    f111 = _op(restar, h113, f112)
    g114 = _op(restar, f113, g115)
    td = "TD_CUADRE"
    filas = [
        _fila(100, CUENTA_DEPO_NAL, "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS", credito=debe_nal, fuente="HA22",
              formula="=VLOOKUP(C100,'td cuadre'!N:O,2,0)  (td cuadre!O7 = 'datos contabilidad'!D2)",
              nota="Debe de la cuenta 196095001838 en HA22 (centro 17)."),
        _fila(101, CUENTA_DEPO_NAL, "017-VR. REVERSIONES D.E. NACIONAL", debito=f101, fuente=td,
              formula="=IF(ISNA(VLOOKUP(C101,'td cuadre'!A:B,2,0)),0,VLOOKUP(C101,'td cuadre'!A:B,2,0))-F105"),
        _fila(102, "196095001770", "017-OP CNBS", credito=FIJO_CERO, fuente="FIJO", formula="0"),
        _fila(103, "299095037", "017-RECHAZOS DEPOSITOS ELECTRONICOS NAL", credito=g103, fuente=td,
              formula="td cuadre!O5 = VLOOKUP(\"...NAL CONSIGNADOS\",A:B,2,0) - contab D2 (0 si #N/A)"),
        _fila(104, "299095037", "017-RECHAZOS DEPOSITOS ELECTRONICOS INT", credito=g104, fuente=td,
              formula="td cuadre!O6 = VLOOKUP(\"...INTERNACIONAL CONSIGNADOS\",A:B,2,0) - contab D4 (0 si #N/A)"),
        _fila(105, "299095037", "017-RECHAZOS DEPOSITOS ELECTRONICOS NAL 26", debito=f105, fuente=td,
              formula="td cuadre!O8 = VLOOKUP(\"...REVERSIONES D.E. NACIONAL\",A:B,2,0) - contab D3 (0 si #N/A)"),
        _fila(106, "299095037", "017-RECHAZOS DEPOSITOS ELECTRONICOS INT 26", debito=f106, fuente=td,
              formula="td cuadre!O9 = VLOOKUP(\"...REVERSIONES D.E. INTERNACIONAL\",A:B,2,0) - contab D5 (0 si #N/A)"),
        _fila(107, CUENTA_DEPO_INT, "017-VR. REVERSIONES D.E. INTERNACIONAL", debito=g104, credito=f106, fuente=td,
              formula="F=+G104; G=+F106"),
        _fila(108, "196095001884", "017-VR. RET ATMs ADQUIRIENTES EN BBV NAL",
              credito=_directo(total("017-VR. RET ATMs ADQUIRIENTES EN  BBV NAL")), fuente=td,
              formula="=VLOOKUP(C108,'td cuadre'!A:B,2,0)"),
        _fila(110, "411514023", "017-ASC - T. I.-MP TII NAL RECHAZOS", debito=MANUAL_VACIA, credito=f111, fuente=td,
              formula="F=+G111; G=+F111"),
        _fila(111, "299095882", "017-ASC - T. I.-MP TII NAL RECHAZOS", debito=f111, fuente=td,
              formula="=+H113-F112  (H113 = I114-H114, celdas manuales)"),
        _fila(112, "299095882", TII_ASC, debito=f112, fuente=td, formula="=VLOOKUP(C112,'td cuadre'!D:E,2,0)"),
        _fila(113, "299095888", TII_INTER, debito=f113, fuente=td, formula="=VLOOKUP(C113,'td cuadre'!D:E,2,0)"),
        _fila(114, "411514023", "017- VR RED, PROCESO CANJE INTERNACIONAL", credito=g114, fuente=td,
              formula="=+F113-G115"),
        _fila(115, CUENTA_DEPO_INT, TII_AMEX_INT, credito=g115, fuente=td,
              formula="=VLOOKUP(C115,'td cuadre'!D:E,2,0)  (tabla de TII 5130 en D20:E23)"),
        _fila(116, "196095001918", "017-VR. COMISIONES ADQ EN ATMs BBV $3.088", credito=atm, fuente=td,
              formula="td cuadre!O4 = VLOOKUP(N4,G:H,2,0)*7460  (cantidad de retiros ATM x 7460)"),
    ]
    contabilidad = {
        "cuenta_838_debe": None if debe_nal[0] is None else str(debe_nal[0]),
        "cuenta_838_haber": None if haber_nal[0] is None else str(haber_nal[0]),
        "cuenta_839_debe": None if debe_int[0] is None else str(debe_int[0]),
        "cuenta_839_haber": None if haber_int[0] is None else str(haber_int[0]),
        "fuente": "HA22, centro 17 (hoja 'datos contabilidad')",
    }
    return _bloque("TOTAL_DEPOSITOS_ELECTRONICOS", "Total depositos electronicos", 122, filas), contabilidad


# ---------------------------------------------------------------- ensamblado

def _valor(celda: Celda) -> str | None:
    return None if celda[0] is None else str(celda[0])


def construir_plantilla_maestra(*, carta: Sequence[Mapping] | None, canje: Sequence[Mapping] | None,
                                depo: Sequence[Mapping] | None, movimientos_host: Sequence[Mapping] | None,
                                l8: Mapping[str, Any] | None = None) -> dict:
    """Cada fuente en None significa insumo no procesado para la jornada."""
    manual, electronico, carta_cargo = _bloques_carta(carta)
    recibido, controles_recibido = _bloque_canje_recibido(canje, carta_cargo, l8)
    depositos, contabilidad = _bloque_depositos(depo, movimientos_host)
    bloques = [manual, electronico, recibido, depositos]

    def sub(bloque: dict, lado: str) -> Decimal:
        return Decimal(bloque[f"subtotal_{lado}"])

    # H40 = F42 - G42 + G38 + G39 + G40 + G41: solo se devuelven los creditos de
    # las filas 38-41 (cuotas de la Carta), no los de pagos/devoluciones (CAI160).
    h40 = sub(manual, "debito") - sub(manual, "credito") + sum(
        (Decimal(f["credito"]) for f in manual["filas"] if f["credito"] is not None and 38 <= f["fila"] <= 41), CERO)
    i40 = carta_cargo["principal_favor"]
    j40 = _op(lambda a, b: a + b, (h40, CALCULADO), i40)
    h90 = sub(recibido, "debito") - sub(recibido, "credito")
    i90 = carta_cargo["total_cargo"]
    j90 = _op(lambda a, b: a - b, (h90, CALCULADO), i90)
    h103 = sub(depositos, "debito") - sub(depositos, "credito")

    controles = {
        "J40_VALIDACION_CANJE_ENVIADO": {
            "h40": str(h40), "i40": _valor(i40), "valor": _valor(j40), "estado": j40[1],
            "formula_excel": "H40=+F42-G42+G38+G39+G40+G41; I40=SUM(SUMIF(TOTALES A FAVOR 0|' '|1, CARTA!C)); J40=+H40+I40"},
        **controles_recibido,
        "J90_VALIDACION_CANJE_RECIBIDO_CARTA": {
            "h90": str(h90), "i90": _valor(i90), "valor": _valor(j90), "estado": j90[1],
            "formula_excel": "H90=+F98-G98; I90=SUM(SUMIF(TOTALES A CARGO 0|' '|1, CARTA!I)); J90=+H90-I90"},
        "H103_VALIDACION_DEPOSITOS": {"valor": str(h103), "estado": CALCULADO, "formula_excel": "=+F122-G122"},
        "F99_G99_CUADRE_CANJE_DEPOSITOS": {
            "debito": str(sub(recibido, "debito") + sub(electronico, "debito") + sub(manual, "debito")),
            "credito": str(sub(recibido, "credito") + sub(electronico, "credito") + sub(manual, "credito")),
            "formula_excel": "F99=+F98+F56+F42; G99=+G98+G56+G42"},
    }
    advertencias = []
    if carta is not None and any(
            f.get("motivo_codigo") == "TOTAL_CANJE_ENVIADO" and control_impresion(f.get("concepto")) in ("0", "1")
            for f in carta):
        advertencias.append("La Carta trae TOTALES A FAVOR con control de impresion 0/1: la Plantilla (G38-G41) "
                            "solo suma la variante sin prefijo, igual que aqui.")
    return {
        "estado": "PLANTILLA_CALCULADA",
        "bloques": bloques,
        "controles": controles,
        "contabilidad_depositos": contabilidad,
        "fuera_de_alcance": ["Filas 4-5 (compensacion 035/063)", "Canje internacional (filas 124-208)"],
        "advertencias": advertencias,
        }
