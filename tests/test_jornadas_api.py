from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_crear_jornada_sin_fecha():
    response = client.post(
        "/api/v1/jornadas",
        json={}
    )

    assert response.status_code == 422


def test_crear_jornada_fecha_invalida():
    response = client.post(
        "/api/v1/jornadas",
        json={"fecha_contable": "fecha-invalida"}
    )

    assert response.status_code == 422


def test_inicializar_sin_version():
    response = client.post(
        "/api/v1/jornadas/4/inicializar",
        json={}
    )

    assert response.status_code == 422


def test_inicializar_version_invalida():
    response = client.post(
        "/api/v1/jornadas/4/inicializar",
        json={"version_catalogo": 0}
    )

    assert response.status_code == 422
