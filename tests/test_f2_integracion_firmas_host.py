from app.services.fase2.integracion_firmas_host import integrar_firmas
import pytest


def fila():
    return {'id_archivo': 1136, 'id_host_resultado': 1, 'tx_host': 'HA22', 'cuenta': '900000000281',
            'centro': '17', 'fecha_contable': '2026-10-21', 'concepto': 'PRUEBA SINTETICA',
            'valor_debe': 1, 'valor_haber': 2}


def test_sin_archivo():
    r = integrar_firmas([fila()], {}, {}, {})
    assert r['registros'][0]['estado_firma'] == 'ORIGEN_NO_VERIFICADO'
    assert r['cruces_certificados'] == 0


def test_sin_revocacion(tmp_path):
    p = tmp_path / 'x.txt'; p.write_text('test')
    r = integrar_firmas([fila()], {1136:p}, {}, {})
    assert r['registros'][0]['motivos_firma'] == ['REVOCACION_NO_VERIFICABLE']


def test_revocado(tmp_path):
    p = tmp_path / 'x.txt'; p.write_text('test')
    att = {'datos': {'emisor':'A','id_autorizacion':'B'}}
    r = integrar_firmas([fila()], {1136:p}, {}, {1136:att}, claves_revocadas={'A'}, autorizaciones_revocadas=set())
    assert r['registros'][0]['motivos_firma'] == ['CREDENCIAL_REVOCADA']


def test_sin_ancla(tmp_path):
    p = tmp_path / 'x.txt'; p.write_text('test')
    r = integrar_firmas([fila()], {1136:p}, {}, {}, claves_revocadas=set(), autorizaciones_revocadas=set())
    assert r['registros'][0]['estado_firma'] == 'ORIGEN_NO_VERIFICADO'


def test_fuera_poblacion():
    with pytest.raises(ValueError, match='FUERA_DE_POBLACION'):
        integrar_firmas([fila()], {}, {}, {999:{}})
