import json
from datetime import date
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.services.fase2.cliente_http_trm_inc017 import (
    consultar_trm_http,
    ErrorConsultaTRM,
    SinRedirecciones,
)

MODULO = "app.services.fase2.cliente_http_trm_inc017"
FECHA = date(2026, 11, 12)


class Respuesta:
    status = 200

    def __init__(self, contenido, tipo="application/json"):
        self.headers = {"Content-Type": tipo}
        self.buffer = BytesIO(contenido)

    def read(self, cantidad):
        return self.buffer.read(cantidad)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def ejecutar(monkeypatch, respuesta=None, error=None):
    monkeypatch.setenv("CONCILIA_TRM_HTTP_HABILITADO", "1")

    with patch(MODULO + ".build_opener") as constructor:
        apertura = constructor.return_value.open

        if error is not None:
            apertura.side_effect = error
        else:
            apertura.return_value = respuesta

        return consultar_trm_http(FECHA)


def test_error_http_403(monkeypatch):
    error = HTTPError(
        "https://www.datos.gov.co",
        403,
        "Forbidden",
        {},
        None,
    )

    with pytest.raises(ErrorConsultaTRM):
        ejecutar(monkeypatch, error=error)


def test_error_conexion(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            error=URLError("Conexion no disponible"),
        )


def test_timeout(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            error=TimeoutError("Timeout"),
        )


def test_json_invalido(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            respuesta=Respuesta(b"{invalido"),
        )


def test_tipo_contenido_incorrecto(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            respuesta=Respuesta(
                b"[]",
                tipo="text/html",
            ),
        )


def test_respuesta_demasiado_grande(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            respuesta=Respuesta(b"x" * 262145),
        )


def test_json_no_es_lista(monkeypatch):
    contenido = json.dumps(
        {"valor": "4100.0000"}
    ).encode()

    with pytest.raises(ErrorConsultaTRM):
        ejecutar(
            monkeypatch,
            respuesta=Respuesta(contenido),
        )


def test_redireccion_bloqueada():
    manejador = SinRedirecciones()

    resultado = manejador.redirect_request(
        None,
        None,
        302,
        "Found",
        {},
        "https://otro-dominio.example",
    )

    assert resultado is None


def test_sin_confirmacion_automatica(monkeypatch):
    registro = [{
        "valor": "4100.0000",
        "unidad": "COP",
        "vigenciadesde": "2026-11-12T00:00:00",
        "vigenciahasta": "2026-11-12T00:00:00",
    }]

    contenido = json.dumps(registro).encode()

    resultado = ejecutar(
        monkeypatch,
        respuesta=Respuesta(contenido),
    )

    assert resultado["confirmada"] is False
    assert resultado["certificado"] is False
    assert resultado["conciliado_host"] is False
