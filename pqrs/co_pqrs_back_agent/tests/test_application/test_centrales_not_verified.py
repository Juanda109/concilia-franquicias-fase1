"""Regression guard: centrales terminal actions must NOT reassure when the
back-data result is missing/unverified (error/timeout/stale).

They must show the safe "no pude validar" message, never "no tienes reportes"
nor "tienes productos activos".
"""

from __future__ import annotations

import unittest

from application.chat.workflow_actions import (
    _load_all_products_central_risk,
    _load_products_consulta_sin_permiso,
    _load_products_notificacion_centrales,
)
from domain.conversation.models import Conversation, ConversationStatus


def _conversation(step: str) -> Conversation:
    return Conversation(
        conversation_id="123_20260717",
        status=ConversationStatus.ACTIVE,
        current_step=step,
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={},
        captured_data={"back_data_status": "error"},  # sin back_data_result
        user_id="123",
        messages=[],
    )


class NotVerifiedTerminalActionsTests(unittest.TestCase):
    def _assert_safe(self, conversation: Conversation) -> None:
        msg = conversation.captured_data.get(
            f"dynamic_prompt_{conversation.current_step}", ""
        )
        self.assertIn("no puedo validar", msg.lower())
        # NUNCA debe afirmar algo tranquilizador/falso:
        self.assertNotIn("no tienes reportes", msg.lower())
        self.assertNotIn("productos activos", msg.lower())
        self.assertNotIn("historial crediticio sigue intacto", msg.lower())

    def test_all_products_central_risk_no_backdata(self) -> None:
        conv = _conversation("1.4.1.0")
        _load_all_products_central_risk(conv)
        self._assert_safe(conv)

    def test_consulta_sin_permiso_no_backdata(self) -> None:
        conv = _conversation("1.4.1.2")
        _load_products_consulta_sin_permiso(conv)
        self._assert_safe(conv)

    def test_notificacion_centrales_no_backdata(self) -> None:
        conv = _conversation("1.4.1.3")
        _load_products_notificacion_centrales(conv)
        self._assert_safe(conv)


if __name__ == "__main__":
    unittest.main()
