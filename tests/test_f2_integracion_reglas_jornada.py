import json
import pytest
from app.services.fase2.integracion_reglas_jornada import procesar, ejecutar

def base():
    return {'id_jornada':1377,'fecha_contable':'2026-10-21','insumos':[
      {'id_jornada':1377,'id_archivo':1254,'tipo_insumo':'CANT','correlation_id':'c1',
       'reglas':['PM37-O15','PM37-P15'],'celdas':{'M15':'10.10','N15':'2.20','L15':'20','O15':'12.30'}}]}

def test_calculo_y_trazabilidad():
    r=procesar(base()); assert [x['valor'] for x in r['resultados']]==['12.30','7.70']
    assert r['resultados'][0]['id_archivo']==1254 and r['resultados'][0]['correlation_id']=='c1'
    assert not r['certificado'] and r['cruces']==[]

def test_faltante_no_cero():
    p=base();p['insumos'][0]['celdas'].pop('O15')
    r=procesar(p); assert r['resultados'][1]['valor'] is None
    assert r['resultados'][1]['estado']=='INSUMO_PENDIENTE'

def test_jornada_incorrecta():
    p=base();p['insumos'][0]['id_jornada']=2060
    with pytest.raises(ValueError,match='otra jornada'): procesar(p)

def test_archivo_duplicado():
    p=base();p['insumos'].append(dict(p['insumos'][0]))
    with pytest.raises(ValueError,match='duplicado'): procesar(p)

def test_regla_desconocida():
    p=base();p['insumos'][0]['reglas']=['NO_EXISTE']
    with pytest.raises(ValueError,match='no autorizada'): procesar(p)

def test_carta_faltante():
    p=base();p['insumos'][0].update(tipo_insumo='CARTA_COMPENSACION',reglas=['PM37-G38'])
    r=procesar(p);assert r['resultados'][0]['valor'] is None

def test_carta_con_datos():
    p=base();p['insumos'][0].update(tipo_insumo='CARTA_COMPENSACION',reglas=['PM37-G38'],
      carta=[{'B':'     T O T A L E S   A   F A V O R','D':'12.50'}])
    assert procesar(p)['resultados'][0]['valor']=='12.50'

def test_sin_resultados_no_inventa():
    p=base();p['insumos']=[]
    assert procesar(p)['resultados']==[]

def test_diagnostico_parte_separado():
    r=procesar(base(),[{'TX':'Totales'}]);assert r['diagnostico_caet_cant']['conteos']['totales']==1

def test_archivo_salida_nuevo(tmp_path):
    p=tmp_path/'entrada.json';p.write_text(json.dumps(base()),encoding='utf-8')
    d=tmp_path/'salida'; r=ejecutar(p,d)
    assert (d/'informe.json').is_file() and r['sha256_entrada']
    with pytest.raises(FileExistsError): ejecutar(p,d)

def test_tipo_no_autorizado():
    p=base();p['insumos'][0]['tipo_insumo']='HA22'
    with pytest.raises(ValueError,match='no permitido'): procesar(p)
