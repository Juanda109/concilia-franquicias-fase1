import hashlib
import pytest
from app.services.fase2.integracion_evidencias_host import integrar


def fila(tipo='HA22', concepto='PRUEBA SINTETICA', ident=1, archivo=1136):
    return {'id_archivo': archivo, 'id_host_resultado': ident, 'tx_host': tipo,
            'concepto': concepto, 'cuenta': '900000000281', 'centro': '17',
            'fecha_contable': '2026-10-21', 'valor_debe': 10, 'valor_haber': 12}


def test_sintetico_bloqueado():
    r = integrar([fila()], {}, {})
    assert r['conteos'] == {'BLOQUEADO_SINTETICO': 1}
    assert r['cruces_certificados'] == 0


def test_ha32_sin_origen():
    r = integrar([fila('HA32', None, 2, 1142)], {}, {})
    assert r['conteos'] == {'ORIGEN_NO_VERIFICADO': 1}


def test_hash_correcto_no_autentica(tmp_path):
    p = tmp_path / 'HA22.txt'; p.write_bytes(b'original')
    e = {'tipo_insumo':'HA22','nombre_archivo':p.name,'sha256':hashlib.sha256(b'original').hexdigest(),
         'fecha_contable':'2026-10-21','id_archivo':1136,'fuente_emisora':'HOST',
         'id_autorizacion':'A1','identidad_contrastada_externamente':True}
    r = integrar([fila('HA22', None)], {1136:p}, {1136:e}, fuentes_acreditadas={'HOST':{'A1'}})
    assert r['registros'][0]['estado'] == 'ORIGEN_NO_VERIFICADO'
    assert r['registros'][0]['estado_evidencia'] == 'ORIGEN_NO_VERIFICADO'
    assert not r['registros'][0]['certificable']


def test_sin_archivo_original():
    r = integrar([fila('HA32', None, 2, 1142)], {}, {})
    assert 'ARCHIVO_ORIGINAL_NO_DISPONIBLE' in r['registros'][0]['motivos_evidencia']


def test_id_evidencia_distinto(tmp_path):
    p=tmp_path/'HA22.txt'; p.write_bytes(b'x')
    r=integrar([fila()], {1136:p}, {1136:{'id_archivo':999}})
    assert 'ID_ARCHIVO_NO_COINCIDE' in r['registros'][0]['motivos_evidencia']


def test_rechaza_duplicados():
    with pytest.raises(ValueError, match='DUPLICADO'):
        integrar([fila(),fila()], {}, {})


def test_rechaza_archivos_fuera_poblacion():
    with pytest.raises(ValueError, match='FUERA_DE_POBLACION'):
        integrar([fila()], {999:'x'}, {})


def test_no_sintetico_no_es_verificado():
    r=integrar([fila('HA26','OPERACION')], {}, {})
    assert r['registros'][0]['estado']=='ORIGEN_NO_VERIFICADO'
