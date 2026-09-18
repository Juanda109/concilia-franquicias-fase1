"""Adapter Agent -> Authorization (punto 15 del pliego): fail-open y contrato."""

import asyncio
import unittest
from unittest.mock import patch

from infrastructure.persistence import authorization_client


class _Resp:
    def __init__(self, status_code=201, cuerpo=None):
        self.status_code = status_code
        self._cuerpo = cuerpo or {"authorization_id": "auth-1", "status": "PENDING"}

    def raise_for_status(self):
        return None

    def json(self):
        return self._cuerpo


class _ClienteOk:
    def __init__(self, *a, **k): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return None
    async def post(self, *a, **k): return _Resp()
    async def get(self, *a, **k): return _Resp(200, {"status": "ACCEPTED"})


class _ClienteRoto(_ClienteOk):
    async def post(self, *a, **k): raise RuntimeError("refused")
    async def get(self, *a, **k): raise RuntimeError("refused")


import httpx


class _ClienteRotoHttpx(_ClienteOk):
    async def post(self, *a, **k): raise httpx.ConnectError("refused")
    async def get(self, *a, **k): raise httpx.ConnectError("refused")


class AuthorizationClientTests(unittest.TestCase):
    def test_registrar_devuelve_el_cuerpo(self):
        with patch.object(authorization_client.httpx, "AsyncClient", _ClienteOk):
            r = asyncio.run(authorization_client.registrar_autorizacion(
                base_url="http://auth:8005", conversation_id="c",
                workflow="w", step="s", challenge="CH",
            ))
        self.assertEqual(r["authorization_id"], "auth-1")

    def test_registrar_fail_open(self):
        with patch.object(authorization_client.httpx, "AsyncClient", _ClienteRotoHttpx):
            r = asyncio.run(authorization_client.registrar_autorizacion(
                base_url="http://auth:8005", conversation_id="c",
                workflow="w", step="s", challenge="CH",
            ))
        self.assertIsNone(r)

    def test_consultar_devuelve_estado(self):
        with patch.object(authorization_client.httpx, "AsyncClient", _ClienteOk):
            r = asyncio.run(authorization_client.consultar_autorizacion(
                base_url="http://auth:8005", authorization_id="auth-1",
            ))
        self.assertEqual(r["status"], "ACCEPTED")

    def test_sin_base_url_no_llama(self):
        r = asyncio.run(authorization_client.consultar_autorizacion(
            base_url="", authorization_id="auth-1",
        ))
        self.assertIsNone(r)
