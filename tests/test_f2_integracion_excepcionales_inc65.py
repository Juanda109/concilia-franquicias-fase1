from copy import deepcopy
from decimal import Decimal
import pytest
from app.services.fase2.integracion_excepcionales_inc65 import aplicar_excepcionales, COLUMNAS_PMD

CODES = {1371: '1.1.1.8.5008', 1640: '4.1.1.10.414', 3110: '2.1.2.50.138', 3111: '2.1.2.50.135'}

def proyeccion():
    filas = [dict(fila_excel=n, codigo_operacion=c, cuenta_contable='1',
                 estado='FORMULA_EXCEPCIONAL_PENDIENTE', neto_diagnostico=None,
                 id_jornada=6466, version_catalogo='sha', certificado=False)
            for n,c in CODES.items()]
    filas.append(dict(fila_excel=3246, codigo_operacion='N/A', cuenta_contable='514005180',
                     estado='PARTIDA_MANUAL_NO_HOMOLOGADA', neto_diagnostico=None,
                     id_jornada=6466, version_catalogo='sha', certificado=False))
    return dict(id_jornada=6466, version_catalogo='sha', certificado=False,
                cantidad_filas=len(filas), filas=filas)

def pmd(codigo, **values):
    fila = dict.fromkeys(COLUMNAS_PMD, Decimal('0'))
    fila['NIVEL'] = codigo
    fila.update(values)
    fila['ES_CONTROL'] = False
    return fila

def test_mapeo_literal():
    assert COLUMNAS_PMD[3] == 'DEBITO_COMISION_INTERCAMBIO'
    assert COLUMNAS_PMD[4] == 'DEBITO_COMISION_ADMINISTRATIVA'
    assert COLUMNAS_PMD[8] == 'CREDITO_COMISION_INTERCAMBIO'
    assert COLUMNAS_PMD[9] == 'CREDITO_COMISION_ADMINISTRATIVA'

def test_una_presente_tres_ausentes_y_manual_intacta():
    original = proyeccion(); copia = deepcopy(original)
    datos = [pmd(CODES[1371], DEBITO_COMISION_INTERCAMBIO=Decimal('0'),
                 CREDITO_COMISION_INTERCAMBIO=Decimal('0'),
                 DEBITO_COMISION_ADMINISTRATIVA=Decimal('36959'))]
    r = aplicar_excepcionales(original, datos)
    assert original == copia
    assert [f['estado'] for f in r['filas']] == (
        ['CALCULO_DIAGNOSTICO'] + ['OPERANDOS_NO_RESUELTOS']*3 + ['PARTIDA_MANUAL_NO_HOMOLOGADA'])
    assert r['filas'][0]['neto_diagnostico'] == '0'
    assert r['filas'][-1] == original['filas'][-1]
    assert r['certificado'] is False

def test_importe_no_cero():
    datos = [pmd(CODES[1371], DEBITO_COMISION_INTERCAMBIO='100.25',
                 CREDITO_COMISION_INTERCAMBIO='20.10')]
    r = aplicar_excepcionales(proyeccion(), datos)
    assert r['filas'][0]['neto_diagnostico'] == '80.15'

def test_codigo_duplicado_no_calcula():
    dato = pmd(CODES[1371])
    r = aplicar_excepcionales(proyeccion(), [dato,dato])
    assert r['filas'][0]['neto_diagnostico'] is None
    assert r['inc65_excepcionales'][0]['estado'] == 'CODIGO_PMD_DUPLICADO'

def test_no_certifica():
    p = proyeccion(); p['certificado'] = True
    with pytest.raises(ValueError): aplicar_excepcionales(p, [])

def test_no_acepta_excepcion_faltante():
    p = proyeccion(); p['filas'] = p['filas'][1:]; p['cantidad_filas'] -= 1
    with pytest.raises(ValueError): aplicar_excepcionales(p, [])
