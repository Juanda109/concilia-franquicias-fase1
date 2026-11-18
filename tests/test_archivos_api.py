from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_archivos_endpoint_registrado():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    rutas = response.json()["paths"]

    assert "/api/v1/archivos" in rutas
    assert "/api/v1/archivos/{id_archivo}" in rutas

    assert "get" in rutas["/api/v1/archivos"]
    assert "get" in rutas["/api/v1/archivos/{id_archivo}"]


def test_archivo_id_invalido():
    response = client.get("/api/v1/archivos/0")

    assert response.status_code == 422


def test_archivo_id_no_numerico():
    response = client.get("/api/v1/archivos/abc")

    assert response.status_code == 422


def test_rechazar_tipo_archivo_no_permitido():
    response = client.post(
        "/api/v1/archivos",
        data={
            "fecha_contable": "2099-03-01",
            "tipo_archivo": "CAIT"
        },
        files={
            "archivo": (
                "prueba.txt",
                b"ARCHIVO DE PRUEBA",
                "text/plain"
            )
        }
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Tipo de insumo no permitido en MVP1"
    )
