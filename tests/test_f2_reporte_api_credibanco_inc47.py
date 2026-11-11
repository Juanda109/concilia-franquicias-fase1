from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import reporte_credibanco_inc47 as api
from app.services.fase2.reporte_api_credibanco_inc47 import construir_respuesta


def informe():
    return {'id_jornada':1377,'origen':'PRUEBA','advertencias':[],
      'totales':[{'A':'CJE','B':2,'C':'11.25','D':'12.25','archivos':[1254],'lineas_origen':[1,2]}],
      'formulas':[{'celda':'G58','cuenta':'299095302','concepto':'CJE','columna_totales':'B',
                   'unidad':'CANTIDAD','valor_proyectado':2,'valor_formula_final':2,'estado':'PROYECCION_NO_HOMOLOGADA'},
                  {'celda':'G60','cuenta':'299095302','concepto':'REEMBOLSO','columna_totales':'C',
                   'unidad':'IMPORTE_ORIGEN','valor_proyectado':'11.25','valor_formula_final':'11.25','estado':'PROYECCION_NO_HOMOLOGADA'}]}

def test_contrato_11_columnas_y_nulos():
    r=construir_respuesta(informe())
    assert len(r['columnas'])==11
    assert all(len(x)==11 and x['valor_franquicia'] is None for x in r['filas'])
    assert r['detalle'][0]['unidad']=='CANTIDAD'
    assert r['detalle'][1]['valor_diagnostico']=='11.25'
    assert r['totales_diagnosticos'][0]['archivos']==[1254]
    assert not r['certificado'] and r['indicadores']['conciliados']==0

def test_endpoint_http(monkeypatch):
    monkeypatch.setattr(api.servicio,'consultar',lambda jornada: construir_respuesta(informe()))
    app=FastAPI();app.include_router(api.router)
    client=TestClient(app)
    r=client.get('/api/v1/jornadas/1377/reporte-maestro-credibanco')
    assert r.status_code==200 and len(r.json()['filas'])==2
    assert client.get('/api/v1/jornadas/0/reporte-maestro-credibanco').status_code==422

def test_f90_pendiente():
    x=informe();x['formulas'][0].update(celda='F92',estado='PENDIENTE_VALIDACION_F90',valor_formula_final=None)
    r=construir_respuesta(x)
    assert r['detalle'][0]['valor_formula_final'] is None
    assert r['filas'][0]['diferencia'] is None
