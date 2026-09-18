"""Routing catalog and data-driven routing prompt tests (LLM-free).

These verify the enriched catalog and the generated routing prompt WITHOUT calling
the model: they check that disambiguation data is present and coherent, that the
buggy hardcoded guidance was removed, and that the datacredito removal intent maps
to centrales_de_riesgo instead of paz_y_salvo.
"""

import re
import unittest

from domain.workflow.routing_prompt_builder import (
    build_routing_system_prompt,
    build_routing_user_prompt,
)
from domain.workflow.workflow_engine import WorkflowEngine


class RoutingCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()
        cls.catalog = cls.engine.build_routing_catalog()
        cls.by_workflow = {entry.workflow: entry for entry in cls.catalog}

    def test_catalog_has_all_workflows(self) -> None:
        self.assertEqual(len(self.catalog), 21)
        for workflow in (
            "paz_y_salvo",
            "centrales_de_riesgo",
            "certificado_tributario",
            "impuesto_4x1000",
            "trx_no_reconocida",
            "faq_cuenta_embargada",
        ):
            self.assertIn(workflow, self.by_workflow)

    def test_trx_no_reconocida_group_and_limit_category(self) -> None:
        trx = self.by_workflow["trx_no_reconocida"]
        self.assertEqual(trx.general_workflow_key, "trx_no_reconocida")
        self.assertTrue((trx.routing_criteria or "").strip())
        self.assertTrue(trx.description)
        self.assertTrue(trx.preconditions)
        self.assertGreaterEqual(len(trx.examples), 12)
        # New independent daily-cap layer.
        self.assertEqual(
            self.engine.get_limit_category("trx_no_reconocida"), "trx_no_reconocida"
        )
        self.assertIn("trx_no_reconocida", self.engine.get_all_limit_categories())

    def test_new_disambiguation_fields_are_populated(self) -> None:
        pys = self.by_workflow["paz_y_salvo"]
        self.assertTrue(pys.description)
        self.assertTrue(pys.preconditions)
        self.assertIn("centrales_de_riesgo", (pys.no_usar or ""))
        self.assertTrue(
            any("datacredito" in c.lower() for c in pys.contraejemplos),
            "paz_y_salvo debe listar el reclamo de datacredito como contraejemplo",
        )

    def test_centrales_examples_cover_removal_intent(self) -> None:
        centrales = self.by_workflow["centrales_de_riesgo"]
        joined = " ".join(centrales.examples).lower()
        self.assertIn("quiten", joined)
        self.assertIn("datacredito", joined)

    def test_datacredito_removal_is_not_a_paz_y_salvo_example(self) -> None:
        # The original bug: "quitar reporte de datacredito" matched paz_y_salvo.
        pys = self.by_workflow["paz_y_salvo"]
        for example in pys.examples:
            low = example.lower()
            self.assertFalse(
                "quiten" in low and "datacredito" in low,
                f"Ejemplo ambiguo en paz_y_salvo: {example}",
            )

    def test_contraejemplos_reference_existing_workflows(self) -> None:
        keys = set(self.by_workflow)
        for entry in self.catalog:
            for contra in entry.contraejemplos:
                for target in re.findall(r"->\s*([a-z0-9_]+)", contra):
                    self.assertIn(
                        target,
                        keys,
                        f"{entry.workflow}: contraejemplo apunta a workflow inexistente '{target}'",
                    )

    def test_every_group_has_routing_criteria(self) -> None:
        criteria = {e.general_workflow_key: e.routing_criteria for e in self.catalog}
        for group in ("hazlo_tu_mismo", "guia_rapida", "pqrs", "preguntas_frecuentes"):
            self.assertTrue(
                (criteria.get(group) or "").strip(),
                f"El grupo {group} debe tener routing_criteria",
            )


class RoutingPromptBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()
        cls.catalog = cls.engine.build_routing_catalog()

    def test_system_prompt_has_persona_and_fewshots(self) -> None:
        system_prompt = build_routing_system_prompt()
        self.assertIn("Blue", system_prompt)
        self.assertIn("FEW_SHOT_EXAMPLES", system_prompt)
        # Business few-shot that fixes the bug (datacredito -> aclarar en centrales).
        self.assertIn("Datacredito", system_prompt)
        # Negatives rule present in the fixed output rules.
        self.assertIn("contraejemplos", system_prompt.lower())

    def test_system_prompt_drops_buggy_hardcoded_line(self) -> None:
        system_prompt = build_routing_system_prompt().lower()
        self.assertNotIn("paz y salvo para que me quiten el reporte", system_prompt)

    def test_user_prompt_includes_groups_workflows_and_negatives(self) -> None:
        user_prompt = build_routing_user_prompt(
            user_message="Estoy reportado y necesito que me quiten ese reporte de datacredito",
            routing_catalog=self.catalog,
        )
        self.assertIn("available_groups", user_prompt)
        self.assertIn("available_workflows", user_prompt)
        self.assertIn("routing_criteria", user_prompt)
        self.assertIn("contraejemplos", user_prompt)
        self.assertIn("no_usar", user_prompt)


if __name__ == "__main__":
    unittest.main()
