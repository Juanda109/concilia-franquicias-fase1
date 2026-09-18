"""API v1: crear (idempotente), obtener, 404 (punto 6 del contrato)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.authorization.service import AuthorizationService
from infrastructure.entrypoint.api.router.v1.authorizations_router import (
    construir_router,
)

from tests.fakes import StoreEnMemoria


def _app():
    app = FastAPI()
    app.include_router(construir_router(AuthorizationService(StoreEnMemoria())))
    return TestClient(app)


def test_post_crea_y_devuelve_pending():
    cliente = _app()
    r = cliente.post("/v1/authorizations", json={
        "conversation_id": "123_20260903", "workflow": "trx_no_reconocida",
        "step": "2.4.0.1.17.1", "challenge": "CH-1",
    })
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["status"] == "PENDING"
    assert cuerpo["created"] is True
    assert cuerpo["deadline"] > 0


def test_post_duplicado_devuelve_el_mismo_id():
    cliente = _app()
    base = {"conversation_id": "c", "workflow": "w", "step": "s", "challenge": "CH"}
    a = cliente.post("/v1/authorizations", json=base).json()
    b = cliente.post("/v1/authorizations", json=base).json()
    assert a["authorization_id"] == b["authorization_id"]
    assert b["created"] is False


def test_get_por_id_y_404():
    cliente = _app()
    creado = cliente.post("/v1/authorizations", json={
        "conversation_id": "c", "workflow": "w", "step": "s", "challenge": "CH",
    }).json()
    r = cliente.get(f"/v1/authorizations/{creado['authorization_id']}")
    assert r.status_code == 200
    assert r.json()["conversation_id"] == "c"
    assert cliente.get("/v1/authorizations/no-existe").status_code == 404
