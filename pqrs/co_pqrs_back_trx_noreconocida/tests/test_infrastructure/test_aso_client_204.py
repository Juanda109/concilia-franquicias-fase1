"""Manejo del 204/2xx sin cuerpo del ASO (incidente DEV 25/08 + rework 26/08).

Historia en dos actos: el 25/08 el 204 explotaba como JSONDecodeError (arreglado
con None fail-closed). El 26/08 el rework de dev fijo la semantica DEFINITIVA:
2xx sin cuerpo = "el cliente no tiene datos" -> {} (outcome=no_content), que
fluye a productos [] -> .4.exit. Estos tests fijan ESA semantica.

RIESGO ACEPTADO (anotado en DECISIONES): si un 204 viniera de una sesion mal
autenticada (el caso del 25/08) y no de un cliente sin datos, el bot diria
"no tienes productos activos" a alguien que si los tiene. La apuesta del equipo
es que con el granting corregido el 204 solo significa "sin datos".
"""

from types import SimpleNamespace
from unittest.mock import patch

from infrastructure.persistence.aso_client import TrxAsoClient


class _RespuestaFalsa:
    def __init__(self, status_code=204, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self.headers = {}
        self.text = content.decode() if content else ""
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _ClienteFalso:
    def __init__(self, respuesta):
        self._respuesta = respuesta

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None):
        return self._respuesta


def _fo(respuesta):
    with patch.object(TrxAsoClient, "_client", lambda self: _ClienteFalso(respuesta)), \
         patch.object(TrxAsoClient, "_base", lambda self: "https://aso.falso"):
        return TrxAsoClient().financial_overview(customer_id="00235597", tsec="t")


def test_204_sin_cuerpo_es_dict_vacio_sin_excepcion():
    """Semantica del rework: {} = "sin datos" (NO None = fallo)."""
    assert _fo(_RespuestaFalsa(status_code=204)) == {}


def test_200_con_cuerpo_vacio_tambien_es_dict_vacio():
    assert _fo(_RespuestaFalsa(status_code=200, content=b"")) == {}


def test_200_con_json_sigue_funcionando():
    payload = {"data": {"contracts": []}}
    assert _fo(_RespuestaFalsa(status_code=200, content=b"{}", payload=payload)) == payload


class _RespuestaGranting:
    def __init__(self, header_tsec="", body=""):
        self.status_code = 200
        self.headers = {"tsec": header_tsec} if header_tsec else {}
        self.text = body
        self.content = body.encode()

    def raise_for_status(self):
        return None


class _ClienteGranting:
    def __init__(self, respuesta):
        self._respuesta = respuesta

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        return self._respuesta


def _tsec(respuesta):
    with patch.object(TrxAsoClient, "_client", lambda self: _ClienteGranting(respuesta)), \
         patch.object(TrxAsoClient, "_base", lambda self: "https://aso.falso"):
        return TrxAsoClient().get_tsec()


def test_tsec_en_cabecera_como_siempre():
    assert _tsec(_RespuestaGranting(header_tsec="TICKET-CABECERA")) == "TICKET-CABECERA"


def test_tsec_en_el_cuerpo_como_centrales():
    """El granting de dev puede devolver el ticket en el cuerpo (la
    implementacion de centrales ya lo contemplaba; la nuestra no)."""
    assert _tsec(_RespuestaGranting(body="TICKET-CUERPO")) == "TICKET-CUERPO"


def test_cabecera_gana_al_cuerpo():
    assert _tsec(_RespuestaGranting(header_tsec="A", body="B")) == "A"
