from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.api.confirmar_trm_visa_inc017 import router

app = FastAPI()
app.include_router(router)


def test_bloqueado_por_defecto(monkeypatch):
    monkeypatch.delenv('CONCILIA_TRM_LOCAL_SIN_AUTH', raising=False)
    monkeypatch.setenv('DB_NAME', 'concilia_test')
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        assert client.post('/api/v1/jornadas/6961/trm-visa/confirmar', json={'modo':'oficial'}).status_code == 503


def test_bloqueado_en_base_no_test(monkeypatch):
    monkeypatch.setenv('CONCILIA_TRM_LOCAL_SIN_AUTH', '1')
    monkeypatch.setenv('DB_NAME', 'concilia')
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        assert client.post('/api/v1/jornadas/6961/trm-visa/confirmar', json={'modo':'oficial'}).status_code == 503


def test_local_valida_sin_escribir(monkeypatch):
    monkeypatch.setenv("CONCILIA_TRM_LOCAL_SIN_AUTH", "1")
    monkeypatch.setenv("DB_NAME", "concilia_test")

    with patch(
        "app.api.confirmar_trm_visa_inc017.registrar_confirmacion_trm"
    ) as guardar:
        guardar.return_value = {
            "id_jornada": 6961,
            "estado": "TRM_CONFIRMADA",
            "version": 1,
            "trm_aplicada": "3326.9600",
            "certificado": False,
            "conciliado_host": False,
        }

        with TestClient(
            app, client=("127.0.0.1", 50000)
        ) as client:
            respuesta = client.post(
                "/api/v1/jornadas/6961/trm-visa/confirmar",
                json={
                    "modo": "manual",
                    "trm_aplicada": "3326.9600",
                },
            )

        assert respuesta.status_code == 200, respuesta.text
        guardar.assert_called_once()

        datos = guardar.call_args.kwargs
        assert datos["fuente"] == "MANUAL_USUARIO"
        assert str(datos["trm_aplicada"]) == "3326.9600"
        assert datos["trm_oficial"] is None
        assert datos["justificacion"] is None
        assert datos["usuario_autenticado"] == (
            "PRUEBA_LOCAL_SIN_AUTENTICACION"
        )
