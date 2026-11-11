"""Validación conservadora de evidencia externa Host; no concede autenticidad por hash."""
from __future__ import annotations
import hashlib
import hmac
from datetime import date
from pathlib import Path

FUENTES = frozenset({'HA22', 'HA26', 'HA32'})


def sha256_archivo(ruta: str | Path) -> str:
    h = hashlib.sha256()
    with open(ruta, 'rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            h.update(bloque)
    return h.hexdigest()


def validar_evidencia(ruta: str | Path, evidencia: dict | None, *, fuentes_acreditadas: dict | None = None) -> dict:
    """fuentes_acreditadas: fuente -> conjunto de IDs de autorización verificados externamente.

    El llamador debe construir esa lista desde un registro independiente y confiable.
    La evidencia recibida no puede acreditarse a sí misma.
    """
    ruta = Path(ruta)
    motivos = []
    if not ruta.is_file():
        return {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['ARCHIVO_NO_ENCONTRADO'], 'sha256': None}
    digest = sha256_archivo(ruta)
    if not isinstance(evidencia, dict):
        return {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['EVIDENCIA_AUSENTE'], 'sha256': digest}
    tipo = evidencia.get('tipo_insumo')
    if tipo not in FUENTES:
        motivos.append('TIPO_INVALIDO')
    nombre = evidencia.get('nombre_archivo')
    if nombre != ruta.name:
        motivos.append('IDENTIDAD_ARCHIVO_NO_COINCIDE')
    hash_esperado = evidencia.get('sha256')
    if not isinstance(hash_esperado, str) or len(hash_esperado) != 64 or not hmac.compare_digest(digest, hash_esperado.lower()):
        motivos.append('INTEGRIDAD_NO_ACREDITADA')
    fecha = evidencia.get('fecha_contable')
    try:
        fecha_valida = date.fromisoformat(fecha) if isinstance(fecha, str) else None
    except ValueError:
        fecha_valida = None
    if fecha_valida is None:
        motivos.append('FECHA_INVALIDA')
    if not isinstance(evidencia.get('id_archivo'), int) or isinstance(evidencia.get('id_archivo'), bool) or evidencia['id_archivo'] <= 0:
        motivos.append('IDENTIFICADOR_INVALIDO')
    fuente = evidencia.get('fuente_emisora')
    autorizacion = evidencia.get('id_autorizacion')
    if not fuente or not autorizacion or autorizacion not in (fuentes_acreditadas or {}).get(fuente, set()):
        motivos.append('AUTORIZACION_EXTERNA_NO_ACREDITADA')
    # Incluso con una autorización acreditada, la identidad del archivo debe
    # contrastarse con el registro externo. Sin esa comprobación no se certifica.
    if not evidencia.get('identidad_contrastada_externamente') is True:
        motivos.append('IDENTIDAD_EXTERNA_NO_CONTRASTADA')
    # El campo anterior es una declaración, no prueba criptográfica: no emitir
    # ORIGEN_VERIFICADO automáticamente desde datos controlados por el solicitante.
    if not motivos:
        motivos.append('REQUIERE_VERIFICACION_INDEPENDIENTE_DE_EVIDENCIA')
    return {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': motivos, 'sha256': digest,
            'id_archivo': evidencia.get('id_archivo'), 'tipo_insumo': tipo}
