import pytest
from app.services.fase2.integracion_host_canje import evaluar, clasificar_host

def test_sintetico():
    assert clasificar_host({'concepto':'PRUEBA SINTETICA','tx_host':'HA22'}) == 'BLOQUEADO_SINTETICO'

def test_ha32_sin_etiqueta():
    assert clasificar_host({'concepto':None,'tx_host':'HA32'}) == 'ORIGEN_NO_VERIFICADO'

def test_matriz_vacia():
    r = evaluar([{'id_archivo':1136,'id_host_resultado':1,'concepto':'PRUEBA SINTETICA'}], [], {'fase':2,'reglas':[]})
    assert r['cruces_aprobados'] == 0

def test_bloqueo_regla_aprobada():
    with pytest.raises(ValueError):
        evaluar([], [], {'fase':2,'reglas':[{'estado_regla':'APROBADA'}]})

def test_duplicados():
    filas = [{'id_archivo':1136,'id_host_resultado':1}]*2
    with pytest.raises(ValueError):
        evaluar(filas, [], {'fase':2,'reglas':[]})

def test_matriz_invalida():
    with pytest.raises(ValueError):
        evaluar([], [], {'fase':1,'reglas':[]})
