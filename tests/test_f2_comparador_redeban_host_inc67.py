from decimal import Decimal
import pytest
from app.services.fase2.comparador_redeban_host_inc67 import comparar

CAT = {'299095508': {'regla_consulta': 'ANTERIOR_RANGO'}, '299095302': {'regla_consulta': 'ANTERIOR_INICIO'}}
HOM = {'299095508': {'franquicia_relacionada': 'REDEBAN', 'estado_homologacion': 'PENDIENTE_VALIDACION_MONETARIA'}, '299095302': {'franquicia_relacionada': 'CREDIBANCO|VISA', 'estado_homologacion': 'PENDIENTE_VALIDACION_MONETARIA'}}
R = [{'cuenta': '299095508', 'estado': 'CALCULO_DIAGNOSTICO', 'importe': Decimal('10.25'), 'fila_excel': 7}]
H = [{'cuenta': '299095508', 'centro': '17', 'fecha_contable': '2026-10-01', 'debe': '10.25', 'haber': '0', 'fuente': 'HA22', 'linea': 2}]

def ejecutar(r=R, h=H, cat=CAT, hom=HOM, fechas=None, signos=None):
    return comparar(cat, hom, r, h, '2026-10-02', fechas, signos)

def test_sin_host():
    assert ejecutar(h=[])['cuentas'][0]['estado'] == 'SIN_HOST'

def test_sin_redeban():
    assert ejecutar(r=[])['cuentas'][0]['estado'] == 'SIN_REDEBAN'

def test_fecha_pendiente():
    assert ejecutar()['cuentas'][0]['estado'] == 'PENDIENTE_REGLA_FECHA'

def test_signo_no_homologado():
    x = ejecutar(fechas={'299095508': {'2026-10-01'}})['cuentas'][0]
    assert x['estado'] == 'PENDIENTE_HOMOLOGACION' and x['diferencia'] is None

def test_sintetico_no_conciliable():
    h = [{**H[0], 'sintetico': True}]
    x = ejecutar(h=h, fechas={'299095508': {'2026-10-01'}})['cuentas'][0]
    assert x['estado'] == 'SOLO_PRUEBA_SINTETICA'

def test_decimal_y_signo_diagnostico():
    hom = {**HOM, '299095508': {**HOM['299095508'], 'estado_homologacion': 'HOMOLOGADA_MONETARIA'}}
    x = ejecutar(hom=hom, fechas={'299095508': {'2026-10-01'}}, signos={'299095508': 'DEBE_MENOS_HABER'})['cuentas'][0]
    assert (x['neto_redeban'], x['neto_host'], x['diferencia']) == ('10.25', '10.25', '0.00')
    assert x['certificado'] is False

def test_no_incluir_cuenta_otra_franquicia():
    assert len(ejecutar()['cuentas']) == 1

def test_no_float():
    with pytest.raises(ValueError):
        ejecutar(r=[{**R[0], 'importe': 10.25}])

def test_catalogos_incompatibles():
    with pytest.raises(ValueError):
        ejecutar(hom={})


def test_bloquea_neto_parcial_con_operandos_pendientes():
    filas = R + [{'cuenta':'299095508','estado':'OPERANDOS_NO_RESUELTOS',
                   'neto_diagnostico':None,'fila_excel':8}]
    hom = {**HOM, '299095508': {**HOM['299095508'],
           'estado_homologacion':'HOMOLOGADA_MONETARIA'}}
    x = ejecutar(r=filas, hom=hom, fechas={'299095508':{'2026-10-01'}},
                signos={'299095508':'DEBE_MENOS_HABER'})['cuentas'][0]
    assert x['estado']=='PENDIENTE_OPERANDOS_REDEBAN'
    assert x['cantidad_redeban_pendientes']==1
    assert x['diferencia'] is None

def test_bloquea_fuentes_host_mezcladas():
    hom = {**HOM, '299095508': {**HOM['299095508'],
           'estado_homologacion':'HOMOLOGADA_MONETARIA'}}
    x = ejecutar(h=H + [{**H[0], 'fuente':'HA26'}], hom=hom,
                fechas={'299095508':{'2026-10-01'}},
                signos={'299095508':'DEBE_MENOS_HABER'})['cuentas'][0]
    assert x['estado']=='PENDIENTE_FUENTE_HOST'
    assert x['diferencia'] is None

def test_bloquea_prueba_en_campos_origen():
    hom = {**HOM, '299095508': {**HOM['299095508'],
           'estado_homologacion':'HOMOLOGADA_MONETARIA'}}
    x = ejecutar(h=[{**H[0], 'campos_origen':{'DESCON':'PRUEBA SINTETICA'}}],
                hom=hom, fechas={'299095508':{'2026-10-01'}},
                signos={'299095508':'DEBE_MENOS_HABER'})['cuentas'][0]
    assert x['estado']=='SOLO_PRUEBA_SINTETICA'
    assert x['diferencia'] is None
