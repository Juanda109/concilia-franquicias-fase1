"""Cuadre Redeban con la hoja ESTRUCTURA, sin BD ni Excel en ejecucion."""
from app.core.cuadre_redeban_estructura import IndicePmd, construir_cuadre_redeban, evaluar_fila

COLUMNAS = ["fila", "centro", "cuenta", "tipo", "codigo_pmd", "nombre_operacion", "movimiento",
            "emisor_adquirente", "indice_debito", "indice_credito", "signo_credito", "manual", "tipo_inconsistente"]
INDICES = {"A": (3, 8), "B": (4, 9), "C": (5, 10)}


def fila_cat(fila, cuenta, tipo, codigo, *, manual=False, inconsistente=False):
    d, c = INDICES[tipo]
    return [fila, "17", cuenta, tipo, codigo, f"OP {codigo}", "NAL", "ADQUIRENTE", d, c, -1, manual, inconsistente]


def catalogo(*filas):
    return {"version_catalogo": "REDEBAN-ESTRUCTURA-V1", "fuente": {"archivo": "prueba.xlsx", "sha256": "x"},
            "columnas": COLUMNAS, "filas": list(filas)}


def pmd(nivel, *, valor=(0, 0), interc=(0, 0), admin=(0, 0), cant=(0, 0), control=False, producto="OP"):
    dv, cv = valor
    di, ci = interc
    da, ca = admin
    return {"NIVEL": nivel, "PRODUCTO_SERVICIO": producto, "ES_CONTROL": control, "numero_linea": 1,
            "DEBITO_CANTIDAD": cant[0], "DEBITO_VALOR": dv, "DEBITO_COMISION_INTERCAMBIO": di,
            "DEBITO_COMISION_ADMIN": da, "DEBITO_NETO": dv + di + da,
            "CREDITO_CANTIDAD": cant[1], "CREDITO_VALOR": cv, "CREDITO_COMISION_INTERCAMBIO": ci,
            "CREDITO_COMISION_ADMIN": ca, "CREDITO_NETO": cv + ci + ca, "TOTAL": (cv + ci + ca) - (dv + di + da)}


def host(cuenta, fuente, debe, haber, fecha="2026-11-12"):
    return {"id_archivo": 9, "tx_host": fuente, "cuenta": cuenta, "fecha_contable": fecha, "debe": debe, "haber": haber}


def cuadre(cat, pmd_filas, host_filas=(), procesadas=("HA22", "HA26", "HA32"), inventario=()):
    return construir_cuadre_redeban(jornada={"id_jornada": 7, "fecha_contable": "2026-11-12"}, catalogo=cat,
                                    pmd_filas=list(pmd_filas), host_filas=list(host_filas),
                                    fuentes_procesadas=list(procesadas), inventario_host=list(inventario))


def cuenta(resultado, numero):
    return next(c for c in resultado["cuentas"] if c["cuenta"] == numero)


def test_fila_tipo_a_b_c_usa_sus_indices_y_resta_el_credito():
    indice = IndicePmd([pmd("1.1.1.10.102", valor=(100, 20), interc=(10, 3), admin=(5, 2), cant=(4, 9))])
    tipos = {t: evaluar_fila(dict(zip(COLUMNAS, fila_cat(n, "111", t, "1.1.1.10.102"))), indice)
             for n, t in enumerate("ABC", start=4)}
    assert (tipos["A"]["debito"], tipos["A"]["credito"], tipos["A"]["neto"]) == ("100", "-20", "80")
    assert tipos["B"]["neto"] == "7" and tipos["C"]["neto"] == "3"
    assert (tipos["A"]["cantidad_debito"], tipos["A"]["cantidad_credito"]) == ("4", "9")
    assert tipos["A"]["estado"] == "CALCULADO"


