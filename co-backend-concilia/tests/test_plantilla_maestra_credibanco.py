"""Plantilla Maestra Credibanco: formulas literales, sin BD ni Excel en ejecucion.

Las pruebas de regresion usan los valores que la propia Plantilla Maestra.xlsx
guarda en cache (vinculos a CARTA del 2026-09-01 y a td cuadre) y exigen los
mismos resultados que calculo Excel.
"""
from app.core.plantilla_maestra_credibanco import construir_plantilla_maestra, control_impresion

HOST_OK = "PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE"


def total_carta(lado, motivo, *, principal, proceso, financiacion, fotocopias, red, total, cc=""):
    concepto = f"TOTALES {lado.replace('_', ' ')}" + (f" [CC={cc}]" if cc else "")
    return dict(seccion="CAI0224A", motivo_codigo=motivo, es_control=True, lado=lado, concepto=concepto,
                cantidad=1, valor_principal=principal, valor_proceso=proceso, valor_financiacion=financiacion,
                valor_fotocopias=fotocopias, valor_red=red, valor_total=total)


def concepto_carta(motivo, concepto, valor):
    return dict(seccion="CAI0224A", motivo_codigo=motivo, es_control=False, lado=None,
                concepto=concepto, cantidad=1, valor_principal=valor)


CARTA_20260901 = [
    total_carta("A_FAVOR", "TOTAL_CANJE_ENVIADO", principal="-1025581202", proceso="706817",
                financiacion="6627", fotocopias="0", red="4265910", total="11963220479"),
    total_carta("A_CARGO", "TOTAL_CANJE_RECIBIDO", principal="1482586095", proceso="413417",
                financiacion="-536307", fotocopias="0", red="100004246", total="51582467451"),
    concepto_carta("REINTEGRO", "A FAVOR OUTCLEAR FECHA > 26/09/01", "359805725"),
    concepto_carta("DESCUENTO_CARGO", "VR A CARGO DOC DEP FOTOCOPIAS", "-156084"),
]


def depo(tipo, oficina, valor, *, amex="", tasa="0", cantidad=1, indicador=""):
    return dict(tipo_movimiento=tipo, cod_oficina=oficina, indicador_cash_back=indicador,
                amex_nacional=amex, cantidad=cantidad, valores_invalidos=0,
                valor_total_crudo=valor, tasa_intercambio_cruda=tasa, nulos_tasa=0)


# td cuadre en cache: A:B por cuenta, D:E por TII, 570 retiros ATM (O4 = 4.252.200).
DEPO_CACHE = [
    depo("06", "0001", "13013733829", tasa="169761063"),
    depo("06", "0090", "1705486023", tasa="2701953"),
    depo("06", "0001", "100", amex="AMEX INTERNACIONAL", tasa="10459090"),
    depo("26", "0001", "15917200"),
    depo("26", "0090", "4237428"),
    depo("02", "0001", "43550000", cantidad=570),
]
HOST_CACHE = [
    dict(cuenta="196095001838", centro="0017", fuente="HA22", debe="13012735535", haber="15288100", estado=HOST_OK),
    dict(cuenta="196095001839", centro="0017", fuente="HA22", debe="1705115823", haber="4237428", estado=HOST_OK),
]


def bloque(resultado, codigo):
    return next(b for b in resultado["bloques"] if b["codigo"] == codigo)


def fila(resultado, codigo, numero):
    return next(f for f in bloque(resultado, codigo)["filas"] if f["fila"] == numero)


def plantilla(**kw):
    base = dict(carta=None, canje=None, depo=None, movimientos_host=None, l8=None)
    base.update(kw)
    return construir_plantilla_maestra(**base)


def test_control_impresion_lee_marca_del_parser():
    assert control_impresion("TOTALES A CARGO [CC=1]") == "1"
    assert control_impresion("TOTALES A CARGO") == ""


