import pytest
from app.services.fase2.clasificacion_depo_inc56h2 import construir_clasificados

FILAS = [{'numero_linea':1,'TIPO_MOVIMIENTO':'02','VALOR_TOTAL_CRUDO':'000000100'},
         {'numero_linea':2,'TIPO_MOVIMIENTO':'05','VALOR_TOTAL_CRUDO':'000000200'}]


def test_pendientes_sin_aprobacion():
    datos, pendientes = construir_clasificados('depo.txt', FILAS, {})
    assert datos == [] and len(pendientes) == 2


def test_aprobacion_explicita_trazable():
    datos, pendientes = construir_clasificados('depo.txt', FILAS, {1:{
        'concepto_verificado':'DEPOSITO_NACIONAL', 'clasificacion_aprobada':True,
        'regla_version':'VALIDADA-PRUEBA', 'importe_crudo':'000000100'}})
    assert datos[0]['linea_origen'] == 1 and len(pendientes) == 1


@pytest.mark.parametrize('aprobacion', [
    {'concepto_verificado':'DEPOSITO_NACIONAL','clasificacion_aprobada':True,'regla_version':'R1','importe_crudo':'999'},
    {'concepto_verificado':'DEPOSITO_NACIONAL','clasificacion_aprobada':True,'regla_version':'','importe_crudo':'000000100'},
    {'concepto_verificado':'NO_EXISTE','clasificacion_aprobada':True,'regla_version':'R1','importe_crudo':'000000100'},
])
def test_rechaza_aprobaciones_invalidas(aprobacion):
    with pytest.raises(ValueError):
        construir_clasificados('depo.txt', FILAS, {1:aprobacion})


def test_control_resumen_no_aprobable():
    with pytest.raises(ValueError):
        construir_clasificados('depo.txt', FILAS, {2:{
            'concepto_verificado':'DEPOSITO_NACIONAL','clasificacion_aprobada':True,
            'regla_version':'R1','importe_crudo':'000000200'}})


def test_linea_inexistente_rechazada():
    with pytest.raises(ValueError):
        construir_clasificados('depo.txt', FILAS, {3:{}})
