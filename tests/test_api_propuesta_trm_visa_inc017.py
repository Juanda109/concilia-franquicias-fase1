from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.main import app
from app.services.fase2.cliente_http_trm_inc017 import (
    ErrorConsultaTRM,
)

MODULO = "app.api.propuesta_trm_visa_inc017"

RUTA = "/api/v1/jornadas/6606/trm-visa/propuesta"

FECHA = date(2026, 11, 12)


def propuesta_valida():
    return {
        "fecha_referencia": "2026-11-12",
        "estado": "TRM_OFICIAL_PROPUESTA",
        "trm_propuesta": "3297.0700",
        "fuente": "SUPERFINANCIERA_DATOS_ABIERTOS",
        "referencia_fuente": (
            "https://www.datos.gov.co/resource/32sa-8pi3.json"
        ),
        "confirmada": False,
        "certificado": False,
        "conciliado_host": False,
    }


def test_propuesta_200():
    with patch(
        MODULO + ".consultar_fecha_contable",
        return_value=FECHA,
    ), patch(
        MODULO + ".consultar_trm_http",
        return_value=propuesta_valida(),
    ) as consulta:
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 200
    datos = r.json()

    assert datos["id_jornada"] == 6606
    assert datos["fecha_contable"] == "2026-11-12"
    assert datos["trm_propuesta"] == "3297.0700"
    assert datos["confirmada"] is False
    assert datos["certificado"] is False
    assert datos["conciliado_host"] is False

    consulta.assert_called_once_with(FECHA)


def test_jornada_inexistente():
    with patch(
        MODULO + ".consultar_fecha_contable",
        side_effect=LookupError("Jornada inexistente"),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 404


def test_jornada_invalida():
    with TestClient(app) as cliente:
        r = cliente.get(
            "/api/v1/jornadas/0/trm-visa/propuesta"
        )

    assert r.status_code == 422


def test_base_no_disponible():
    with patch(
        MODULO + ".consultar_fecha_contable",
        side_effect=OperationalError("Sin conexion"),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 503


def test_fuente_no_disponible():
    with patch(
        MODULO + ".consultar_fecha_contable",
        return_value=FECHA,
    ), patch(
        MODULO + ".consultar_trm_http",
        side_effect=ErrorConsultaTRM("Sin acceso"),
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 503


def test_fecha_inconsistente():
    propuesta = propuesta_valida()
    propuesta["fecha_referencia"] = "2026-11-13"

    with patch(
        MODULO + ".consultar_fecha_contable",
        return_value=FECHA,
    ), patch(
        MODULO + ".consultar_trm_http",
        return_value=propuesta,
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 409


def test_no_acepta_confirmacion_automatica():
    propuesta = propuesta_valida()
    propuesta["confirmada"] = True

    with patch(
        MODULO + ".consultar_fecha_contable",
        return_value=FECHA,
    ), patch(
        MODULO + ".consultar_trm_http",
        return_value=propuesta,
    ):
        with TestClient(app) as cliente:
            r = cliente.get(RUTA)

    assert r.status_code == 409


def test_openapi_solo_get():
    with TestClient(app) as cliente:
        r = cliente.get("/openapi.json")

    assert r.status_code == 200

    ruta = (
        "/api/v1/jornadas/{id_jornada}/trm-visa/propuesta"
    )

    paths = r.json()["paths"]

    assert ruta in paths
    assert "get" in paths[ruta]
    assert "post" not in paths[ruta]
    assert "put" not in paths[ruta]
    assert "delete" not in paths[ruta]
