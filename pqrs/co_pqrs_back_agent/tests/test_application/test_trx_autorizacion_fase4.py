"""Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback.

Cubre el mapeo ACCEPTED/REJECTED/EXPIRED/PENDING -> aceptado/rechazado/
vencido/pendiente, y que sin servicio (o sin registro) se degrada a la
consulta directa de siempre (comportamiento identico, criterio Fase 5).
"""

import asyncio
import json
import time
import unittest
from unittest.mock import patch

from application.chat import chat_service as CS
from domain.conversation.models import Conversation, ConversationStatus


def _conv(authorization_id="auth-1", deadline_delta=120.0):
    conv = Conversation(
        conversation_id="13083558_20260903",
        status=ConversationStatus.ACTIVE,
        current_step="2.4.0.1.17.2",
        general_workflow="Transaccion no reconocida",
        workflow="trx_no_reconocida",
        flow_version=1,
        user_id="13083558",
    )
    estado = {
        "subida_nivel": {
            "challenge": "CH-1",
            "authentication_state": "ST-1",
            "device_id": "DEV",
            "profile_id": "CC1",
            "last_four": "4818",
            "account_last_four": "2156",
            "deadline": time.time() + deadline_delta,
        }
    }
    if authorization_id:
        estado["subida_nivel"]["authorization_id"] = authorization_id
    conv.captured_data["trx_case_state_json"] = json.dumps(estado)
    return conv


def _estado(conv, respuesta_authorization):
    async def _consulta_falsa(**_k):
        return respuesta_authorization

    async def _via_directa_falsa(**_k):
        return {"aceptado": False, "status": "pending", "challenge": "CH-1"}

    with (
        patch.object(CS, "load_authorization_service_url", lambda *a, **k: "http://auth:8005"),
        patch.object(CS, "consultar_autorizacion", _consulta_falsa),
        patch.object(CS, "subida_nivel_estado_trx", _via_directa_falsa),
    ):
        return asyncio.run(CS._trx_estado_push_bloqueo(conv, "http://trx:8004"))


class Fase4MapeoTests(unittest.TestCase):
    def test_accepted(self):
        self.assertEqual(_estado(_conv(), {"status": "ACCEPTED"}), "aceptado")

    def test_rejected(self):
        self.assertEqual(_estado(_conv(), {"status": "REJECTED"}), "rechazado")

    def test_expired(self):
        self.assertEqual(_estado(_conv(), {"status": "EXPIRED"}), "vencido")

    def test_pending(self):
        self.assertEqual(_estado(_conv(), {"status": "PENDING"}), "pendiente")

    def test_pending_con_plazo_local_vencido(self):
        conv = _conv(deadline_delta=-5.0)
        self.assertEqual(_estado(conv, {"status": "PENDING"}), "vencido")

    def test_servicio_caido_degrada_a_via_directa(self):
        # consultar_autorizacion devuelve None -> fallback: la via directa
        # (aqui simulada como pending) manda, no un error
        self.assertEqual(_estado(_conv(), None), "pendiente")

    def test_sin_registro_usa_via_directa(self):
        conv = _conv(authorization_id="")
        self.assertEqual(_estado(conv, {"status": "ACCEPTED"}), "pendiente")

    def test_sin_url_configurada_usa_via_directa(self):
        conv = _conv()

        async def _via_directa(**_k):
            return {"aceptado": True, "status": "accepted", "challenge": "CH-1"}

        with (
            patch.object(CS, "load_authorization_service_url", lambda *a, **k: None),
            patch.object(CS, "subida_nivel_estado_trx", _via_directa),
        ):
            r = asyncio.run(CS._trx_estado_push_bloqueo(conv, "http://trx:8004"))
        self.assertEqual(r, "aceptado")
