import pytest
from app.services.fase2.diagnostico_procedencia_host import diagnosticar


def fila(tipo, id_, archivo, concepto=None, cuenta='900000000281'):
    return dict(tx_host=tipo, id_host_resultado=id_, id_archivo=archivo,
                cuenta=cuenta, centro='17', fecha_contable='2026-10-21',
                concepto=concepto, valor_debe='2910.00', valor_haber='2912.00')


def test_sintetico_ha22():
    r=diagnosticar([fila('HA22',1,1136,'PRUEBA SINTETICA')])
    assert r['conteos']=={'BLOQUEADO_SINTETICO':1}


def test_ha32_no_verificado():
    r=diagnosticar([fila('HA32',2,1142)])
    assert r['conteos']=={'ORIGEN_NO_VERIFICADO':1}


def test_correlacion_sin_empresa_no_certifica():
    r=diagnosticar([fila('HA22',1,1136,'PRUEBA SINTETICA'),fila('HA32',2,1142)])
    assert r['conteos']=={'BLOQUEADO_SINTETICO':1,'ORIGEN_NO_VERIFICADO':1}
    assert r['cruces_certificados']==0


def test_rechaza_duplicados():
    with pytest.raises(ValueError, match='duplicados'):
        diagnosticar([fila('HA22',1,1136),fila('HA22',1,1136)])


def test_rechaza_fuente_incorrecta():
    with pytest.raises(ValueError, match='inesperados'):
        diagnosticar([fila('HA22',1,1142)])


def test_rechaza_fecha():
    x=fila('HA22',1,1136);x['fecha_contable']='2026-10-20'
    with pytest.raises(ValueError, match='Fecha'):
        diagnosticar([x])


def test_no_certifica_sin_evidencia():
    r=diagnosticar([fila('HA26',1,1141)])
    assert r['detalles'][0]['certificable_por_procedencia'] is False
