import copy
import pytest
from app.services.fase2.motor_desagregacion_redeban import validar_desagregacion, MEDIDAS


def datos():
    g = {'padre':'1.1', 'filas_excel':[8,9], 'operaciones':2,
         'registros_pmd_reales':[{'medidas':{m:'0' for m in MEDIDAS}}]}
    g['registros_pmd_reales'][0]['medidas']['DEBITO_VALOR']='30'
    return ({'id_jornada':6466,'grupos':[g],'certificado':False},
            {'id_jornada':6466,'matriz':[{'fila_excel':8},{'fila_excel':9}],'certificado':False})


def asignacion(fila,importe,tx):
    return {'padre':'1.1','fila_excel':fila,'medida':'DEBITO_VALOR',
            'importe':importe,'id_evidencia':'doc','id_regla':'regla',
            'fecha_contable':'2026-10-02','fuente':'DETALLE','id_transaccion':tx}


def test_no_infiere_importes():
    c,m=datos();r=validar_desagregacion(c,m,[])
    assert r['homologados']==0 and r['certificado'] is False


def test_bloquea_duplicidad():
    c,m=datos()
    with pytest.raises(ValueError,match='mas de una vez'):
        validar_desagregacion(c,m,[asignacion(8,'10','X'),asignacion(9,'20','X')])


def test_sin_aprobacion_no_homologa_aun_si_conserva():
    c,m=datos();r=validar_desagregacion(c,m,[asignacion(8,'10','X'),asignacion(9,'20','Y')])
    assert r['homologados']==0
    assert r['grupos'][0]['medidas'][0]['conserva'] is True


def test_rechaza_fecha():
    c,m=datos();a=asignacion(8,'10','X');a['fecha_contable']='2026-09-23'
    with pytest.raises(ValueError,match='Fecha'):
        validar_desagregacion(c,m,[a])


def test_aprobacion_no_suple_medidas_faltantes():
    c,m=datos();ap={'1.1':{'aprobado':True,'id_regla':'r','evidencia_exclusividad':'doc',
                          'fecha_contable':'2026-10-02','fuente':'DETALLE'}}
    r=validar_desagregacion(c,m,[asignacion(8,'10','X'),asignacion(9,'20','Y')],aprobaciones=ap)
    assert r['homologados']==0
