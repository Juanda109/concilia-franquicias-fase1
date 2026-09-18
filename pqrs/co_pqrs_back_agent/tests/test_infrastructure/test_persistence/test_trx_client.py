import asyncio
import unittest
from unittest.mock import patch

from infrastructure.persistence import trx_client


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"status": "mock", "step": "consultar_trx", "detail": "x", "data": {}}


class _FakeAsyncClient:
    """Context-manager stub that returns a canned response."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, *args, **kwargs):
        return _FakeResponse()

    async def get(self, *args, **kwargs):
        return _FakeResponse()


class _BoomAsyncClient(_FakeAsyncClient):
    async def post(self, *args, **kwargs):
        raise RuntimeError("connection refused")

    async def get(self, *args, **kwargs):
        raise RuntimeError("connection refused")


class TrxClientTests(unittest.TestCase):
    def test_consultar_trx_returns_body_on_success(self) -> None:
        with patch.object(trx_client.httpx, "AsyncClient", _FakeAsyncClient):
            result = asyncio.run(
                trx_client.consultar_trx(base_url="http://trx:8004", customer_id="123")
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["step"], "consultar_trx")

    def test_consultar_productos_activos_returns_body_on_success(self) -> None:
        with patch.object(trx_client.httpx, "AsyncClient", _FakeAsyncClient):
            result = asyncio.run(
                trx_client.consultar_productos_activos(
                    base_url="http://trx:8004",
                    customer_id="123",
                )
            )
        self.assertIsNotNone(result)

    def test_consultar_trx_fail_open_returns_none(self) -> None:
        with patch.object(trx_client.httpx, "AsyncClient", _BoomAsyncClient):
            result = asyncio.run(
                trx_client.consultar_trx(base_url="http://trx:8004", customer_id="123")
            )
        self.assertIsNone(result)

    def test_analizar_fail_open_returns_none(self) -> None:
        with patch.object(trx_client.httpx, "AsyncClient", _BoomAsyncClient):
            result = asyncio.run(
                trx_client.analizar(
                    base_url="http://trx:8004", customer_id="123", evento="cambiazo"
                )
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

class _RespuestaFija(_FakeResponse):
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    def json(self) -> dict:
        return self._cuerpo


def _cliente_con(cuerpo: dict):
    class _Cliente(_FakeAsyncClient):
        async def get(self, *args, **kwargs):
            return _RespuestaFija(cuerpo)

    return _Cliente


class EstadoRetoNormalizacionTests(unittest.TestCase):
    """El sobre del servicio TXNR trae status="ok" (resultado del REQUEST):
    jamas debe leerse como estado del reto. Un pending leido como accepted
    autorizaba bloqueos sin confirmacion del cliente (E2E 28/08)."""

    def _estado(self, cuerpo: dict) -> dict:
        with patch.object(trx_client.httpx, "AsyncClient", _cliente_con(cuerpo)):
            return asyncio.run(
                trx_client.subida_nivel_estado_trx(
                    base_url="http://trx:8004", challenge="CH-1"
                )
            )

    def test_sobre_ok_con_pending_no_es_aceptado(self) -> None:
        r = self._estado(
            {"status": "ok", "aceptado": False, "estado": "pending",
             "pendiente": True, "sondeos": 1}
        )
        self.assertFalse(r["aceptado"])
        self.assertEqual(r["status"], "pending")

    def test_sobre_ok_sin_estado_pero_pendiente_es_pending(self) -> None:
        r = self._estado({"status": "ok", "aceptado": False, "pendiente": True})
        self.assertFalse(r["aceptado"])
        self.assertEqual(r["status"], "pending")

    def test_sobre_ok_aceptado_true_es_accepted(self) -> None:
        r = self._estado(
            {"status": "ok", "aceptado": True, "estado": "accepted", "sondeos": 1}
        )
        self.assertTrue(r["aceptado"])
        self.assertEqual(r["status"], "accepted")

    def test_forma_cruda_del_aso_sigue_funcionando(self) -> None:
        r = self._estado({"data": {"status": {"id": "accepted"}}})
        self.assertTrue(r["aceptado"])
        self.assertEqual(r["status"], "accepted")

    def test_rechazado_y_expirado_del_servicio(self) -> None:
        r = self._estado({"status": "ok", "aceptado": False, "estado": "rejected"})
        self.assertEqual(r["status"], "rejected")
        r = self._estado({"status": "ok", "aceptado": False, "estado": "expired"})
        self.assertEqual(r["status"], "expired")

