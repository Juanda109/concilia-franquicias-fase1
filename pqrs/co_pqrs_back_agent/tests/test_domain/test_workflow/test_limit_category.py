"""Tests for the data-driven daily-interaction limit category mapping."""

import unittest

from domain.workflow.workflow_engine import WorkflowEngine


class LimitCategoryMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_centrales_group_maps_to_centrales(self) -> None:
        self.assertEqual(
            self.engine.get_limit_category("centrales_de_riesgo"), "centrales"
        )

    def test_faq_workflow_maps_to_general(self) -> None:
        self.assertEqual(
            self.engine.get_limit_category("faq_plazos_reporte_negativo"), "general"
        )

    def test_guia_rapida_workflow_maps_to_general(self) -> None:
        self.assertEqual(self.engine.get_limit_category("impuesto_4x1000"), "general")

    def test_hazlo_tu_mismo_workflow_maps_to_general(self) -> None:
        self.assertEqual(self.engine.get_limit_category("paz_y_salvo"), "general")

    def test_unknown_workflow_falls_back_to_general(self) -> None:
        self.assertEqual(
            self.engine.get_limit_category("workflow_inexistente"), "general"
        )


class LimitKeyPerCaseTests(unittest.TestCase):
    """The per-CASE limit key is the workflow itself (not the shared group
    category), so every case has its own daily counter."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_key_is_the_workflow_name(self) -> None:
        self.assertEqual(
            self.engine.get_limit_key("impuesto_4x1000"), "impuesto_4x1000"
        )
        self.assertEqual(self.engine.get_limit_key("paz_y_salvo"), "paz_y_salvo")

    def test_two_cases_of_same_group_have_distinct_keys(self) -> None:
        # Both are in the "general" limit category but must NOT share a counter.
        self.assertNotEqual(
            self.engine.get_limit_key("impuesto_4x1000"),
            self.engine.get_limit_key("cuota_de_manejo"),
        )

    def test_unknown_workflow_falls_back(self) -> None:
        self.assertEqual(
            self.engine.get_limit_key("workflow_inexistente"), "workflow_inexistente"
        )


if __name__ == "__main__":
    unittest.main()
