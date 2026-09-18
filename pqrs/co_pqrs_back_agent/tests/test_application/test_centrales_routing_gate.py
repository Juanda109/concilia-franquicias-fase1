"""Tests del keyword-gate de centrales (acote minimo).

Tras el acote (2026-08), el gate SOLO dispara si el mensaje menciona
explicitamente "centrales" o una central por nombre (datacredito/transunion/cifin).
Los terminos genericos ("reportado", "me reportaron", "reporte negativo") ya NO
disparan: los rutea el LLM y, ante no-match, es preferible el formulario a forzar
centrales por una palabra suelta.
"""

from __future__ import annotations

import unittest

from application.chat.chat_service import (
    _looks_like_centrales_case,
    _resolve_routing_entry_hint,
)


class CentralesRoutingGateTests(unittest.TestCase):
    def test_explicit_centrales_cases_are_detected(self) -> None:
        cases = [
            "Tengo un reporte en centrales de riesgo",
            "Tengo un reporte en centrales",
            "reportado en centrales",
            "me reportaron en centrales",
            "Aparezco reportado en Datacredito",
            "quiero que me quiten mi reporte de datacredito",
            "salir de datacredito",
            "tengo un embargo en centrales de riesgo",
        ]
        for text in cases:
            self.assertTrue(_looks_like_centrales_case(text), text)

    def test_generic_report_terms_no_longer_trigger(self) -> None:
        # Sin mencionar "centrales" ni una central por nombre, el gate NO dispara.
        non_cases = [
            "estoy reportado y quiero saber por que",
            "tengo un reporte negativo",
            "me reportaron",
        ]
        for text in non_cases:
            self.assertFalse(_looks_like_centrales_case(text), text)

    def test_transaction_block_and_freeze_are_not_centrales(self) -> None:
        # Casos reales que antes eran secuestrados a centrales por una palabra.
        non_cases = [
            "me reportaron los movimientos de mi compra como fraudulentos",
            "necesito desbloquear mi cuenta de nomina",
            "me congelaron mi dinero estando al dia en mis obligaciones",
            "me bloquearon todos mis productos y no puedo usarlos",
        ]
        for text in non_cases:
            self.assertFalse(_looks_like_centrales_case(text), text)

    def test_unrelated_and_empty_are_not_detected(self) -> None:
        for text in ["hola", "quiero una pizza", "como descargo mi extracto", "", None]:
            self.assertFalse(_looks_like_centrales_case(text), text)


class CentralesEntryHintTests(unittest.TestCase):
    """El auto-entry al sub-flujo de centrales SOLO con ancla explicita."""

    def _hint(self, user_content: str, rationale: str = "") -> str | None:
        return _resolve_routing_entry_hint(
            workflow="centrales_de_riesgo",
            user_content=user_content,
            rationale=rationale,
        )

    def test_explicit_anchors_auto_enter(self) -> None:
        self.assertEqual(self._hint("tengo un reporte en centrales de riesgo"), "centrales_de_riesgo")
        self.assertEqual(self._hint("aparezco reportado en datacredito"), "centrales_de_riesgo")
        self.assertEqual(self._hint("tengo un embargo en centrales"), "centrales_de_riesgo")

    def test_bare_terms_do_not_auto_enter(self) -> None:
        # Sin "centrales"/buro: se muestra el menu (None), no se salta al sub-flujo.
        self.assertIsNone(self._hint("me hicieron un embargo y necesito una certificacion de ese retiro"))
        self.assertIsNone(self._hint("me reportaron los movimientos de mi compra como fraudulentos"))
        self.assertIsNone(self._hint("tengo un reporte negativo"))

    def test_other_workflows_never_get_hint(self) -> None:
        self.assertIsNone(
            _resolve_routing_entry_hint(
                workflow="cuota_de_manejo",
                user_content="me cobran cuota de manejo",
                rationale="",
            )
        )


if __name__ == "__main__":
    unittest.main()
