from app.services.fase2.reporte_host_inc50 import integrar_host
import pytest

def base():
    columnas=['c'+str(i) for i in range(11)]
    return {'id_jornada':2590,'certificado':False,'columnas':columnas,
            'filas':[{'cuenta':'299095302','ha22':None,'ha26':None,'ha32':None,'total_host':None,'diferencia':None}],
            'detalle':[{'cuenta':'299095302','concepto':'CJE','vl_interc':'11.25'}]}

def host():
    return {'id_jornada':2590,'certificado':False,'filas':[
        {'fuente':'HA22','cuenta':'299095302','centro':'17','neto_diagnostico':'11747139.00','id_archivo':2207,'lineas_origen':[2]},
        {'fuente':'HA26','cuenta':'299095302','centro':'17','neto_diagnostico':'11747389.00','id_archivo':2211,'lineas_origen':[2]},
        {'fuente':'HA32','cuenta':'299095302','centro':'17','neto_diagnostico':'11747389.00','id_archivo':2212,'lineas_origen':[2]}]}

def test_diagnostico_no_modifica_columnas():
    b=base();r=integrar_host(b,host());assert len(r['columnas'])==11
    assert r['filas']==b['filas'] and r['detalle'][0]['vl_interc']=='11.25'
    assert r['detalle'][0]['host_diagnostico_inc50']['fuentes']['HA22'][0]['neto_diagnostico']=='11747139.00'
    assert r['detalle'][0]['host_diagnostico_inc50']['total_host_homologado'] is None
    assert r['certificado'] is False

def test_jornada_incorrecta():
    h=host();h['id_jornada']=2591
    with pytest.raises(ValueError): integrar_host(base(),h)

def test_sin_registros_no_es_cero():
    h=host();h['filas']=[]
    r=integrar_host(base(),h)
    assert r['detalle'][0]['host_diagnostico_inc50']['fuentes']['HA22']==[]
