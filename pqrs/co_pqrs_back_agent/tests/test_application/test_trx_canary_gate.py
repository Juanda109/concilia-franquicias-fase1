"""Porton de despliegue del flujo TXNR (piloto en produccion).

Garantia que se prueba aqui: con TRX_FLOW_ENABLED=false, un cliente normal NUNCA
recorre el flujo real (que consulta ASOs y puede apagar/cancelar una tarjeta);
siempre termina en el formulario PQR. Solo una conversacion con el token de piloto
entra al flujo. Con TRX_FLOW_ENABLED=true entran todos (salida a produccion).
"""

import asyncio
import unittest
from unittest.mock import patch

from application.chat import chat_service as cs
from domain.conversation.models import Conversation, ConversationStatus

_TOKEN = "TOKEN-DE-PRUEBA-123"


def _conv(step: str = "2.4.0") -> Conversation:
    return Conversation(
        conversation_id="1013634960_20260820",
        status=ConversationStatus.ACTIVE,
        current_step=step,
        general_workflow="Transaccion no reconocida",
        workflow="trx_no_reconocida",
        flow_version=1,
        user_id="1013634960",
    )


def _prefetch(conv: Conversation) -> None:
    asyncio.run(cs._prefetch_trx_data_if_needed(conv, None, None, None))


def _env(**valores):
    """Simula el .env del configmap (el agente lo lee con _env_const)."""
    return patch.object(cs, "_env_const", side_effect=lambda name: valores.get(name))


class PortonCerradoTests(unittest.TestCase):
    """TRX_FLOW_ENABLED=false y sin token -> siempre formulario."""

    def test_op4_no_entra_al_flujo_va_al_formulario(self) -> None:
        conv = _conv("2.4.0.1")  # paso al que lleva "compra presencial o por internet"
        with _env(TRX_FLOW_ENABLED="false", TRX_CANARY_TOKEN=_TOKEN):
            _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.4.pqr")
        self.assertEqual(conv.captured_data.get("trx_gated"), "true")

    def test_ningun_paso_del_flujo_es_alcanzable(self) -> None:
        # Cubre conversaciones restauradas del store o saltos inesperados.
        for step in (
            "2.4.0.1", "2.4.0.1.1", "2.4.0.1.4", "2.4.0.1.5", "2.4.0.1.8",
            "2.4.0.1.10", "2.4.0.1.16.1", "2.4.0.1.17.1", "2.4.0.1.19", "2.4.0.1.20",
        ):
            conv = _conv(step)
            with _env(TRX_FLOW_ENABLED="false", TRX_CANARY_TOKEN=_TOKEN):
                _prefetch(conv)
            self.assertEqual(
                conv.current_step, "2.4.0.4.pqr", f"fuga en el paso {step}"
            )

    def test_el_menu_sigue_visible(self) -> None:
        # El porton no bloquea el menu 2.4.0: el cliente ve los 4 sucesos.
        conv = _conv("2.4.0")
        with _env(TRX_FLOW_ENABLED="false", TRX_CANARY_TOKEN=_TOKEN):
            _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0")

    def test_el_nodo_del_formulario_existe_y_ofrece_pqr(self) -> None:
        from domain.workflow.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        conv = _conv("2.4.0.4.pqr")
        prompt = engine.render_current_step_prompt(conv) or ""
        self.assertIn("formulario", prompt.lower())
        engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")


class TokenDePilotoTests(unittest.TestCase):
    def test_token_valido_habilita_el_flujo_en_esa_conversacion(self) -> None:
        conv = _conv("2.4.0.1")
        conv.captured_data[cs._TRX_CANARY_KEY] = "true"  # como lo deja el interceptor
        with _env(TRX_FLOW_ENABLED="false", TRX_CANARY_TOKEN=_TOKEN):
            _prefetch(conv)
        self.assertNotEqual(conv.current_step, "2.4.0.4.pqr")

    def test_reconoce_el_token_exacto(self) -> None:
        with _env(TRX_CANARY_TOKEN=_TOKEN):
            self.assertTrue(cs._is_trx_canary_token(_TOKEN))
            self.assertTrue(cs._is_trx_canary_token(f"  {_TOKEN}  "))  # tolera espacios

    def test_token_incorrecto_no_habilita(self) -> None:
        with _env(TRX_CANARY_TOKEN=_TOKEN):
            for intento in ("token-de-prueba-123", "TOKEN", "", "trx no reconocida", _TOKEN + "X"):
                self.assertFalse(cs._is_trx_canary_token(intento), intento)

    def test_sin_token_configurado_nada_habilita(self) -> None:
        with _env(TRX_CANARY_TOKEN=""):
            self.assertFalse(cs._is_trx_canary_token(""))
            self.assertFalse(cs._is_trx_canary_token("cualquier cosa"))


class KillSwitchTests(unittest.TestCase):
    def test_flag_true_abre_el_flujo_a_todos(self) -> None:
        conv = _conv("2.4.0.1")
        with _env(TRX_FLOW_ENABLED="true"):
            _prefetch(conv)
        self.assertNotEqual(conv.current_step, "2.4.0.4.pqr")
        self.assertIsNone(conv.captured_data.get("trx_gated"))

    def test_default_es_cerrado(self) -> None:
        # Sin la variable en el configmap, el flujo debe estar CERRADO.
        conv = _conv("2.4.0.1")
        with _env():
            _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.4.pqr")

    def test_valores_aceptados_del_flag(self) -> None:
        for valor, abierto in (("true", True), ("TRUE", True), ("1", True), ("on", True),
                               ("false", False), ("no", False), ("", False), ("cualquiera", False)):
            with _env(TRX_FLOW_ENABLED=valor):
                self.assertEqual(cs._trx_flow_enabled(), abierto, valor)


if __name__ == "__main__":
    unittest.main()
