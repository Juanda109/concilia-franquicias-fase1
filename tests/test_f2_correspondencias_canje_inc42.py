import pytest
from app.services.fase2.correspondencias_canje_inc42 import aplicar


def base():
    return {'origen':'POSTGRESQL_SOLO_LECTURA','certificado':False,'id_jornada':1377,
        'resultados':[{'id_jornada':1377,'id_archivo':1254,'franquicia':'CREDIBANCO',
          'insumo':'CANT','familia':'principal','concepto_literal':'CONCEPTO PRUEBA',
          'importes':{'vl_interc':'123.00','vl_total':'124.00'},'lineas_origen':[31]}]}


def regla(**kwargs):
    r={'insumo':'CANT','familia':'principal','concepto_literal':'CONCEPTO PRUEBA',
       'cuenta_host':'196095001830','campo_importe':'vl_interc','evidencia':'Plantilla!A1 revisada'}
    r.update(kwargs)
    return r


def test_sin_reglas_pendiente():
    r=aplicar(base()); assert r['resultados'][0]['cuenta'] is None
    assert r['resultados'][0]['valor_franquicia'] is None

def test_asignacion_explicita():
    r=aplicar(base(),[regla()]); fila=r['resultados'][0]
    assert fila['cuenta']=='196095001830' and fila['valor_franquicia']=='123.00'
    assert fila['diferencia'] is None and fila['certificado'] is False

def test_campo_total_distinto():
    r=aplicar(base(),[regla(campo_importe='vl_total')]); assert r['resultados'][0]['valor_franquicia']=='124.00'

def test_duplicado_rechazado():
    with pytest.raises(ValueError,match='ambigua'): aplicar(base(),[regla(),regla()])

def test_sin_evidencia_rechazado():
    with pytest.raises(ValueError,match='evidencia'): aplicar(base(),[regla(evidencia='')])

def test_cuenta_invalida():
    with pytest.raises(ValueError,match='Cuenta'): aplicar(base(),[regla(cuenta_host='017-TEXTO')])

def test_campo_invalido():
    with pytest.raises(ValueError,match='Campo'): aplicar(base(),[regla(campo_importe='cantidad_tipo')])

def test_no_certificado():
    b=base();b['certificado']=True
    with pytest.raises(ValueError): aplicar(b)

def test_jornada_cruzada():
    b=base();b['resultados'][0]['id_jornada']=2060
    with pytest.raises(ValueError): aplicar(b)

def test_importe_nulo():
    b=base();b['resultados'][0]['importes']['vl_interc']=None
    assert aplicar(b,[regla()])['resultados'][0]['estado']=='PENDIENTE_IMPORTE_NULO'

def test_correspondencia_no_encontrada():
    r=aplicar(base(),[regla(concepto_literal='OTRO')]); assert len(r['correspondencias_sin_grupo'])==1

def test_valor_no_finito():
    b=base();b['resultados'][0]['importes']['vl_interc']='NaN'
    with pytest.raises(ValueError): aplicar(b,[regla()])
