import pytest

from psycopg import OperationalError

from app.batch.clasificacion_errores import clasificar_error
from app.services.procesamiento_host import ProcesamientoHostError
from app.services.normalizacion_host import NormalizacionHostError
from app.services.validacion_fechas_host import (
    FechaInternaHostInvalida,
)


@pytest.mark.parametrize(
    "error,categoria,reintentable",
    [
        (OperationalError("Conexion fallida"), "TRANSITORIO", True),
        (NormalizacionHostError("Importe invalido"), "FUNCIONAL", False),
        (FechaInternaHostInvalida([]), "FUNCIONAL", False),
        (ProcesamientoHostError("Checksum invalido"), "FUNCIONAL", False),
        (
            ProcesamientoHostError("Archivo fisico no encontrado"),
            "OPERATIVO",
            False,
        ),
        (
            ProcesamientoHostError("Parser reporto 1 errores"),
            "FUNCIONAL",
            False,
        ),
        (ValueError("Error desconocido"), "DESCONOCIDO", False),
    ],
)
def test_clasificacion(error, categoria, reintentable):
    resultado = clasificar_error(error)

    assert resultado["categoria"] == categoria
    assert resultado["reintentable"] is reintentable
    assert resultado["codigo"]
