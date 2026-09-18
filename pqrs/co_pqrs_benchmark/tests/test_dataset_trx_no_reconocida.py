"""El dataset de ruteo de trx_no_reconocida esta bien formado y cubre sus vecinos.

Los vecinos son los que el propio catalogo declara en `se_confunde_con`: si el
catalogo agrega un vecino nuevo, este test exige un caso frontera para el.
"""

import json
import re
from pathlib import Path

import yaml

from src.benchmark.job import _validate_dataset

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "datasets" / "trx_no_reconocida_routing.json"
CATALOG = ROOT.parent / "co_pqrs_back_agent" / "src" / "domain" / "workflow" / "general.yml"


def _cases():
    return json.loads(DATASET.read_text())


def _catalog_option():
    catalog = yaml.safe_load(CATALOG.read_text())
    for group in catalog["welcome"]["groups"]:
        for option in (group.get("options") or []):
            if option.get("key") == "trx_no_reconocida":
                return option
    raise AssertionError("trx_no_reconocida no esta en el catalogo")


def test_dataset_validates_clean_and_has_enough_cases():
    cases = _cases()
    assert len(cases) >= 30
    assert _validate_dataset(cases) == 0
    assert all(case["nota"].split(":")[0].split(" ")[0] in
               {"sanity", "generalizacion", "frontera", "desambiguacion"} for case in cases)


def test_every_declared_neighbour_has_a_boundary_case():
    option = _catalog_option()
    neighbours = {n.strip() for n in option["se_confunde_con"].split(",")}
    covered = {case["expect_output"] for case in _cases()}
    assert neighbours <= covered, f"vecinos sin caso frontera: {sorted(neighbours - covered)}"
    assert "pqrs_no_ruteo" in covered  # cobros recurrentes y rutas no disponibles


def test_sanity_cases_are_literal_catalog_examples():
    option = _catalog_option()
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower().translate(str.maketrans("áéíóúñ", "aeioun")))
    examples = {norm(e) for e in option["examples"]}
    sanity = [c for c in _cases() if c["nota"].startswith("sanity")]
    assert sanity
    for case in sanity:
        assert norm(case["question"]) in examples, case["question"]


def test_disambiguation_cases_carry_a_follow_up():
    for case in _cases():
        if case["nota"].startswith("desambiguacion"):
            assert case.get("follow_ups"), case["question"]