def test_regresion_bloques_carta_contra_cache_de_la_plantilla():
    r = plantilla(carta=CARTA_20260901, canje=[], l8={"l8": "255034593"})
    manual = bloque(r, "CUADRE_CANJE_MANUAL")
    assert [fila(r, "CUADRE_CANJE_MANUAL", n)["credito"] for n in (38, 39, 40, 41)] == ["706817", "6627", "0", "4265910"]
    assert manual["subtotal_credito"] == "4979354" and manual["subtotal_debito"] == "0"
    electronico = bloque(r, "CUADRE_CANJE_ELECTRONICO")
    assert fila(r, "CUADRE_CANJE_ELECTRONICO", 52)["credito"] == "359805725"
    assert fila(r, "CUADRE_CANJE_ELECTRONICO", 55)["debito"] == "156084"
    assert fila(r, "CUADRE_CANJE_ELECTRONICO", 50)["debito"] == "0"
    assert (electronico["subtotal_debito"], electronico["subtotal_credito"]) == ("156084", "359805725")
    j40 = r["controles"]["J40_VALIDACION_CANJE_ENVIADO"]
    assert (j40["h40"], j40["i40"], j40["valor"]) == ("0", "-1025581202", "-1025581202")


def test_regresion_canje_recibido_contra_cache_de_la_plantilla():
    r = plantilla(carta=CARTA_20260901, canje=[], l8={"l8": "255034593"})
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 94)["debito"] == "413417"
    f95 = fila(r, "TOTAL_CANJE_RECIBIDO", 95)
    assert (f95["debito"], f95["credito"]) == ("-536307", "-536307")
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 96)["credito"] == "536307"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 97)["debito"] == "255034593"
    recibido = bloque(r, "TOTAL_CANJE_RECIBIDO")
    assert (recibido["subtotal_debito"], recibido["subtotal_credito"]) == ("254911703", "0")
    j90 = r["controles"]["J90_VALIDACION_CANJE_RECIBIDO_CARTA"]
    assert (j90["h90"], j90["i90"], j90["valor"]) == ("254911703", "51582467451", "-51327555748")


def test_regresion_depositos_contra_cache_de_td_cuadre():
    r = plantilla(depo=DEPO_CACHE, movimientos_host=HOST_CACHE)
    esperado = {
        100: (None, "13012735535"), 101: ("15288100", None), 103: (None, "998294"), 104: (None, "370300"),
        105: ("629100", None), 106: ("0", None), 107: ("370300", "0"), 108: (None, "43550000"),
        110: ("0", "-169761063"), 111: ("-169761063", None), 112: ("169761063", None),
        113: ("13161043", None), 114: (None, "2701953"), 115: (None, "10459090"), 116: (None, "4252200"),
    }
    for numero, (debito, credito) in esperado.items():
        f = fila(r, "TOTAL_DEPOSITOS_ELECTRONICOS", numero)
        assert (f["debito"], f["credito"]) == (debito, credito), numero
    depositos = bloque(r, "TOTAL_DEPOSITOS_ELECTRONICOS")
    assert (depositos["subtotal_debito"], depositos["subtotal_credito"]) == ("29448543", "12905306309")
    assert depositos["subtotal_completo"] is True


def test_totales_usa_columna_2_vl_interc_y_columna_3_vl_total():
    canje = [
        dict(cuenta="017-CANJE RECIBIDO TARJETA CREDITO PAGOS", total_intercambio="40", total_valor="100",
             nulos_interc=0, nulos_total=0),
        dict(cuenta="017-ORIGINAL REEMBOLSOS CREDITO", total_intercambio="5", total_valor="70",
             nulos_interc=0, nulos_total=0),
    ]
    r = plantilla(canje=canje)
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 58)["credito"] == "40"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 60)["credito"] == "70"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 61)["estado"] == "SIN_DATO_EXCEL_CERO"
    assert r["controles"]["I57_CUENTA_302"]["valor"] == "-110"


