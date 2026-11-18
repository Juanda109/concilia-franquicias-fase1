from decimal import Decimal
import pytest
from app.services.fase2.validacion_integral_excel_canje import numero, comparar_grupos, comparar


def test_numero_nulo():
    assert numero('') is None


def test_numero_decimal():
    assert numero('12.50') == Decimal('12.50')


def test_numero_no_finito():
    assert numero('NaN') is None


def test_diferencia_monetaria():
    d = comparar_grupos({'A': {'vl_total': Decimal(10)}}, {'A': {'vl_total': Decimal(9)}}, ['vl_total'])
    assert d[0]['estado'] == 'DIFERENCIA'


def test_sin_diferencia():
    assert comparar_grupos({'A': {'vl_total': Decimal(10)}}, {'A': {'vl_total': Decimal(10)}}, ['vl_total']) == []


def test_grupo_solo_python():
    assert comparar_grupos({'A': {}}, {}, [])[0]['estado'] == 'SOLO_PYTHON'


def test_grupo_solo_excel():
    assert comparar_grupos({}, {'A': {}}, [])[0]['estado'] == 'SOLO_CACHE_EXCEL'


def test_cache_sin_valor():
    d = comparar_grupos({'A': {'vl_total': 10}}, {'A': {'vl_total': None}}, ['vl_total'])
    assert d[0]['estado'] == 'CACHE_SIN_VALOR'


def test_comparacion_tres_grupos():
    grupos = {'principal': {}, 'comisiones': {}, 'cuenta_880': {}}
    assert comparar(grupos, grupos) == {k: [] for k in grupos}


def test_falta_plantilla(tmp_path):
    from app.services.fase2.validacion_integral_excel_canje import ejecutar
    with pytest.raises(FileNotFoundError):
        ejecutar(tmp_path / 'no.xlsx', tmp_path / 'out')


def test_no_sobrescribir(tmp_path):
    from app.services.fase2.validacion_integral_excel_canje import ejecutar
    archivo = tmp_path / 'a.xlsx'
    archivo.write_bytes(b'placeholder')
    salida = tmp_path / 'out'
    salida.mkdir()
    with pytest.raises(FileExistsError):
        ejecutar(archivo, salida)
