"""F2-24: puerta adicional de vigencia/revocacion para atestaciones F2-22.

No altera el contrato firmado de F2-22; un registro de control externo debe estar
firmado por una autoridad de confianza independiente y vinculado a la atestacion.
"""
from __future__ import annotations
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _date(value):
    if not isinstance(value, str):
        raise ValueError('Fecha invalida')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Zona horaria requerida')
    return dt.astimezone(timezone.utc)


def _denegar(motivo):
    return {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': [motivo], 'certificable': False}


def verificar_vigencia_revocacion(atestacion, control, claves_autoridad=None, ahora=None):
    """Verifica control externo Ed25519 firmado y su vinculo a atestacion.

    control = {'datos': {emisor, clave_id, emitida_en, valida_desde,
    valida_hasta, clave_valida_desde, clave_valida_hasta, revocacion_actualizada_en,
    revocacion_valida_hasta, revocada, hash_atestacion}, 'firma_ed25519': base64}.
    claves_autoridad: mapa emisor -> bytes de clave publica Ed25519, provisionado
    independientemente. No se acepta confianza autodeclarada.
    """
    if not isinstance(atestacion, dict) or not isinstance(control, dict):
        return _denegar('EVIDENCIA_AUSENTE')
    if not claves_autoridad:
        return _denegar('SIN_ANCLA_DE_CONFIANZA')
    datos = control.get('datos')
    if not isinstance(datos, dict) or not isinstance(control.get('firma_ed25519'), str):
        return _denegar('CONTROL_INVALIDO')
    campos = {'emisor', 'clave_id', 'emitida_en', 'valida_desde', 'valida_hasta',
              'clave_valida_desde', 'clave_valida_hasta', 'revocacion_actualizada_en',
              'revocacion_valida_hasta', 'revocada', 'hash_atestacion'}
    if set(datos) != campos or type(datos['revocada']) is not bool:
        return _denegar('ESQUEMA_INVALIDO')
    emisor = datos['emisor']
    if not isinstance(emisor, str) or emisor not in claves_autoridad:
        return _denegar('AUTORIDAD_NO_ACREDITADA')
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(claves_autoridad[emisor])
        key.verify(base64.b64decode(control['firma_ed25519'], validate=True), _canonical(datos))
    except Exception:
        return _denegar('FIRMA_CONTROL_INVALIDA')
    if hashlib.sha256(_canonical(atestacion)).hexdigest() != datos['hash_atestacion']:
        return _denegar('ATESTACION_NO_COINCIDE')
    try:
        ahora = datetime.now(timezone.utc) if ahora is None else ahora
        if ahora.tzinfo is None:
            return _denegar('RELOJ_SIN_ZONA')
        ahora = ahora.astimezone(timezone.utc)
        emision = _date(datos['emitida_en'])
        inicio, fin = _date(datos['valida_desde']), _date(datos['valida_hasta'])
        clave_inicio, clave_fin = _date(datos['clave_valida_desde']), _date(datos['clave_valida_hasta'])
        rev_inicio, rev_fin = _date(datos['revocacion_actualizada_en']), _date(datos['revocacion_valida_hasta'])
    except (ValueError, TypeError, OverflowError):
        return _denegar('FECHAS_INVALIDAS')
    if emision > ahora or emision < inicio or emision > fin:
        return _denegar('EMISION_INVALIDA')
    if not (inicio <= ahora <= fin and clave_inicio <= ahora <= clave_fin):
        return _denegar('VIGENCIA_INVALIDA')
    if not (rev_inicio <= ahora <= rev_fin) or rev_inicio < emision:
        return _denegar('REVOCACION_NO_VIGENTE')
    if datos['revocada']:
        return _denegar('CREDENCIAL_REVOCADA')
    return {'estado': 'CONTROL_VIGENCIA_VALIDADO', 'motivos': [], 'certificable': False,
            'emisor_control': emisor, 'clave_id': datos['clave_id']}
