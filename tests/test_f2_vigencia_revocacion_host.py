import base64
import hashlib
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pathlib import Path
import importlib.util
try:
    from app.services.fase2.vigencia_revocacion_host import verificar_vigencia_revocacion, _canonical
except ModuleNotFoundError:
    spec = importlib.util.spec_from_file_location("vigencia_revocacion_host", Path(__file__).with_name("vigencia_revocacion_host.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    verificar_vigencia_revocacion, _canonical = mod.verificar_vigencia_revocacion, mod._canonical

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)

def fixture():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    at = {'datos': {'id_archivo': 123}, 'firma_ed25519': 'test'}
    datos = dict(emisor='autoridad', clave_id='clave1', emitida_en='2026-10-22T00:00:00Z',
                 valida_desde='2026-10-20T00:00:00Z', valida_hasta='2026-10-30T00:00:00Z',
                 clave_valida_desde='2026-10-01T00:00:00Z', clave_valida_hasta='2026-11-01T00:00:00Z',
                 revocacion_actualizada_en='2026-10-22T00:00:00Z', revocacion_valida_hasta='2026-10-24T00:00:00Z',
                 revocada=False, hash_atestacion=hashlib.sha256(_canonical(at)).hexdigest())
    def sign():
        return {'datos': datos.copy(), 'firma_ed25519': base64.b64encode(priv.sign(_canonical(datos))).decode()}
    return at, datos, sign, {'autoridad': pub}

def test_valido_no_certifica():
    a, d, s, keys = fixture()
    r = verificar_vigencia_revocacion(a, s(), keys, NOW)
    assert r['estado'] == 'CONTROL_VIGENCIA_VALIDADO' and not r['certificable']

def test_sin_confianza():
    a, d, s, keys = fixture()
    assert verificar_vigencia_revocacion(a, s(), {}, NOW)['estado'] == 'ORIGEN_NO_VERIFICADO'

def test_firma_alterada():
    a, d, s, keys = fixture()
    c = s(); c['datos']['revocada'] = True
    assert verificar_vigencia_revocacion(a, c, keys, NOW)['motivos'] == ['FIRMA_CONTROL_INVALIDA']

def test_revocada():
    a, d, s, keys = fixture(); d['revocada'] = True
    assert verificar_vigencia_revocacion(a, s(), keys, NOW)['motivos'] == ['CREDENCIAL_REVOCADA']

def test_revocacion_vencida():
    a, d, s, keys = fixture(); d['revocacion_valida_hasta'] = '2026-10-22T12:00:00Z'
    assert verificar_vigencia_revocacion(a, s(), keys, NOW)['motivos'] == ['REVOCACION_NO_VIGENTE']

def test_atestacion_diferente():
    a, d, s, keys = fixture()
    assert verificar_vigencia_revocacion({'otro': 1}, s(), keys, NOW)['motivos'] == ['ATESTACION_NO_COINCIDE']

def test_vigencia_expirada():
    a, d, s, keys = fixture(); d['valida_hasta'] = '2026-10-22T12:00:00Z'
    assert verificar_vigencia_revocacion(a, s(), keys, NOW)['motivos'] == ['VIGENCIA_INVALIDA']

def test_emision_futura():
    a, d, s, keys = fixture(); d['emitida_en'] = '2026-10-24T00:00:00Z'
    assert verificar_vigencia_revocacion(a, s(), keys, NOW)['motivos'] == ['EMISION_INVALIDA']

def test_fecha_sin_zona():
    a, d, s, keys = fixture(); d['valida_desde'] = '2026-10-20T00:00:00'
    assert verificar_vigencia_revocacion(a, s(), keys, NOW)['motivos'] == ['FECHAS_INVALIDAS']