def test_codigo_ausente_en_pmd_es_cero_de_excel_sin_movimiento():
    r = evaluar_fila(dict(zip(COLUMNAS, fila_cat(4, "111", "A", "9.9.9.9.9"))), IndicePmd([]))
    assert r["neto"] == "0" and r["estado"] == "SIN_MOVIMIENTO_PMD"


def test_valor_invalido_o_ausente_no_rompe_y_deja_cuenta_sin_informacion():
    malo = pmd("1.1.1.10.102", valor=(100, 20))
    malo["CREDITO_VALOR"] = "abc"
    r = cuadre(catalogo(fila_cat(4, "111", "A", "1.1.1.10.102")), [malo])
    assert r["cuentas"][0]["neto_pmd"] is None and r["cuentas"][0]["estado"] == "SIN_INFORMACION"
    assert r["cuentas"][0]["operaciones"][0]["estado"] == "VALOR_INVALIDO"
    ausente = pmd("1.1.1.10.102", valor=(100, 20))
    ausente["DEBITO_VALOR"] = None
    r = cuadre(catalogo(fila_cat(4, "111", "A", "1.1.1.10.102")), [ausente])
    assert r["cuentas"][0]["operaciones"][0]["estado"] == "VALOR_AUSENTE"


def test_nivel_duplicado_no_elige_fila():
    filas = [pmd("1.1.1.10.102", valor=(100, 0)), pmd("1.1.1.10.102", valor=(50, 0))]
    r = cuadre(catalogo(fila_cat(4, "111", "A", "1.1.1.10.102")), filas)
    assert r["cuentas"][0]["neto_pmd"] is None
    assert r["cuentas"][0]["operaciones"][0]["estado"] == "NIVEL_DUPLICADO"


def test_carga_masiva_suma_p_por_cuenta_entre_tipos_y_excluye_manuales():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"), fila_cat(5, "111", "B", "1.1.1.10.102"),
                   fila_cat(6, "222", "C", "1.1.1.10.102"), fila_cat(7, "111", "A", "N/A", manual=True))
    r = cuadre(cat, [pmd("1.1.1.10.102", valor=(100, 20), interc=(10, 3), admin=(5, 2))])
    c111 = cuenta(r, "111")
    assert c111["neto_pmd"] == "87" and c111["filas_captura_manual"] == [7]
    assert cuenta(r, "222")["neto_pmd"] == "3"


def test_host_se_compara_por_fuente_sin_sumarlas():
    cat = catalogo(fila_cat(4, "196095001828", "A", "1.1.1.10.102"))
    filas_host = [host("196095001828", "HA32", "80", "0"), host("196095001828", "HA22", "500", "0")]
    r = cuadre(cat, [pmd("1.1.1.10.102", valor=(100, 20))], filas_host,
               inventario=[{"cuenta": "196095001828", "insumo_host": "HA32"}])
    c = r["cuentas"][0]
    assert c["host"]["HA32"]["neto"] == "80" and c["host"]["HA32"]["diferencia"] == "0"
    assert c["host"]["HA22"]["neto"] == "500" and c["host"]["HA22"]["obligatoria"] is False
    assert c["fuentes_consulta"] == ["HA32"] and c["estado"] == "CONCILIADO"


def test_estados_con_diferencia_pendiente_y_sin_consulta():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"))
    inv = [{"cuenta": "111", "insumo_host": "HA32"}]
    base = [pmd("1.1.1.10.102", valor=(100, 20))]
    assert cuadre(cat, base, [host("111", "HA32", "70", "0")], inventario=inv)["cuentas"][0]["estado"] == "CON_DIFERENCIA"
    pendiente = cuadre(cat, base, procesadas=("HA22",), inventario=inv)["cuentas"][0]
    assert pendiente["estado"] == "PENDIENTE_CONCILIACION" and pendiente["host"]["HA32"]["estado"] == "INSUMO_FALTANTE"
    assert cuadre(cat, base)["cuentas"][0]["estado"] == "SIN_CONSULTA_HOST"


