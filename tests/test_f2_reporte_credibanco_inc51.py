from app.services.fase2.reporte_credibanco_inc51 import enriquecer
import pytest

def base():
    return {'id_jornada':2637,'certificado':False,'columnas':[str(i) for i in range(11)],
            'filas':[{'cuenta':'299095302','valor_franquicia':None,'total_host':None,'diferencia':None}],
            'detalle':[{'concepto':'CONCEPTO_A','cantidad_operaciones':2,'vl_interc':'10.00'}],
            'totales_diagnosticos':[{'A':'CONCEPTO_A','B':2,'C':'10.00','D':'12.00'},
                                   {'A':'SIN_MAPEO','B':4,'C':'20.00','D':'22.00','archivos':[2208],'lineas_origen':[1,2]}]}

def test_sin_correspondencia():
    b=base();r=enriquecer(b)
    s=r['diagnostico_credibanco_inc51']['agregados_sin_correspondencia']
    assert len(s)==1 and s[0]['concepto_origen']=='SIN_MAPEO' and s[0]['archivos_origen']==[2208]
    assert len(r['columnas'])==11 and r['filas']==b['filas']
    assert r['detalle'][0]['vl_interc']=='10.00' and r['certificado'] is False

def test_no_cero_ni_falsa_homologacion():
    r=enriquecer(base()); assert r['filas'][0]['valor_franquicia'] is None
    assert r['filas'][0]['total_host'] is None and r['filas'][0]['diferencia'] is None
    assert r['diagnostico_credibanco_inc51']['depo']['estado']=='PENDIENTE_REGLAS_FASE_2'

def test_rechaza_certificado():
    b=base();b['certificado']=True
    with pytest.raises(ValueError): enriquecer(b)
