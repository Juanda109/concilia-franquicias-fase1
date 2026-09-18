"""El formulario PQRS se envía como botón {key:"pqr", label:"Formulario PQR"}.

Cubre:
- El router emite el botón `pqr` cuando la señal ``centrales_riesgo_form_option``
  está presente (en vez del link inline en el texto).
- El input_type resuelto es ``choice``.
- El ruteo de ``pqr`` lleva a ``satisfaction_check``.
"""

import json
import unittest

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.workflow_engine import WorkflowEngine
from infrastructure.entrypoint.api.router.v0.chat_router import (
    _build_message_content,
    _resolve_message_input_type,
)


def _formulario_conversation() -> Conversation:
    return Conversation(
        conversation_id="13083558_20260728",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.1.1.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        user_id="13083558",
        captured_data={
            "centrales_riesgo_form_option": json.dumps(
                {"key": "pqr", "label": "Formulario PQR"}, ensure_ascii=False
            )
        },
    )


class PqrFormButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_signal_emits_pqr_button_and_no_link(self) -> None:
        conv = _formulario_conversation()
        content = _build_message_content(
            conversation=conv,
            assistant_content="Para radicar tu solicitud, completa el formulario de PQRS.",
            workflow_engine=self.engine,
        )
        self.assertEqual(
            [(opt.key, opt.label) for opt in content.options],
            [("pqr", "Formulario PQR")],
        )
        self.assertNotIn("http", content.label)

    def test_signal_resolves_choice_input_type(self) -> None:
        conv = _formulario_conversation()
        self.assertEqual(
            _resolve_message_input_type(
                conversation=conv, workflow_engine=self.engine
            ),
            "choice",
        )

    def test_pqr_selection_routes_to_satisfaction(self) -> None:
        conv = _formulario_conversation()
        # Simula que el usuario oprime el botón "Formulario PQR" (key=pqr).
        self.engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")


if __name__ == "__main__":
    unittest.main()