def test_totales_busca_regalo_en_tabla_cuenta_880_y_comisiones_en_e_f():
    canje = [
        dict(cuenta_880="017-CANJE RECIBIDO TARJETA DEBITO REGALO", total_intercambio="3", total_valor="9",
             nulos_interc=0, nulos_total=0),
        dict(cuentas_comisiones="017-COMISIONES EXIT. TARJETA DEBITO ONLINE", total_comision="7450", nulos_comision=0),
        dict(cuentas_comisiones="017-TII RECIBIDA EMISOR VISA OP REVER VENTAS", total_tii="12"),
    ]
    r = plantilla(canje=canje)
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 84)["debito"] == "9"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 66)["credito"] == "9"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 75)["debito"] == "7450"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 89)["debito"] == "12"
    f83 = fila(r, "TOTAL_CANJE_RECIBIDO", 83)
    assert f83["debito"] is None and f83["estado"] == "SIN_DATO_EXCEL_VACIO" and f83["sin_valor"] is False


def test_nulos_del_parser_no_se_convierten_en_cero():
    canje = [dict(cuenta="017-CANJE RECIBIDO TARJETA CREDITO PAGOS", total_intercambio=None, total_valor="1",
                  nulos_interc=2, nulos_total=0)]
    f58 = fila(plantilla(canje=canje), "TOTAL_CANJE_RECIBIDO", 58)
    assert f58["credito"] is None and f58["estado"] == "DATO_INCOMPLETO" and f58["sin_valor"] is True


def test_cuota_red_pendiente_sin_l8_aprobado():
    r = plantilla(carta=CARTA_20260901, canje=[])
    f97 = fila(r, "TOTAL_CANJE_RECIBIDO", 97)
    assert f97["debito"] is None and f97["estado"] == "PENDIENTE_APROBACION_L8"
    assert 97 in bloque(r, "TOTAL_CANJE_RECIBIDO")["filas_sin_valor"]


def test_insumos_faltantes_no_inventan_valores():
    r = plantilla()
    assert fila(r, "CUADRE_CANJE_MANUAL", 38)["estado"] == "INSUMO_CARTA_FALTANTE"
    assert fila(r, "TOTAL_CANJE_RECIBIDO", 58)["estado"] == "INSUMO_CAET_CANT_FALTANTE"
    assert fila(r, "TOTAL_DEPOSITOS_ELECTRONICOS", 100)["estado"] == "INSUMO_HA22_FALTANTE"
    assert fila(r, "TOTAL_DEPOSITOS_ELECTRONICOS", 108)["estado"] == "INSUMO_DEPO_FALTANTE"


def test_host_sin_cuenta_es_cero_por_sumifs_y_sintetico_bloquea():
    r = plantilla(depo=DEPO_CACHE, movimientos_host=[])
    f100 = fila(r, "TOTAL_DEPOSITOS_ELECTRONICOS", 100)
    assert f100["credito"] == "0" and f100["estado"] == "SIN_MOVIMIENTO_HOST_SUMIFS_CERO"
    sintetico = [{**HOST_CACHE[0], "estado": "BLOQUEADO_SINTETICO"}]
    f103 = fila(plantilla(depo=DEPO_CACHE, movimientos_host=sintetico), "TOTAL_DEPOSITOS_ELECTRONICOS", 103)
    assert f103["credito"] is None and f103["estado"] == "HOST_NO_VALIDADO_O_SINTETICO"


def test_atm_sin_retiros_es_na_como_excel():
    f116 = fila(plantilla(depo=[depo("06", "0001", "10")], movimientos_host=[]), "TOTAL_DEPOSITOS_ELECTRONICOS", 116)
    assert f116["credito"] is None and f116["estado"] == "SIN_DATO_EXCEL_NA"


def test_totales_a_favor_con_control_0_no_entra_en_g38_y_avisa():
    carta = [total_carta("A_FAVOR", "TOTAL_CANJE_ENVIADO", principal="1", proceso="50", financiacion="0",
                         fotocopias="0", red="0", total="1", cc="0")]
    r = plantilla(carta=carta)
    f38 = fila(r, "CUADRE_CANJE_MANUAL", 38)
    assert f38["credito"] == "0" and f38["estado"] == "SIN_DATO_EXCEL_CERO"
    assert r["controles"]["J40_VALIDACION_CANJE_ENVIADO"]["i40"] == "1"
    assert r["advertencias"]


