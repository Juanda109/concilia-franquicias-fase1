import pytest
from app.services.fase2.cruce_depo_host_inc56h3 import cruzar


def depo(valor=None):
    return {'resultados': [{'concepto': 'DEPOSITO_NACIONAL',
        'importe_calculado': valor, 'escala_aplicada': '100' if valor else None,
        'regla_version': 'PRUEBA' if valor else None,
        'lineas_origen': [{'archivo_origen': 'DEPO.txt', 'linea_origen': 2}]}]}


def host():
    return [{'cuenta': '196095001838', 'naturaleza': 'D', 'importe_contable': '100'},
            {'cuenta': '196095001838', 'naturaleza': 'H', 'importe_contable': '2'}]


def aprobacion():
    return {'DEPOSITO_NACIONAL': {'cuenta': '196095001838',
             'naturaleza': 'D', 'aprobada': True, 'regla_version': 'PRUEBA'}}


def neto():
    return {'aprobada': True, 'regla_version': 'PRUEBA', 'expresion': 'DEBE_MENOS_HABER'}


def test_sin_correspondencia_no_infiere_cuenta():
    r = cruzar(depo(), host(), fuente_host='HA22')
    assert r['resultados'][0]['cuenta'] is None
    assert r['resultados'][0]['diferencia_diagnostica'] is None


def test_correspondencia_sin_escala_no_calcula_diferencia():
    r = cruzar(depo(), host(), fuente_host='HA22', correspondencias_aprobadas=aprobacion())
    assert r['resultados'][0]['valor_host'] == '100'
    assert r['resultados'][0]['diferencia_diagnostica'] is None


def test_comparacion_explicita_sigue_no_certificada():
    r = cruzar(depo('101'), host(), fuente_host='HA22',
              correspondencias_aprobadas=aprobacion(), regla_neto=neto())
    fila = r['resultados'][0]
    assert fila['diferencia_diagnostica'] == '1'
    assert fila['neto_host'] == '98'
    assert r['certificado_monetario'] is False and r['diferencia'] is None


def test_fuente_obligatoria():
    with pytest.raises(ValueError):
        cruzar(depo(), host())


def test_cuenta_no_autorizada():
    a = aprobacion()
    a['DEPOSITO_NACIONAL']['cuenta'] = '900000000281'
    with pytest.raises(ValueError):
        cruzar(depo(), host(), fuente_host='HA22', correspondencias_aprobadas=a)


def test_host_duplicado():
    with pytest.raises(ValueError):
        cruzar(depo(), host() + host(), fuente_host='HA22')


def test_importe_float_no_permitido():
    h = host()
    h[0]['importe_contable'] = 100.5
    with pytest.raises(ValueError):
        cruzar(depo(), h, fuente_host='HA22')


def test_no_excel_importado():
    import inspect
    from app.services.fase2 import cruce_depo_host_inc56h3 as modulo
    assert 'openpyxl' not in inspect.getsource(modulo)
