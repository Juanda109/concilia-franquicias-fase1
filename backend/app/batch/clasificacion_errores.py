"""Clasificacion de errores del Host Loader."""

from psycopg import OperationalError

from app.services.procesamiento_host import ProcesamientoHostError
from app.services.normalizacion_host import NormalizacionHostError
from app.services.validacion_fechas_host import (
    FechaInternaHostInvalida,
)


def clasificar_error(exc):
    """Clasifica un error sin modificar estados."""

    if isinstance(exc, OperationalError):
        return {
            "categoria": "TRANSITORIO",
            "reintentable": True,
            "codigo": "ERROR_CONEXION_POSTGRESQL",
        }

    if isinstance(
        exc,
        (NormalizacionHostError, FechaInternaHostInvalida),
    ):
        return {
            "categoria": "FUNCIONAL",
            "reintentable": False,
            "codigo": "VALIDACION_HOST_INVALIDA",
        }

    if isinstance(exc, ProcesamientoHostError):
        mensaje = str(exc)

        if "Checksum" in mensaje:
            categoria = "FUNCIONAL"
            codigo = "CHECKSUM_INVALIDO"

        elif "Archivo fisico no encontrado" in mensaje:
            categoria = "OPERATIVO"
            codigo = "ARCHIVO_FISICO_AUSENTE"

        elif "Parser reporto" in mensaje:
            categoria = "FUNCIONAL"
            codigo = "PARSER_HOST_INVALIDO"

        else:
            categoria = "OPERATIVO"
            codigo = "PROCESAMIENTO_HOST_INCONSISTENTE"

        return {
            "categoria": categoria,
            "reintentable": False,
            "codigo": codigo,
        }

    return {
        "categoria": "DESCONOCIDO",
        "reintentable": False,
        "codigo": "ERROR_NO_CLASIFICADO",
    }
