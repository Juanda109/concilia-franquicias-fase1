import pytest
from app.services.fase2.reporte_credibanco_inc43 import construir


def informe():
    def g(familia, concepto, valores):
        return {'id_jornada':1377,'id_archivo':1254,'franquicia':'CREDIBANCO','insumo':'CANT',
                'familia':familia,'concepto_literal':concepto,'importes':valores,
                'lineas_origen':[31,32] if familia=='principal' else [31,32], 'certificado':False}
    return {'id_jornada':1377,'origen':'POSTGRESQL_SOLO_LECTURA','certificado':False,
            'resultados':[g('principal','CONCEPTO PRUEBA',{'vl_interc':'25','vl_total':'30'}),
                          g('cuenta_880','',{'vl_interc':'25','vl_total':'30'})],
            'conteos':{'entrada':2}}


def regla():
    return {'insumo':'CANT','familia':'principal','concepto_literal':'CONCEPTO PRUEBA',
            'cuenta_host':'196095001830','evidencia':'Plantilla hoja X celda Y: ejemplo de prueba, no regla productiva',
            'campo_importe':'vl_interc'}


def test_sin_matriz_no_inventa_cuenta():
    r=construir(informe()); assert len(r['filas'])==1
    assert r['filas'][0]['cuenta'] is None and r['filas'][0]['valor_franquicia'] is None


def test_con_regla_explicita_importe():
    r=construir(informe(),[regla()]); f=r['filas'][0]
    assert f['cuenta']=='196095001830' and f['valor_franquicia']=='25'
    assert f['estado_conciliacion']=='CALCULADO_NO_HOMOLOGADO'


def test_no_doble_conteo():
    r=construir(informe(),[regla()]); assert len(r['filas'])==1
    assert any(x['uso']=='SOLO_TRAZABILIDAD_NO_SUMAR' for x in r['detalle'])


def test_contrato_11_columnas():
    r=construir(informe()); assert len(r['columnas'])==11
    assert list(r['filas'][0])==r['columnas']


def test_no_host_no_certificacion():
    r=construir(informe(),[regla()]); f=r['filas'][0]
    assert all(f[k] is None for k in ('ha22','ha26','ha32','total_host','diferencia'))
    assert not r['certificado'] and not any(r['indicadores'].values())


def test_rechaza_regla_sin_evidencia():
    x=regla();x['evidencia']=''
    with pytest.raises(ValueError): construir(informe(),[x])


def test_rechaza_cuenta_invalida():
    x=regla();x['cuenta_host']='017-ABC'
    with pytest.raises(ValueError): construir(informe(),[x])


def test_rechaza_reporte_certificado():
    x=informe();x['certificado']=True
    with pytest.raises(ValueError): construir(x)


def test_rechaza_grupo_duplicado():
    x=informe();x['resultados'].append(dict(x['resultados'][0]))
    with pytest.raises(ValueError): construir(x)


def test_rechaza_reglas_ambiguas():
    with pytest.raises(ValueError): construir(informe(),[regla(),regla()])


def test_preserva_cero_real():
    x=informe();x['resultados'][0]['importes']['vl_interc']='0'
    assert construir(x,[regla()])['filas'][0]['valor_franquicia']=='0'


def test_preserva_nulo():
    x=informe();x['resultados'][0]['importes']['vl_interc']=None
    r=construir(x,[regla()]);assert r['filas'][0]['valor_franquicia'] is None
