"""Lint de estilo (capa C4): tuteo consistente y promesas controladas.

Dos frentes: que el detector detecte (violaciones sembradas) y que el corpus
real este limpio (gate de regresion sobre TODOS los YAML de workflows: si un
copy nuevo trata al cliente de usted o promete un abono fuera de un terminal
de confirmacion, esta suite lo frena antes del despliegue).
"""

import unittest

from domain.workflow.style_lint import check_promise, check_text, lint_workflows


class CheckTextTests(unittest.TestCase):
    def _rules(self, text: str) -> set[str]:
        return {rule for rule, _ in check_text(text)}

    def test_clean_tuteo_passes(self) -> None:
        self.assertEqual(
            self._rules(
                "Selecciona la fecha en la que identificas el cobro duplicado. "
                "Consulta la fecha en tu extracto y verifica tus movimientos."
            ),
            set(),
        )

    def test_usted_pronoun_is_flagged(self) -> None:
        self.assertIn("usted_pronombre", self._rules("¿Usted ya revisó el cobro?"))

    def test_usted_imperative_is_flagged(self) -> None:
        self.assertIn(
            "usted_imperativo",
            self._rules("Seleccione el producto e ingrese el monto."),
        )

    def test_usted_possessive_is_flagged(self) -> None:
        self.assertIn(
            "posesivo_usted", self._rules("Verás el abono en su cuenta.")
        )

    def test_third_person_subjunctive_is_not_usted(self) -> None:
        """"que un equipo revise tu caso" es subjuntivo, no usted."""

        self.assertEqual(
            self._rules(
                "Para que nuestro equipo de especialistas revise tu caso, "
                "completa el siguiente formulario."
            ),
            set(),
        )

    def test_mixed_tone_still_flags_the_usted_half(self) -> None:
        rules = self._rules("Cuéntame tu solicitud y luego ingrese el monto.")
        self.assertIn("usted_imperativo", rules)


class CheckPromiseTests(unittest.TestCase):
    _PROMISE = "Identificamos el cobro duplicado y realizamos el abono a tu cuenta."

    def test_promise_allowed_in_confirmation_terminals(self) -> None:
        for step_id in ("3.4.0.8.aprobado", "3.4.0.8.pendiente", "3.4.0.5.recurrente"):
            self.assertEqual(check_promise(step_id, self._PROMISE), [], step_id)

    def test_promise_outside_confirmation_is_flagged(self) -> None:
        for step_id in ("3.4.0.8.no_procede", "3.4.0", "satisfaction_check"):
            self.assertTrue(check_promise(step_id, self._PROMISE), step_id)

    def test_neutral_text_never_flags(self) -> None:
        self.assertEqual(
            check_promise("3.4.0", "Estoy validando los tiempos de conciliación."),
            [],
        )


class CorpusGateTests(unittest.TestCase):
    def test_all_workflow_copy_is_clean(self) -> None:
        """Gate de regresion: todo el copy visible tutea y no promete de mas."""

        violations = lint_workflows()
        self.assertEqual(
            violations,
            [],
            "\n".join(str(violation) for violation in violations),
        )


if __name__ == "__main__":
    unittest.main()
