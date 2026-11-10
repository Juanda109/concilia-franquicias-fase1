"""Seguridad HTTP de consolidacion tecnica MVP1."""

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import LockNotAvailable

from app.main import app
from app.api import consolidacion as api


def test_consolidacion_sin_autorizacion(monkeypatch):
    def prohibido(id_jornada):
        pytest.fail("No debe ejecutarse el servicio")

    monkeypatch.setattr(
        api, "consolidar_jornada", prohibido
    )

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/294/consolidar"
        )

    assert respuesta.status_code == 403
    assert (
        respuesta.json()["detail"]["codigo"]
        == "CONSOLIDACION_NO_AUTORIZADA"
    )


def test_consolidacion_bloqueada_http_503(monkeypatch):
    def simular_bloqueo(id_jornada):
        raise LockNotAvailable(
            "canceling statement due to lock timeout"
        )

    monkeypatch.setattr(
        api, "consolidar_jornada", simular_bloqueo
    )

    app.dependency_overrides[
        api.autorizar_consolidacion
    ] = lambda: True

    try:
        with TestClient(app) as cliente:
            respuesta = cliente.post(
                "/api/v1/jornadas/295/consolidar"
            )

        assert respuesta.status_code == 503
        assert respuesta.headers["retry-after"] == "5"

    finally:
        app.dependency_overrides.pop(
            api.autorizar_consolidacion,
            None,
        )
