from decimal import Decimal
import pytest
from app.services.fase2.agrupacion_credibanco_inc40 import agrupar

def fila(linea=1, **kw):
    x = dict(id_jornada=1377,id_archivo=1254,tipo_archivo='CANT',linea_origen=linea,
             tx='02',cuenta='017-RECH CJE',vl_total=100,vl_interc=80,
             comision_op_exitosas=None,tii_recibida_emisor_visa_op_rever_ventas=0)
    x.update(kw)
    return x

def test_pendiente_sin_asignacion():
    r=agrupar([fila()]); assert r['conteos']['sin_cuenta']==1 and not r['grupos']
    assert r['pendientes'][0]['estado']=='PENDIENTE_ASIGNACION_CONTABLE'

def test_cuenta_asignada_y_nulos():
    r=agrupar([fila()],{(1254,1):'196095001830'})
    g=r['grupos'][0]; assert g['cuenta']=='196095001830'
    assert g['sumas']['vl_interc']==Decimal(80)
    assert g['nulos']['comision_op_exitosas']==1
    assert g['sumas']['tii_recibida_emisor_visa_op_rever_ventas']==0
    assert g['diferencia'] is None and not g['certificado']

def test_agrega_misma_cuenta_concepto():
    r=agrupar([fila(),fila(2,vl_total=20)],{(1254,1):'196095001830',(1254,2):'196095001830'})
    assert len(r['grupos'])==1 and r['grupos'][0]['sumas']['vl_total']==120
    assert r['grupos'][0]['lineas_origen']==[1,2]

def test_no_mezcla_conceptos():
    r=agrupar([fila(),fila(2,cuenta='OTRO')],{(1254,1):'196095001830',(1254,2):'196095001830'})
    assert len(r['grupos'])==2

def test_control_no_suma():
    r=agrupar([fila(tx='Totales')]); assert r['conteos']['control']==1 and not r['grupos']

def test_duplicado_bloqueado():
    with pytest.raises(ValueError,match='duplicada'): agrupar([fila(),fila()])

def test_no_asignacion_puc_invalida():
    with pytest.raises(ValueError,match='contable'): agrupar([fila()],{(1254,1):'017-RECH'})

def test_no_numerico():
    with pytest.raises(ValueError,match='numerico'): agrupar([fila(vl_total='abc')],{(1254,1):'196095001830'})

def test_no_infinito():
    with pytest.raises(ValueError,match='finito'): agrupar([fila(vl_total='Infinity')],{(1254,1):'196095001830'})

def test_no_otras_franquicias():
    with pytest.raises(ValueError,match='CAET/CANT'): agrupar([fila(tipo_archivo='PMD')])

def test_no_mezcla_archivos():
    r=agrupar([fila(),fila(2,id_archivo=1253,tipo_archivo='CAET')],{(1254,1):'196095001830',(1253,2):'196095001830'})
    assert len(r['grupos'])==2

def test_jornada_obligatoria():
    with pytest.raises(ValueError,match='id_jornada'): agrupar([fila(id_jornada=None)])


def test_documento_tecnico_no_es_entrada_operativa():
    r = agrupar([fila()])
    assert any('no es un insumo operativo' in a for a in r['advertencias'])
    assert all('CE01' not in p['estado'] for p in r['pendientes'])
