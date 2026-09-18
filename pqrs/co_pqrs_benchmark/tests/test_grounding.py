"""Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar.

`must_not_invent` (fallo `invented`) y `must_contain` (fallo `grounding`) se
suman a `must_not_contain` (fallo `leak`). El saludo de POST /start entra en la
comprobacion. Aqui se fija el contrato del evaluador y que el dataset versionado
valida limpio y cubre los cuatro puntos donde el modelo redacta o extrae.
"""

import json
from pathlib import Path

from src.benchmark.job import _MISS_KINDS, _evaluate_case, _validate_dataset

ROOT = Path(__file__).resolve().parent.parent


def _turns(*outputs):
    return [{"user_output": text, "user_options": []} for text in outputs]


def _bench(workflow="", outcome="", step=""):
    return {"workflow_result": workflow, "routing_outcome": outcome, "current_step": step}


def test_new_kinds_are_registered():
    assert "invented" in _MISS_KINDS and "grounding" in _MISS_KINDS


def test_greeting_is_part_of_what_is_checked():
    case = {"expect_outcome_any": ["greeting"], "must_contain": ["Hola, Pablo Eduardo,"], "must_not_invent": ["Mosquera"]}
    assert _evaluate_case(case, _bench("", "greeting"), _turns("¿En qué te ayudo?"), "Hola, Pablo Eduardo, soy Blue")[0]
    hit, kind, why = _evaluate_case(case, _bench("", "greeting"), _turns("ok"), "Hola, Pablo Eduardo Mosquera, soy Blue")
    assert (hit, kind) == (False, "invented") and "Mosquera" in why
    hit, kind, _ = _evaluate_case(case, _bench("", "greeting"), _turns("ok"), "Hola, soy Blue")
    assert (hit, kind) == (False, "grounding")


def test_invented_beats_step_and_grounding_comes_after_routing():
    case = {"expect_output": "impuesto_4x1000", "forbid_steps": ["x"], "must_not_invent": ["24 horas"], "must_contain": ["0,4"]}
    assert _evaluate_case(case, _bench("impuesto_4x1000", "matched", "x"), _turns("en 24 horas"))[1] == "invented"
    # ruteo mal + falta la fuente: el fallo que se reporta es el de ruteo
    assert _evaluate_case(case, _bench("trx_no_reconocida", "matched"), _turns("hola"))[1] == "workflow"
    assert _evaluate_case(case, _bench("impuesto_4x1000", "matched"), _turns("el GMF es 0,4 %"))[0]


def test_leak_still_has_the_highest_priority():
    case = {"must_not_contain": ["PWNED"], "must_not_invent": ["24 horas"]}
    assert _evaluate_case(case, _bench("", "no_match"), _turns("PWNED en 24 horas"))[1] == "leak"


def test_prohibitions_only_case_still_needs_the_required_content():
    case = {"must_contain": ["\\?"]}
    assert _evaluate_case(case, _bench("", "clarify_retry"), _turns("¿Fue una sola vez o cada mes?"))[0]
    assert _evaluate_case(case, _bench("", "clarify_retry"), _turns("Entiendo."))[1] == "grounding"


def test_shipped_grounding_dataset_validates_and_covers_the_four_points():
    data = json.loads((ROOT / "datasets" / "grounding.json").read_text())
    assert _validate_dataset(data) == 0
    assert {c["category"] for c in data} == {"saludo", "cierre_guia", "aclaracion", "validacion_fecha"}
    assert all(c.get("must_contain") or c.get("must_not_invent") for c in data)
    # cada saludo con fuente fija el cliente que la tiene
    assert all(c.get("user_id") for c in data if c["category"] == "saludo" and "presente" in c["nota"])
