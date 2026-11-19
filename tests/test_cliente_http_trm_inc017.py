import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest

from app.services.fase2.cliente_http_trm_inc017 import (
    consultar_trm_http,
    ErrorConsultaTRM,
)

MODULO = "app.services.fase2.cliente_http_trm_inc017"
FECHA = date(2026, 11, 12)


class Respuesta:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, datos):
        self.contenido = BytesIO(json.dumps(datos).encode())

    def read(self, cantidad):
        return self.contenido.read(cantidad)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def registro(**cambios):
    r = {
        "valor": "4100.0000",
        "unidad": "COP",
        "vigenciadesde": "2026-11-12T00:00:00",
        "vigenciahasta": "2026-11-12T00:00:00",
    }
    r.update(cambios)
    return r


def ejecutar(monkeypatch, registros):
    monkeypatch.setenv("CONCILIA_TRM_HTTP_HABILITADO", "1")

    with patch(MODULO + ".build_opener") as constructor:
        constructor.return_value.open.return_value = Respuesta(
            registros
        )
        resultado = consultar_trm_http(FECHA)

        assert constructor.return_value.open.call_count == 1

    return resultado


def test_consulta_exitosa(monkeypatch):
    r = ejecutar(monkeypatch, [registro()])
    assert r["estado"] == "TRM_OFICIAL_PROPUESTA"
    assert r["trm_propuesta"] == "4100.0000"
    assert r["confirmada"] is False


def test_http_deshabilitado(monkeypatch):
    monkeypatch.delenv(
        "CONCILIA_TRM_HTTP_HABILITADO",
        raising=False,
    )

    with pytest.raises(ErrorConsultaTRM):
        consultar_trm_http(FECHA)


def test_sin_tasa_vigente(monkeypatch):
    r = ejecutar(monkeypatch, [])
    assert r["estado"] == "SIN_FUENTE_OFICIAL"


def test_respuesta_duplicada(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(monkeypatch, [registro(), registro()])


def test_fecha_invalida(monkeypatch):
    monkeypatch.setenv("CONCILIA_TRM_HTTP_HABILITADO", "1")

    with pytest.raises(ErrorConsultaTRM):
        consultar_trm_http("2026-11-12")


def test_moneda_incorrecta(monkeypatch):
    with pytest.raises(ErrorConsultaTRM):
        ejecutar(monkeypatch, [registro(unidad="USD")])


def test_no_certifica(monkeypatch):
    r = ejecutar(monkeypatch, [registro()])
    assert r["certificado"] is False
    assert r["conciliado_host"] is False
