import pytest
from app.services.fase2.puente_totales_credibanco_inc46 import construir, MapeoNoAcreditado

def cat():
    import json
    from pathlib import Path
    return json.loads(Path('catalogo_credibanco_inc44.json').read_text(encoding='utf-8'))

def base():
    return {'origen':'POSTGRESQL_SOLO_LECTURA','certificado':False,'id_jornada':1377,
        'resultados':[{'familia':'principal','concepto_literal':'017-CANJE RECIBIDO TARJETA CREDITO PAGOS',
        'concepto':'017-CANJE RECIBIDO TARJETA CREDITO PAGOS','insumo':'CANT',
        'id_archivo':1254,'lineas_origen':[31,32], 'importes':{'vl_interc':'223136015.0000','vl_total':'223136015.0000'}}]}

def mapping():
    return {'concepto':'017-CANJE RECIBIDO TARJETA CREDITO PAGOS','insumo':'CANT',
        'columna_totales':'B','campo_pg':'vl_interc','evidencia':'validacion-funcional-pendiente'}

def test_sin_mapeos_no_inventa_valores():
    r=construir(base(),cat());assert len(r['resultados'])==6
    assert all(x['valor'] is None for x in r['resultados']);assert not r['certificado']

def test_mapeo_explicito_conserva_decimal():
    r=construir(base(),cat(),[mapping()]); x=next(x for x in r['resultados'] if x['celda']=='G58')
    assert x['valor']=='223136015.0000';assert x['certificado'] is False
    assert r['mapeos'][0]['lineas_origen']==[31,32]

def test_sin_evidencia_rechazado():
    m=mapping();m['evidencia']=''
    with pytest.raises(MapeoNoAcreditado): construir(base(),cat(),[m])

def test_duplicado_rechazado():
    with pytest.raises(MapeoNoAcreditado): construir(base(),cat(),[mapping(),mapping()])

def test_familia_auxiliar_no_se_usa():
    b=base();b['resultados'][0]['familia']='cuenta_880'
    with pytest.raises(MapeoNoAcreditado): construir(b,cat(),[mapping()])

def test_campo_ajeno_rechazado():
    m=mapping();m['campo_pg']='cantidad_tipo'
    with pytest.raises(MapeoNoAcreditado): construir(base(),cat(),[m])

def test_nulo_no_es_cero():
    b=base();b['resultados'][0]['importes']['vl_interc']=None
    with pytest.raises(MapeoNoAcreditado): construir(b,cat(),[mapping()])

def test_origen_no_certificado():
    b=base();b['certificado']=True
    with pytest.raises(MapeoNoAcreditado): construir(b,cat())
