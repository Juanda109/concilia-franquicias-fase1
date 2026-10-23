import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.api import archivos as archivos_api
from app.services.procesamiento_host import ProcesamientoHostError
from app.services.normalizacion_host import NormalizacionHostError
from app.services.validacion_fechas_host import FechaInternaHostInvalida


@pytest.fixture
def cliente():
    with TestClient(app) as test_client:
        yield test_client


def test_http_200_procesamiento(cliente, monkeypatch):
    def procesar(id_archivo):
        assert id_archivo == 999
        return {
            "id_archivo": id_archivo,
            "tipo_archivo": "HA22",
            "estado": "PROCESADO",
            "registros": 1,
            "idempotente": False,
        }

    monkeypatch.setattr(archivos_api, "procesar_host", procesar)

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "PROCESADO"
    assert respuesta.json()["idempotente"] is False


def test_http_200_idempotente(cliente, monkeypatch):
    monkeypatch.setattr(
        archivos_api,
        "procesar_host",
        lambda id_archivo: {
            "id_archivo": id_archivo,
            "tipo_archivo": "HA22",
            "estado": "PROCESADO",
            "registros": 1,
            "idempotente": True,
        },
    )

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == 200
    assert respuesta.json()["idempotente"] is True


@pytest.mark.parametrize(
    "mensaje,codigo_http",
    [
        ("Archivo no asociado a una jornada", 404),
        ("Archivo no disponible para procesamiento", 409),
    ],
)
def test_http_error_funcional(
    cliente, monkeypatch, mensaje, codigo_http
):
    def procesar(_):
        raise ProcesamientoHostError(mensaje)

    monkeypatch.setattr(archivos_api, "procesar_host", procesar)

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == codigo_http


def test_http_422_fecha_interna(cliente, monkeypatch):
    def procesar(_):
        raise FechaInternaHostInvalida([{
            "linea": 2,
            "codigo": "FECHA_REGISTRO_INVALIDA",
            "descripcion": "Fecha incompatible",
        }])

    monkeypatch.setattr(archivos_api, "procesar_host", procesar)

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == (
        "FECHA_INTERNA_NO_CORRESPONDE"
    )


def test_http_422_normalizacion(cliente, monkeypatch):
    def procesar(_):
        raise NormalizacionHostError("Importe invalido")

    monkeypatch.setattr(archivos_api, "procesar_host", procesar)

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == (
        "NORMALIZACION_HOST_INVALIDA"
    )


def test_http_503_base_no_disponible(cliente, monkeypatch):
    def procesar(_):
        raise KeyError("DB_HOST")

    monkeypatch.setattr(archivos_api, "procesar_host", procesar)

    respuesta = cliente.post("/api/v1/archivos/999/procesar")

    assert respuesta.status_code == 503
    assert respuesta.json()["detail"]["codigo"] == (
        "SERVICIO_NO_DISPONIBLE"
    )


def test_http_422_id_invalido(cliente, monkeypatch):
    def no_debe_ejecutarse(_):
        raise AssertionError("No debe ejecutar procesamiento")

    monkeypatch.setattr(
        archivos_api, "procesar_host", no_debe_ejecutarse
    )

    respuesta = cliente.post("/api/v1/archivos/0/procesar")

    assert respuesta.status_code == 422
