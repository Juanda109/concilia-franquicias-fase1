from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.confirmar_trm_visa_inc017 import router


def test_sin_sso_no_confirma():
    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).post('/api/v1/jornadas/6961/trm-visa/confirmar', json={'modo': 'oficial'})
    assert r.status_code == 503
    assert 'Confirmacion TRM local no habilitada' in r.json()['detail']


def test_cabecera_usuario_no_sustituye_sso():
    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).post('/api/v1/jornadas/6961/trm-visa/confirmar',
        headers={'X-User': 'admin', 'X-Role': 'TRM_CONFIRMAR'}, json={'modo': 'oficial'})
    assert r.status_code == 503
