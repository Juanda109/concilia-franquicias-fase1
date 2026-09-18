"""Item 4: the PQRS form must NOT be rendered as a button, only inline in text.

Buttons are reserved for step menus / satisfaction / continuar-salir / product
selection. The radicar_pqrs "form option" must never appear as an option.
"""

from __future__ import annotations

import unittest

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.workflow_engine import WorkflowEngine
from infrastructure.entrypoint.api.router.v0.chat_router import _build_message_content


class PqrsNotButtonTests(unittest.TestCase):
    def test_pqrs_form_option_is_not_a_button(self) -> None:
        engine = WorkflowEngine()
        conversation = Conversation(
            conversation_id="123_20260717",
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.2",
            general_workflow="PQRs",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={},
            captured_data={
                "centrales_riesgo_form_option": (
                    '{"key": "radicar_pqrs", "label": "https://peticiones.bbva.com.co/"}'
                )
            },
            user_id="123",
            messages=[],
        )

        content = _build_message_content(
            conversation=conversation,
            assistant_content=(
                "Tu caso requiere revisión. Radica aquí: "
                "[Formulario de PQRS](https://peticiones.bbva.com.co/)"
            ),
            workflow_engine=engine,
        )

        keys = [opt.key for opt in content.options]
        self.assertNotIn("radicar_pqrs", keys)
        # El PQRS sigue disponible como link inline en el texto del mensaje.
        self.assertIn("peticiones.bbva.com.co", content.label)


if __name__ == "__main__":
    unittest.main()