def test_cero_confirmado_en_ambas_partes_concilia():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"))
    c = cuadre(cat, [pmd("2.2.2.2.2")], inventario=[{"cuenta": "111", "insumo_host": "HA26"}])["cuentas"][0]
    assert c["host"]["HA26"]["estado"] == "COINCIDE" and c["host"]["HA26"]["movimientos"] == 0
    assert c["estado"] == "CONCILIADO"


def test_host_de_otra_fecha_no_entra_y_avisa():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"))
    r = cuadre(cat, [pmd("1.1.1.10.102", valor=(100, 20))], [host("111", "HA32", "80", "0", fecha="2026-11-11")],
               inventario=[{"cuenta": "111", "insumo_host": "HA32"}])
    assert r["cuentas"][0]["host"]["HA32"]["neto"] == "0" and r["advertencias"]


def test_validador_cuadra_y_detecta_niveles_sin_estructura():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"), fila_cat(5, "111", "B", "1.1.1.10.102"),
                   fila_cat(6, "111", "C", "1.1.1.10.102"))
    filas = [pmd("1.1", valor=(100, 20), interc=(10, 3), admin=(5, 2)),
             pmd("1.1.1.10.102", valor=(100, 20), interc=(10, 3), admin=(5, 2)),
             pmd("2.1", valor=(0, 40))]
    v = {x["nivel_1"]: x for x in cuadre(cat, filas)["validador"]}
    assert v["1.1"]["neto_estructura"] == "90" and v["1.1"]["total_pmd"] == "-90" and v["1.1"]["estado"] == "CUADRA"
    assert v["2.1"]["estado"] == "SIN_FILAS_ESTRUCTURA"


def test_cobertura_parcial_y_codigos_sin_estructura():
    cat = catalogo(fila_cat(4, "111", "A", "1.2.1.8.74"), fila_cat(5, "111", "C", "1.2.1.8.74"))
    filas = [pmd("1.2.1.8.74", valor=(100, 0), interc=(7, 0)), pmd("7.1.1.19.110", valor=(0, 55))]
    r = cuadre(cat, filas)
    parcial = r["codigos_pmd_cobertura_parcial"][0]
    assert parcial["codigo_pmd"] == "1.2.1.8.74" and parcial["diferencia"] == "-7"
    assert parcial["tipos_en_estructura"] == ["A", "C"]
    assert [x["codigo_pmd"] for x in r["codigos_pmd_sin_estructura"]] == ["7.1.1.19.110"]


def test_movimiento_pmd_en_fila_sin_cuenta_se_reporta():
    cat = catalogo(fila_cat(4, "", "B", "1.1.1.10.102"))
    r = cuadre(cat, [pmd("1.1.1.10.102", interc=(9, 0))])
    assert [x["fila"] for x in r["movimientos_pmd_sin_cuenta"]] == [4]


def test_filas_de_control_pmd_se_excluyen():
    cat = catalogo(fila_cat(4, "111", "A", "1.1.1.10.102"))
    r = cuadre(cat, [pmd("1.1.1.10.102", valor=(999, 0), control=True)])
    assert r["cuentas"][0]["neto_pmd"] == "0"


def test_sin_pmd_marca_insumo_faltante():
    r = cuadre(catalogo(fila_cat(4, "111", "A", "1.1.1.10.102")), [])
    assert r["estado"] == "INSUMO_PMD_FALTANTE" and r["cuentas"] == []
    assert "certificado" not in r


def test_catalogo_real_estructura():
    from app.repositories.cierre_redeban import _cargar_estructura, _cargar_inventario_host
    cat = _cargar_estructura()
    filas = [dict(zip(cat["columnas"], f)) for f in cat["filas"]]
    assert len(filas) == 3248
    assert [f["fila"] for f in filas if f["tipo_inconsistente"]] == [1371, 1640, 3110, 3111]
    assert sum(1 for f in filas if f["manual"]) == 10
    assert len(_cargar_inventario_host()) == 31
