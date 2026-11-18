import base64
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from app.services.fase2.acreditacion_firmada_host import verificar_atestacion


def caso(tmp_path):
    archivo = tmp_path / 'DESCARHA22_F261021.TXT'
    archivo.write_bytes(b'contenido de prueba')
    privada = Ed25519PrivateKey.generate()
    publica = privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    datos = {'id_archivo': 1136, 'tipo_insumo': 'HA22', 'nombre_archivo': archivo.name,
             'fecha_contable': '2026-10-21', 'sha256': hashlib.sha256(archivo.read_bytes()).hexdigest(),
             'emisor': 'HOST-FIRMANTE', 'id_autorizacion': 'APROB-001',
             'alcance_autorizacion': 'PROCEDENCIA_HOST'}
    def firmar():
        msg = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        return {'datos': dict(datos), 'firma_ed25519': base64.b64encode(privada.sign(msg)).decode()}
    return archivo, datos, firmar, {'HOST-FIRMANTE': publica}


def test_sin_atestacion(tmp_path):
    a, d, f, claves = caso(tmp_path)
    assert verificar_atestacion(a, None, claves)['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_sin_ancla(tmp_path):
    a, d, f, claves = caso(tmp_path)
    assert verificar_atestacion(a, f())['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_firma_alterada(tmp_path):
    a, d, f, claves = caso(tmp_path)
    att = f(); att['datos']['id_archivo'] = 999
    assert verificar_atestacion(a, att, claves, {'APROB-001'})['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_autorizacion_ausente(tmp_path):
    a, d, f, claves = caso(tmp_path)
    assert verificar_atestacion(a, f(), claves)['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_hash_alterado(tmp_path):
    a, d, f, claves = caso(tmp_path)
    a.write_bytes(b'alterado')
    assert verificar_atestacion(a, f(), claves, {'APROB-001'})['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_firma_y_autorizacion_validas_no_certifican(tmp_path):
    a, d, f, claves = caso(tmp_path)
    r = verificar_atestacion(a, f(), claves, {'APROB-001'})
    assert r['estado'] == 'EVIDENCIA_EXTERNA_VERIFICADA'
    assert r['certificable'] is False


def test_emisor_desconocido(tmp_path):
    a, d, f, claves = caso(tmp_path)
    assert verificar_atestacion(a, f(), {'OTRO': next(iter(claves.values()))}, {'APROB-001'})['estado'] == 'ORIGEN_NO_VERIFICADO'


def test_alcance_invalido(tmp_path):
    a, d, f, claves = caso(tmp_path)
    d['alcance_autorizacion'] = 'CONCILIACION'
    assert verificar_atestacion(a, f(), claves, {'APROB-001'})['estado'] == 'ORIGEN_NO_VERIFICADO'
