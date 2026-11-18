"""Seleccion de plantilla de REGLAS, nunca de importes, para una jornada.

La plantilla es un contrato estructural; el PMD se lee exclusivamente de BD.
"""
import hashlib
import os
from pathlib import Path


def resolver_plantilla_reglas(id_jornada, fecha_contable):
    ruta = os.getenv('INC64_PLANTILLA_REGLAS')
    huella = os.getenv('INC64_PLANTILLA_REGLAS_SHA256')
    if not ruta and not huella:
        return None
    if not ruta or not huella:
        raise ValueError('Ruta y SHA256 de reglas son obligatorios conjuntamente')
    archivo = Path(ruta)
    if not archivo.is_absolute() or archivo.suffix.lower() not in ('.xlsx', '.xlsm') or not archivo.is_file():
        raise ValueError('Plantilla de reglas invalida o inexistente')
    if len(huella) != 64 or any(c not in '0123456789abcdef' for c in huella.lower()):
        raise ValueError('SHA256 de reglas invalido')
    if hashlib.sha256(archivo.read_bytes()).hexdigest() != huella.lower():
        raise ValueError('SHA256 de reglas no coincide')
    return archivo
