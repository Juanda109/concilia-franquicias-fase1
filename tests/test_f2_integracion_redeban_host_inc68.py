from datetime import date
from unittest.mock import Mock
import pytest
from app.services.fase2.integracion_redeban_host_inc68 import diagnosticar_jornada, leer_host_jornada


def _reporte(_):
    return {'certificado':False,'diagnostico_redeban_inc64':{'certificado':False,'cantidad_filas':2,'detalle':[
        {'estado':'CALCULO_DIAGNOSTICO','cuenta_contable':'299095508','neto_diagnostico':'10','fila_excel':8},
        {'estado':'PARTIDA_MANUAL_NO_HOMOLOGADA','cuenta_contable':'196095001035','neto_diagnostico':None,'fila_excel':3247}]}}


def _datos():
    return {'299095508':{'regla_consulta':'ANTERIOR_INICIO'}}, {'299095508':{'franquicia_relacionada':'REDEBAN','estado_homologacion':'PENDIENTE_VALIDACION_MONETARIA'}}


def test_host_pendiente_no_diferencias():
    c,h=_datos()
    r=diagnosticar_jornada(6466,consultar_reporte=_reporte,leer_host=lambda _: (date(2026,10,2),[],'HOST_PENDIENTE'),catalogo=c,homologaciones=h)
    assert r['estado']=='HOST_PENDIENTE' and r['cuentas']==[] and r['diferencias_calculadas']==0
    assert r['certificado'] is False


def test_host_sintetico_no_certifica():
    c,h=_datos()
    host=[{'fuente':'HA22','cuenta':'299095508','centro':'17','fecha_contable':'2026-10-02','debe':'10','haber':'0','sintetico':True,'linea':2}]
    r=diagnosticar_jornada(6466,consultar_reporte=_reporte,leer_host=lambda _: (date(2026,10,2),host,'HOST_DISPONIBLE'),catalogo=c,homologaciones=h)
    assert r['certificado'] is False and r['cuentas'][0]['diferencia'] is None


def test_ha32_no_se_suma():
    c,h=_datos()
    host=[{'fuente':'HA32','cuenta':'299095508','centro':'17','fecha_contable':'2026-10-02','debe':'10','haber':'0','linea':2}]
    r=diagnosticar_jornada(6466,consultar_reporte=_reporte,leer_host=lambda _: (date(2026,10,2),host,'HOST_DISPONIBLE'),catalogo=c,homologaciones=h)
    assert r['host_ha32_excluido_de_suma']==1
    assert r['cuentas'][0]['diferencia'] is None


def test_rechaza_reporte_certificado():
    c,h=_datos()
    with pytest.raises(ValueError):
        diagnosticar_jornada(6466,consultar_reporte=lambda _: {'certificado':True},leer_host=lambda _: (date(2026,10,2),[],'HOST_PENDIENTE'),catalogo=c,homologaciones=h)


def test_rechaza_jornada_invalida():
    with pytest.raises(ValueError):
        leer_host_jornada(0)
