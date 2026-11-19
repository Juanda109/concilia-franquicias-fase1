"""Filtro de persistencia DEPO-F1-001 (especificacion integral, seccion 3.1)."""
from app.parsers.depo import DEPOParser, _amex_nacional, _persiste


def fila(tipo, *, indicador="", tasa=0, amex=""):
    return {"TIPO_MOVIMIENTO": tipo, "INDICADOR_CASH_BACK": indicador,
            "TASA_DE_INTERCAMBIO": tasa, "AMEX_NACIONAL": amex}


def linea_tarjeta(tarjeta):
    """Linea DEPO con NO_TARJETA (posicion 56, longitud 19) dada."""
    return ("99".ljust(55) + tarjeta.ljust(19)).ljust(282)


def test_amex_nacional_por_bin_de_la_hoja_bines_amex():
    assert _amex_nacional(linea_tarjeta("0000377813000000000")) == "AMEX NACIONAL"


def test_amex_internacional_si_bin_no_esta_en_lista():
    assert _amex_nacional(linea_tarjeta("0000371234000000000")) == "AMEX INTERNACIONAL"


def test_no_amex_si_posiciones_59_60_no_son_0_y_3():
    assert _amex_nacional(linea_tarjeta("0000456789000000000")) == ""
    assert _amex_nacional(linea_tarjeta("0001377813000000000")) == ""


def test_regla4_amex_internacional_persiste_y_nacional_no():
    assert _persiste(fila("99", amex="AMEX INTERNACIONAL"))
    assert not _persiste(fila("99", amex="AMEX NACIONAL"))


def test_regla1_control_resumen_no_persiste_aunque_cumpla_otras():
    assert not _persiste(fila("05", indicador="010", tasa=5))


def test_regla2_tipos_movimiento_persisten():
    for tipo in ("02", "06", "26", "42"):
        assert _persiste(fila(tipo))


def test_regla3_indicador_cnb_persiste():
    for indicador in ("010", "011", "012", "110", "111", "112"):
        assert _persiste(fila("99", indicador=indicador))


def test_regla3_indicador_no_cnb_no_persiste():
    assert not _persiste(fila("99", indicador="013"))


def test_regla5_tasa_distinta_de_cero_persiste():
    assert _persiste(fila("99", tasa=-3))


def test_sin_regla_funcional_no_persiste():
    assert not _persiste(fila("99"))


def test_parser_aplica_regla3_sobre_linea_posicional(tmp_path):
    linea = "99".ljust(264) + "011"
    descartada = "99".ljust(264) + "013"
    archivo = tmp_path / "depo.txt"
    archivo.write_text(linea + "\n" + descartada + "\n", encoding="utf-8")
    r = DEPOParser().parse(archivo)
    assert [row["INDICADOR_CASH_BACK"] for row in r.records] == ["011"]
    controles = {c["codigo"]: c["obtenido"] for c in r.controls}
    assert controles["DESCARTADOS_FILTRO_PERSISTENCIA"] == 1
