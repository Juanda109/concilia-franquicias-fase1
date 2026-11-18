"""F2-22: comprueba atestaciones firmadas por emisor confiable, sin certificar conciliaciones.

La clave pública confiable se administra fuera del paquete y de la atestación.
"""
from __future__ import annotations
import base64
import hashlib
import json
from datetime import date
from pathlib import Path

FUENTES = {'HA22', 'HA26', 'HA32'}
CAMPOS = ('id_archivo', 'tipo_insumo', 'nombre_archivo', 'fecha_contable', 'sha256',
          'emisor', 'id_autorizacion', 'alcance_autorizacion')


def _fallo(motivo: str) -> dict:
    return {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': [motivo], 'certificable': False}


def verificar_atestacion(ruta_archivo: str | Path, atestacion: dict | None,
                         claves_confiables: dict[str, bytes] | None = None,
                         autorizaciones_externas: set[str] | None = None) -> dict:
    """Valida firma Ed25519 y autorización externa independiente (IDs confiables).

    La mera firma acredita al emisor de la atestación, no su autoridad funcional.
    La aplicación consumidora NO debe cambiar estados de BD ni activar reglas.
    """
    ruta = Path(ruta_archivo)
    if not ruta.is_file():
        return _fallo('ARCHIVO_NO_ENCONTRADO')
    if not isinstance(atestacion, dict):
        return _fallo('ATESTACION_AUSENTE')
    if not claves_confiables:
        return _fallo('SIN_ANCLA_DE_CONFIANZA')
    cuerpo = atestacion.get('datos')
    firma = atestacion.get('firma_ed25519')
    if not isinstance(cuerpo, dict) or not isinstance(firma, str):
        return _fallo('ATESTACION_INVALIDA')
    if set(cuerpo) != set(CAMPOS):
        return _fallo('ESQUEMA_INVALIDO')
    emisor = cuerpo['emisor']
    if not isinstance(emisor, str) or emisor not in claves_confiables:
        return _fallo('EMISOR_NO_ACREDITADO')
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        clave = Ed25519PublicKey.from_public_bytes(claves_confiables[emisor])
        firma_bytes = base64.b64decode(firma, validate=True)
        mensaje = json.dumps(cuerpo, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode('utf-8')
        clave.verify(firma_bytes, mensaje)
    except (ValueError, TypeError, ImportError, Exception) as exc:
        # Nunca devolver material criptográfico ni datos de atestación en el error.
        return _fallo('FIRMA_INVALIDA_O_VERIFICADOR_NO_DISPONIBLE')
    if cuerpo['tipo_insumo'] not in FUENTES or cuerpo['nombre_archivo'] != ruta.name:
        return _fallo('IDENTIDAD_NO_COINCIDE')
    if type(cuerpo['id_archivo']) is not int or cuerpo['id_archivo'] <= 0:
        return _fallo('ID_ARCHIVO_INVALIDO')
    try:
        date.fromisoformat(cuerpo['fecha_contable'])
    except (ValueError, TypeError):
        return _fallo('FECHA_INVALIDA')
    if cuerpo['alcance_autorizacion'] != 'PROCEDENCIA_HOST':
        return _fallo('ALCANCE_NO_AUTORIZADO')
    if not autorizaciones_externas or cuerpo['id_autorizacion'] not in autorizaciones_externas:
        return _fallo('AUTORIZACION_NO_ACREDITADA')
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloque)
    import hmac
    esperado = cuerpo['sha256']
    if not isinstance(esperado, str) or not hmac.compare_digest(h.hexdigest(), esperado):
        return _fallo('HASH_NO_COINCIDE')
    return {'estado': 'EVIDENCIA_EXTERNA_VERIFICADA', 'motivos': [],
            'certificable': False, 'id_archivo': cuerpo['id_archivo'],
            'emisor': emisor, 'id_autorizacion': cuerpo['id_autorizacion']}
