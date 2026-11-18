from decimal import Decimal
import pytest
from app.services.fase2.calculo_canje_pg_inc41 import adaptar, procesar


def fila(linea, **extra):
    d=dict(id_jornada=1377,id_archivo=1254,tipo_archivo='CANT',linea_origen=linea,
           tx='22',tipo='01',cuenta='017-CANJE RECIBIDO TARJETA CREDITO',
           cuentas_comisiones='',cuenta_880='',vl_total=Decimal('100.25'),
           vl_interc=Decimal('100.25'),comision_op_exitosas=None,
           tii_recibida_emisor_visa_op_rever_ventas=None)
    d.update(extra)
    return d


def test_importes_reales_por_concepto():
    r=procesar([fila(1),fila(2,vl_total=Decimal('10.10'))],1377)
    p=next(x for x in r['resultados'] if x['familia']=='principal')
    assert p['importes']['vl_total']==Decimal('110.35')
    assert p['lineas_origen']==[1,2]
    assert p['cuenta_host'] is None and not p['certificado']


def test_nulos_no_se_convierten_a_cero():
    r=procesar([fila(1)],1377)
    assert r['conteos']['detalle']==1
    assert all(x['nulos_familia']['COMISION OP EXITOSAS']==1 for x in r['resultados'])
    assert adaptar(fila(1))['COMISION OP EXITOSAS'] is None


def test_totales_excluidos():
    r=procesar([fila(1,tx='Totales'),fila(2)],1377)
    assert r['conteos']==dict(entrada=2,detalle=1,control=1)


def test_duplicados_bloqueados():
    with pytest.raises(ValueError,match='Duplicado'): procesar([fila(1),fila(1)],1377)


def test_jornada_cruzada():
    with pytest.raises(ValueError,match='Jornada cruzada'): procesar([fila(1,id_jornada=2060)],1377)


def test_no_mezclar_archivos():
    r=procesar([fila(1),fila(1,id_archivo=1253,tipo_archivo='CAET')],1377)
    assert len([x for x in r['resultados'] if x['familia']=='principal'])==2


def test_conteo_declarado():
    with pytest.raises(ValueError,match='Conteo inconsistente'):
        procesar([fila(1)],1377,[dict(id_archivo=1254,tipo_archivo='CANT',estado='PROCESADO',total_registros=186)])


def test_conteo_correcto():
    r=procesar([fila(1)],1377,[dict(id_archivo=1254,tipo_archivo='CANT',estado='PROCESADO',total_registros=1)])
    assert r['archivos'][0]['leidos']==1


def test_jornada_vacia():
    r=procesar([],2060,[dict(id_archivo=1738,tipo_archivo='CAET',estado='RECIBIDO',total_registros=0)])
    assert r['resultados']==[] and r['archivos'][0]['leidos']==0


def test_no_otros_insumos():
    with pytest.raises(ValueError,match='Insumo no permitido'): procesar([fila(1,tipo_archivo='DEPO')],1377)


def test_no_infiera_cuenta_host():
    r=procesar([fila(1,cuenta='196095001830')],1377)
    assert all(x['cuenta_host'] is None for x in r['resultados'])


def test_decimal_invalido():
    with pytest.raises(ValueError): procesar([fila(1,vl_total='invalido')],1377)
