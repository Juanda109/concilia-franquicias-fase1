"""Pruebas HTTP de consolidacion sin modificar PostgreSQL."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import consolidacion as api
from app.services.consolidacion_jornada import (
    JornadaNoEncontrada,
    JornadaIncompleta,
)


@pytest.fixture(autouse=True)
def autorizacion_simulada():
    """Autoriza solo dentro de pruebas y revierte el override."""
    app.dependency_overrides[
        api.autorizar_consolidacion
    ] = lambda: True

    try:
        yield
    finally:
        app.dependency_overrides.pop(
            api.autorizar_consolidacion,
            None,
        )


def test_consolidacion_exitosa(monkeypatch):
    def simular(id_jornada):
        assert id_jornada == 295
        return {
            "id_jornada": 295,
            "estado": "COMPLETADA",
            "total_archivos": 10,
            "idempotente": False,
            "correlation_id": "TEST-295",
        }

    monkeypatch.setattr(api, "consolidar_jornada", simular)

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/295/consolidar"
        )

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "COMPLETADA"
    assert respuesta.json()["total_archivos"] == 10


def test_consolidacion_idempotente(monkeypatch):
    monkeypatch.setattr(
        api,
        "consolidar_jornada",
        lambda id_jornada: {
            "id_jornada": id_jornada,
            "estado": "COMPLETADA",
            "total_archivos": 10,
            "idempotente": True,
            "correlation_id": "TEST-IDEMPOTENTE",
        },
    )

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/295/consolidar"
        )

    assert respuesta.status_code == 200
    assert respuesta.json()["idempotente"] is True


def test_jornada_inexistente(monkeypatch):
    def simular(id_jornada):
        raise JornadaNoEncontrada("Jornada no encontrada")

    monkeypatch.setattr(api, "consolidar_jornada", simular)

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/999999/consolidar"
        )

    assert respuesta.status_code == 404


def test_jornada_incompleta(monkeypatch):
    def simular(id_jornada):
        raise JornadaIncompleta("Jornada incompleta")

    monkeypatch.setattr(api, "consolidar_jornada", simular)

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/295/consolidar"
        )

    assert respuesta.status_code == 409


def test_identificador_invalido():
    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/jornadas/0/consolidar"
        )

    assert respuesta.status_code == 422
