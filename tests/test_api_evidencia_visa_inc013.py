from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.fase2.evidencia_visa_vss_inc013 import (
    EvidenciaVisaInconsistente,
)

RUTA = "/api/v1/jornadas/6606/evidencia-visa-vss"
SERVICIO = (
    "app.api.evidencia_visa_vss_inc013."
    "consultar_evidencia_visa"
)


def respuesta_valida():
    return {
        "id_jornada": 6606,
        "fecha_contable": "2026-11-12",
        "estado": "IMPORTE_SIMULADO_OBSERVADO",
        "certificado": False,
        "conciliado_host": False,
        "evidencia": {
            "reporte": "VSS-110",
            "moneda_liquidacion": "COP",
            "importe_observado": "1250.00",
            "signo_observado": "CR",
            "modo": "SOLO_PRUEBAS",
            "origen_simulado": True,
            "liquidacion_recalculada": None,
        },
    }


def test_api_visa_200():
    with patch(SERVICIO, return_value=respuesta_valida()):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["certificado"] is False
    assert datos["conciliado_host"] is False
    assert datos["evidencia"]["importe_observado"] == "1250.00"


def test_api_visa_404():
    with patch(SERVICIO, side_effect=LookupError("Jornada inexistente")):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 404


def test_api_visa_409():
    with patch(
        SERVICIO,
        side_effect=EvidenciaVisaInconsistente("Paridad invalida"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 409


def test_api_visa_422():
    with TestClient(app) as cliente:
        respuesta = cliente.get(
            "/api/v1/jornadas/0/evidencia-visa-vss"
        )

    assert respuesta.status_code == 422


def test_api_visa_openapi():
    with TestClient(app) as cliente:
        respuesta = cliente.get("/openapi.json")

    assert respuesta.status_code == 200
    assert (
        "/api/v1/jornadas/{id_jornada}/evidencia-visa-vss"
        in respuesta.json()["paths"]
    )


def test_api_visa_503():
    from psycopg import OperationalError

    with patch(
        SERVICIO,
        side_effect=OperationalError("Conexion no disponible"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == (
        "Base de datos no disponible"
    )
