from unittest.mock import patch
import pytest
from app.services.fase2.evaluacion_integral_host import evaluar_integral

FILAS = [{'id_archivo': 1136}, {'id_archivo': 1142}]


def base_simulada(*args, **kwargs):
    return {'registros': [
        {'id_archivo': 1136, 'estado': 'BLOQUEADO_SINTETICO', 'estado_firma': 'ORIGEN_NO_VERIFICADO', 'motivos_firma': []},
        {'id_archivo': 1142, 'estado': 'ORIGEN_NO_VERIFICADO', 'estado_firma': 'EVIDENCIA_EXTERNA_VERIFICADA', 'motivos_firma': []},
    ], 'advertencias': [], 'cruces_certificados': 0}


def ejecutar(controles=None, atestaciones=None, **kwargs):
    with patch('app.services.fase2.evaluacion_integral_host.integrar_firmas', side_effect=base_simulada):
        return evaluar_integral(FILAS, {}, {}, atestaciones or {}, controles or {}, **kwargs)


def test_sin_control_falla_cerrado():
    r = ejecutar()
    assert r['conteos_vigencia'] == {'ORIGEN_NO_VERIFICADO': 2}
    assert r['cruces_certificados'] == 0


def test_control_fuera_poblacion_rechazado():
    with pytest.raises(ValueError, match='CONTROL_FUERA_DE_POBLACION'):
        ejecutar(controles={999: {}})


def test_firma_valida_no_suplanta_vigencia():
    r = ejecutar(atestaciones={1142: {}}, controles={1142: {}})
    assert not r['registros'][1]['evidencia_integral_validada']


def test_doble_control_valido_no_certifica():
    with patch('app.services.fase2.evaluacion_integral_host.verificar_vigencia_revocacion', return_value={'estado': 'CONTROL_VIGENCIA_VALIDADO', 'motivos': []}):
        r = ejecutar(atestaciones={1142: {}}, controles={1142: {}})
    assert r['registros'][1]['evidencia_integral_validada']
    assert r['registros'][1]['estado'] == 'ORIGEN_NO_VERIFICADO'
    assert r['registros'][1]['certificable'] is False
    assert r['cruces_certificados'] == 0


def test_sintetico_siempre_bloqueado():
    with patch('app.services.fase2.evaluacion_integral_host.verificar_vigencia_revocacion', return_value={'estado': 'CONTROL_VIGENCIA_VALIDADO', 'motivos': []}):
        r = ejecutar(atestaciones={1136: {}}, controles={1136: {}})
    assert r['registros'][0]['estado'] == 'BLOQUEADO_SINTETICO'
    assert r['registros'][0]['certificable'] is False