def test_filas_de_captura_manual_se_listan_aparte():
    r = plantilla()
    manuales = {m["fila"] for m in bloque(r, "TOTAL_CANJE_RECIBIDO")["filas_captura_manual"]}
    assert {63, 64, 65, 76, 77, 78, 86, 88, 91} == manuales


# ---------------------------------------------- CAI 160 A y comision ATM
def cai160(codigo, bin_, valor):
    return dict(seccion="CAI0160A", motivo_codigo=f"CAI160_{codigo}", es_control=False, lado=None,
                concepto=f"{codigo} X - BIN {bin_}", cantidad=1, valor_total=valor)


def test_cai160_llena_pagos_devoluciones_represent_y_reembolso():
    carta = CARTA_20260901 + [
        cai160("04", "404280", "100"), cai160("04", "421892", "50"),
        cai160("16", "404280", "-30"), cai160("16", "421892", "-20"),
        cai160("36", "404280", "-10"), cai160("08", "410164", "7"),
    ]
    r = plantilla(carta=carta, canje=[], l8={"l8": "1"})
    assert fila(r, "CUADRE_CANJE_MANUAL", 6)["debito"] == "150"
    assert [fila(r, "CUADRE_CANJE_MANUAL", n)["credito"] for n in (16, 17)] == ["30", "20"]
    assert fila(r, "CUADRE_CANJE_MANUAL", 26)["credito"] == "10"
    assert fila(r, "CUADRE_CANJE_MANUAL", 29)["debito"] == "7"
    manuales = {m["fila"] for m in bloque(r, "CUADRE_CANJE_MANUAL")["filas_captura_manual"]}
    assert not manuales & {6, 16, 17, 26, 29} and 18 in manuales


def test_cai160_mas_de_ocho_devoluciones_acumula_el_resto_en_la_23():
    carta = CARTA_20260901 + [cai160("16", f"40000{i}", "-1") for i in range(10)]
    r = plantilla(carta=carta, canje=[], l8={"l8": "1"})
    assert fila(r, "CUADRE_CANJE_MANUAL", 22)["credito"] == "1"
    assert fila(r, "CUADRE_CANJE_MANUAL", 23)["credito"] == "3"


def test_sin_hoja_cai160_las_filas_quedan_como_captura_manual():
    r = plantilla(carta=CARTA_20260901, canje=[], l8={"l8": "1"})
    manuales = {m["fila"] for m in bloque(r, "CUADRE_CANJE_MANUAL")["filas_captura_manual"]}
    assert {6, 16, 26, 29} <= manuales


def test_comision_interoperabilidad_atm_va_a_g9():
    carta = CARTA_20260901 + [dict(seccion="CAI0224A", motivo_codigo="CONCEPTO_CANJE_ENVIADO", es_control=False,
                                   lado="A_FAVOR", concepto="COMISION INTEROPERABILI. ATM", cantidad=1,
                                   valor_principal="188550")]
    r = plantilla(carta=carta, canje=[], l8={"l8": "1"})
    assert fila(r, "CUADRE_CANJE_MANUAL", 9)["credito"] == "188550"
    assert bloque(r, "CUADRE_CANJE_MANUAL")["subtotal_credito"] == str(4979354 + 188550)


def test_h40_solo_devuelve_creditos_de_las_filas_38_a_41():
    carta = CARTA_20260901 + [cai160("04", "404280", "1000"), cai160("16", "404280", "-200")]
    r = plantilla(carta=carta, canje=[], l8={"l8": "1"})
    # F42 = 1000; G42 = 200 + 4979354 (filas 38-41); H40 = 1000 - 200
    assert r["controles"]["J40_VALIDACION_CANJE_ENVIADO"]["h40"] == "800"
