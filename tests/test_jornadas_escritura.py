import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import jornadas as jornadas_api
from app.repositories.database import connection as real_connection


@pytest.fixture
def cliente_transaccional(monkeypatch):
    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.fail("Las pruebas requieren concilia_test")

    # La conexion real pertenece exclusivamente a esta prueba.
    with real_connection() as conn:
        if conn.info.dbname != "concilia_test":
            pytest.fail("Conexion a base no autorizada")

        # Transaccion externa: nunca debe confirmarse.
        with conn.transaction() as tx_externa:

            @contextmanager
            def conexion_prueba():
                # Cada solicitud utiliza un SAVEPOINT.
                with conn.transaction():
                    yield conn

            monkeypatch.setattr(
                jornadas_api,
                "connection",
                conexion_prueba
            )

            try:
                with TestClient(app) as cliente:
                    yield cliente
            finally:
                # Fuerza la reversion de la transaccion externa.
                tx_externa.force_rollback = True


def test_crear_consultar_y_rechazar_duplicado(cliente_transaccional):
    cliente = cliente_transaccional
    fecha = "2099-02-01"

    respuesta = cliente.post(
        "/api/v1/jornadas",
        json={"fecha_contable": fecha}
    )

    assert respuesta.status_code == 201
    jornada = respuesta.json()
    assert jornada["fecha_contable"] == fecha

    id_jornada = jornada["id_jornada"]

    consulta = cliente.get(
        f"/api/v1/jornadas/{id_jornada}"
    )
    assert consulta.status_code == 200

    duplicado = cliente.post(
        "/api/v1/jornadas",
        json={"fecha_contable": fecha}
    )
    assert duplicado.status_code == 409




@pytest.mark.parametrize(
    "version,esperados,fecha",
    [
        (1, 10, "2026-07-04"),
        (2, 11, "2026-07-05"),
    ],
)
def test_inicializacion_catalogo_versionado(
    cliente_transaccional, version, esperados, fecha
):
    cliente = cliente_transaccional

    creacion = cliente.post(
        "/api/v1/jornadas",
        json={"fecha_contable": fecha}
    )
    assert creacion.status_code == 201, creacion.text

    id_jornada = creacion.json()["id_jornada"]

    inicializacion = cliente.post(
        f"/api/v1/jornadas/{id_jornada}/inicializar",
        json={"version_catalogo": version}
    )
    assert inicializacion.status_code == 200, inicializacion.text
    assert inicializacion.json()["insumos_insertados"] == esperados

    consulta = cliente.get(
        f"/api/v1/jornadas/{id_jornada}/insumos"
    )
    assert consulta.status_code == 200
    assert consulta.json()["total"] == esperados

    segunda = cliente.post(
        f"/api/v1/jornadas/{id_jornada}/inicializar",
        json={"version_catalogo": version}
    )
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["insumos_insertados"] == 0

    otra_version = 2 if version == 1 else 1
    cambio = cliente.post(
        f"/api/v1/jornadas/{id_jornada}/inicializar",
        json={"version_catalogo": otra_version}
    )
    assert cambio.status_code == 409, cambio.text
