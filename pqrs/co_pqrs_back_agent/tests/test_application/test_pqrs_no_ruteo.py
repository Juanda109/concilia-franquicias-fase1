"""Flujo interno pqrs_no_ruteo: pregunta del banco sin ruteo -> formulario PQRS.

Cuando el ruteo no encuentra flujo (no-match), la conversación entra al workflow
interno ``pqrs_no_ruteo`` (no seleccionable/ruteable), que muestra el texto único
de formulario PQRS y el botón ``pqr`` -> ``satisfaction_check``.
"""

import unittest

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.workflow_engine import WorkflowEngine

_PQRS_FORM_TEXT = (
    "Tu caso requiere una revisión a fondo por parte de nuestro equipo "
    "especializado. Para radicar tu solicitud, por favor completa el "
    "siguiente formulario. Así podremos analizar lo ocurrido con tu reporte "
    "y darte una respuesta oficial."
)


class PqrsNoRuteoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def _conversation(self) -> Conversation:
        return Conversation(
            conversation_id="7667553_20260728",
            status=ConversationStatus.ACTIVE,
            current_step="1",
            workflow="pqrs_no_ruteo",
            flow_version=1,
            user_id="7667553",
        )

    def test_internal_workflow_is_loaded_with_shared_steps(self) -> None:
        self.assertIn("pqrs_no_ruteo", self.engine.catalog.flows)
        steps = self.engine.catalog.flows["pqrs_no_ruteo"].steps
        # shared_steps (satisfaction_check / si / no) deben quedar mergeados.
        self.assertIn("satisfaction_check", steps)
        self.assertIn("satisfaction_si", steps)
        self.assertIn("satisfaction_no", steps)

    def test_entry_step_renders_unified_pqrs_text_and_pqr_option(self) -> None:
        conv = self._conversation()
        prompt = self.engine.render_current_step_prompt(conv)
        self.assertEqual(prompt.strip(), _PQRS_FORM_TEXT)
        _, step = self.engine.get_current_step(conv)
        self.assertEqual([(o.key, o.label) for o in step.options], [("pqr", "Formulario PQR")])

    def test_pqr_button_routes_to_satisfaction_check(self) -> None:
        conv = self._conversation()
        self.engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")


if __name__ == "__main__":
    unittest.main()
