"""Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots).

El ruteo real lo decide el LLM con el catalogo como insumo, por lo que aqui se
verifica que las senales negativas clave existan en la configuracion (no que el
LLM las use). Protege contra borrados accidentales de estos negativos.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

_WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "src" / "domain" / "workflow"


def _load(name: str):
    with (_WORKFLOW_DIR / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _option(catalog: dict, group_key: str, option_key: str) -> dict:
    group = next(g for g in catalog["welcome"]["groups"] if g["key"] == group_key)
    return next(o for o in group["options"] if o["key"] == option_key)


class CatalogBlockNegativesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = _load("general.yml")

    def test_centrales_no_usar_excludes_product_block(self) -> None:
        centrales = _option(self.catalog, "pqrs", "centrales_de_riesgo")
        no_usar = centrales["no_usar"].lower()
        self.assertIn("bloqueo", no_usar)
        self.assertIn("productos", no_usar)
        self.assertIn("formulario", no_usar)

    def test_centrales_contraejemplos_include_block_and_salary(self) -> None:
        centrales = _option(self.catalog, "pqrs", "centrales_de_riesgo")
        joined = " ".join(centrales["contraejemplos"]).lower()
        self.assertIn("bloquearon todos mis productos", joined)
        self.assertIn("sueldo a la tarjeta", joined)

    def test_centrales_no_usar_excludes_transaction_and_scopes_desembargo(self) -> None:
        centrales = _option(self.catalog, "pqrs", "centrales_de_riesgo")
        no_usar = centrales["no_usar"].lower()
        # Retiro/transaccion, bloqueo y congelamiento no-embargo -> formulario.
        self.assertIn("retiro", no_usar)
        self.assertIn("bloqueo", no_usar)
        self.assertIn("formulario", no_usar)
        # Embargo/DESEMBARGO (estado) SI es centrales (no se excluye).
        self.assertIn("desembargo", no_usar)

    def test_centrales_examples_include_desembargo(self) -> None:
        centrales = _option(self.catalog, "pqrs", "centrales_de_riesgo")
        examples = " ".join(centrales["examples"]).lower()
        self.assertIn("desembargo", examples)

    def test_centrales_contraejemplos_include_freeze_and_certification(self) -> None:
        centrales = _option(self.catalog, "pqrs", "centrales_de_riesgo")
        joined = " ".join(centrales["contraejemplos"]).lower()
        self.assertIn("congelaron mi dinero", joined)
        self.assertIn("certificacion de un retiro", joined)

    def test_embargada_no_usar_excludes_full_product_block(self) -> None:
        embargada = _option(self.catalog, "guia_rapida", "faq_cuenta_embargada")
        no_usar = embargada["no_usar"].lower()
        self.assertIn("todos los productos", no_usar)


class RoutingPromptFewShotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt = _load("routing_prompt.yml")

    def test_has_greeting_and_block_few_shots(self) -> None:
        users = " ".join(fs.get("user", "") for fs in self.prompt["few_shots"]).lower()
        self.assertIn("buena tarde", users)          # saludo coloquial
        self.assertIn("bloquearon todos mis productos", users)  # bloqueo != centrales

    def test_greeting_few_shot_uses_canonical_welcome(self) -> None:
        catalog = _load("general.yml")
        welcome = catalog["welcome"]["message"].strip().lower()
        bots = " ".join(fs.get("bot", "") for fs in self.prompt["few_shots"]).lower()
        # El saludo del few_shot reutiliza el mensaje canonico de bienvenida.
        self.assertIn(welcome, bots)

    def test_has_freeze_and_embargo_state_few_shots(self) -> None:
        users = " ".join(fs.get("user", "") for fs in self.prompt["few_shots"]).lower()
        self.assertIn("congelan parte de mi dinero", users)   # congelamiento -> PQRS
        self.assertIn("esta embargada", users)                # consulta de estado -> centrales
        self.assertIn("desembargo", users)                    # desembargo -> centrales

    def test_output_rules_prioritize_action_over_theme(self) -> None:
        rules = self.prompt["output_rules"].lower()
        self.assertIn("prioriza la accion sobre el tema", rules)
        self.assertIn("formulario pqrs", rules)


if __name__ == "__main__":
    unittest.main()
