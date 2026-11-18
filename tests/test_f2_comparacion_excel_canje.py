import pytest
from app.services.fase2.comparacion_excel_canje import comparar_grupos

BASE = {'tipo_insumo': 'CANT', 'cuenta': '017-PRUEBA', 'tipo_tarjeta': 'DEBITO',
        'canal': 'ELECTRONICO', 'tx': '02', 'cantidad': 2, 'vl_total': '100.00',
        'vl_interc': '2.00', 'comision_op_exitosas': '0', 'tii_recibida': '0'}

def test_igualdad():
    assert comparar_grupos([BASE], [dict(BASE)])['coincide']

def test_diferencia():
    row = dict(BASE, vl_total='101.00')
    assert not comparar_grupos([row], [BASE])['coincide']

def test_tolerancia():
    row = dict(BASE, vl_total='100.01')
    assert comparar_grupos([row], [BASE], '0.01')['coincide']

def test_cantidad_siempre_exacta():
    assert not comparar_grupos([dict(BASE, cantidad=3)], [BASE], '100')['coincide']

def test_faltante():
    assert comparar_grupos([], [BASE])['diferencias'][0]['estado'] == 'FALTA_CALCULADO'

def test_duplicado():
    with pytest.raises(ValueError, match='duplicado'):
        comparar_grupos([BASE, BASE], [BASE])

def test_float_prohibido():
    with pytest.raises(ValueError):
        comparar_grupos([dict(BASE, vl_total=100.0)], [BASE])

def test_sin_referencia_no_aprueba():
    assert comparar_grupos([BASE], [])['coincide'] is False
