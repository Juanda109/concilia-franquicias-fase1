from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.main import app


RUTA = "/api/v1/jornadas/6606/trm-visa"
MODULO = "app.api.trm_visa_inc017"


def respuesta_valida():
    return {
        "id_jornada": 6606,
        "fecha_contable": "2026-11-12",
        "estado": "TRM_CONFIRMADA",
        "trm": {
            "id_trm": 17,
            "version": 1,
            "fecha_referencia": "2026-11-12",
            "trm_oficial": "4100.0000",
            "trm_aplicada": "4100.0000",
            "fuente": "TASA_FICTICIA_PARA_PRUEBAS",
            "modificada_manualmente": False,
        },
    }


def test_api_trm_200():
    with patch(
        MODULO + ".esquema_trm_disponible",
        return_value=True,
    ), patch(
        MODULO + ".consultar_trm_vigente",
        return_value=respuesta_valida(),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 200
    datos = r.json()
    assert datos["trm"]["version"] == 1
    assert datos["certificado"] is False
    assert datos["conciliado_host"] is False


def test_api_trm_sin_confirmacion():
    respuesta = {
        "id_jornada": 6606,
        "fecha_contable": "2026-11-12",
        "estado": "SIN_TRM_CONFIRMADA",
        "trm": None,
    }

    with patch(
        MODULO + ".esquema_trm_disponible",
        return_value=True,
    ), patch(
        MODULO + ".consultar_trm_vigente",
        return_value=respuesta,
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 200
    assert r.json()["trm"] is None


def test_api_trm_esquema_pendiente():
    with patch(
        MODULO + ".esquema_trm_disponible",
        return_value=False,
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 503
    assert r.json()["detail"] == (
        "Esquema TRM pendiente de instalacion"
    )


def test_api_trm_jornada_inexistente():
    with patch(
        MODULO + ".esquema_trm_disponible",
        return_value=True,
    ), patch(
        MODULO + ".consultar_trm_vigente",
        side_effect=LookupError("Jornada inexistente"),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 404


def test_api_trm_jornada_invalida():
    with TestClient(app) as cliente:
        r = cliente.get(
            "/api/v1/jornadas/0/trm-visa"
        )

    assert r.status_code == 422


def test_api_trm_bd_no_disponible():
    with patch(
        MODULO + ".esquema_trm_disponible",
        side_effect=OperationalError("Sin conexion"),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 503
    assert r.json()["detail"] == (
        "Base de datos no disponible"
    )


def test_api_trm_openapi():
    with TestClient(app) as cliente:
        r = cliente.get("/openapi.json")

    assert r.status_code == 200

    ruta = (
        "/api/v1/jornadas/{id_jornada}/trm-visa"
    )

    assert ruta in r.json()["paths"]
    assert "get" in r.json()["paths"][ruta]
    assert "post" not in r.json()["paths"][ruta]
