import json
from pathlib import Path
import pytest
from app.services.fase2.cuentas_credibanco_inc44 import asociar, cargar_catalogo

CAT = cargar_catalogo(Path(__file__).resolve().parents[1] / 'catalogo_credibanco_inc44.json')

def muestra(concepto='017-CANJE RECIBIDO TARJETA CREDITO PAGOS', uso='FILA_MAESTRO'):
    return {'id_jornada':1377,'certificado':False,'filas':[{'franquicia':'CREDIBANCO','concepto':concepto,'cuenta':None,'valor_franquicia':None}], 'detalle':[{'franquicia':'CREDIBANCO','concepto':concepto,'uso':uso,'cuenta':None,'valor_franquicia':None,'importes_diagnosticos':{'vl_interc':'223136015.0000','vl_total':'223136015.0000'},'ha22':None,'ha26':None,'ha32':None,'diferencia':None}]}

def test_identifica_cuenta_sin_certificar():
    x=asociar(muestra(),CAT)
    assert x['detalle'][0]['cuenta_referencia_plantilla']=='299095302'
    assert x['detalle'][0]['cuenta'] is None
    assert x['detalle'][0]['valor_franquicia'] is None
    assert x['detalle'][0]['importes_diagnosticos']['vl_interc']=='223136015.0000'
    assert x['catalogo_inc44']['homologaciones_host']==0

def test_auxiliar_no_sumar():
    x=asociar(muestra(uso='SOLO_TRAZABILIDAD_NO_SUMAR'),CAT)
    assert x['detalle'][0]['estado_cuenta_referencia']=='AUXILIAR_NO_SUMAR'
    assert x['detalle'][0]['cuenta_referencia_plantilla'] is None

def test_sin_match_no_infiere():
    x=asociar(muestra('CONCEPTO NO DOCUMENTADO'),CAT)
    assert x['detalle'][0]['cuenta_referencia_plantilla'] is None

def test_rechaza_certificado():
    x=muestra(); x['certificado']=True
    with pytest.raises(ValueError): asociar(x,CAT)

def test_catalogo_seis_conceptos():
    assert len(CAT['reglas'])==6

def test_representacion_duplicada_por_insumo_no_duplica_catalogo():
    x=muestra('017-REPRESENTACION  VENTA NAL (CENTRO 730)')
    x['detalle'].append(dict(x['detalle'][0],insumo='CANT'))
    y=asociar(x,CAT)
    assert y['catalogo_inc44']['filas_detalle_con_cuenta_referencia']==2
    assert all(d['cuenta_referencia_plantilla']=='299095038' for d in y['detalle'])

def test_cuentas_documentadas():
    cuentas={r['concepto']:r['cuenta'] for r in CAT['reglas']}
    assert cuentas['017-ORIGINAL REEMBOLSOS DEBITO']=='299095301'
    assert cuentas['017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO']=='299095843'

def test_no_cambia_host_ni_diferencia():
    d=asociar(muestra(),CAT)['detalle'][0]
    assert all(d[k] is None for k in ('ha22','ha26','ha32','diferencia'))
