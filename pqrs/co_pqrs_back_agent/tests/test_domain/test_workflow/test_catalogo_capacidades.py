"""Contrato del catalogo de capacidades (KYNS IT 4).

Tres cosas que no pueden romperse sin que alguien lo vea:
1. toda accion declarada en un YAML esta en la allowlist, y la allowlist no
   arrastra acciones muertas;
2. todo camino del YAML hacia una accion con efecto pasa por sus puertas, y el
   codigo no salta directo a esos pasos;
3. el catalogo publicado en docs/ es el generado desde el YAML actual.
"""

import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(AGENT / "scripts"))

import build_capability_catalog as cat  # noqa: E402


@pytest.fixture(scope="module")
def catalog():
    return cat.build()


def test_every_yaml_action_is_in_the_allowlist(catalog):
    declared = set(cat.yaml_actions())
    unclassified = sorted(a["action"] for a in catalog["actions"] if a["class"] == "SIN_CLASIFICAR")
    assert not unclassified, f"acciones en YAML sin clasificar: {unclassified}"
    dead = sorted(set(cat.ACTION_CLASSES) - declared)
    assert not dead, f"acciones en la allowlist que ningun YAML declara: {dead}"


def test_every_class_is_known_and_effect_actions_are_few(catalog):
    assert all(a["class"] in cat.CLASS_LABELS for a in catalog["actions"])
    effect = sorted(a["action"] for a in catalog["actions"] if a["class"] in cat.EFFECT_CLASSES)
    assert effect == sorted(cat.FINANCIAL_GATES), "toda accion con efecto necesita sus puertas en FINANCIAL_GATES"


def test_effect_actions_never_start_a_flow():
    for flow, path in cat.flow_files().items():
        start, steps = cat.flow_steps(path)
        action = str((steps.get(start) or {}).get("action") or "")
        assert cat.ACTION_CLASSES.get(action, ("", "", "", ""))[0] not in cat.EFFECT_CLASSES, (flow, start, action)


def test_all_paths_to_effect_actions_cross_their_gates(catalog):
    for action, g in catalog["gates"].items():
        assert g["paths"] >= 1, f"{action}: ningun camino desde el inicio del flujo"
        assert not g["missing_gates"], f"{action}: hay un camino que se salta {g['missing_gates']}"


def test_code_never_jumps_directly_into_an_effect_step(catalog):
    assert catalog["direct_jumps"] == {}, catalog["direct_jumps"]


def test_refund_only_after_the_customer_confirms_and_the_rules_pass(catalog):
    mandatory = set(catalog["gates"]["registrar_devolucion_trx"]["mandatory"])
    # La confirmacion del cliente (2.4.0.1.11) y las dos reglas (2.4.0.1.12, 2.4.0.1.19)
    # son innegociables aunque alguien reordene el YAML.
    assert {"2.4.0.1.11", "2.4.0.1.12", "2.4.0.1.19"} <= mandatory


def test_blocks_require_app_authorization_step(catalog):
    assert "2.4.0.1.16.1" in catalog["gates"]["bloqueo_temporal_trx"]["mandatory"]
    assert "2.4.0.1.17.1" in catalog["gates"]["bloqueo_permanente_trx"]["mandatory"]


def test_published_catalog_is_up_to_date(catalog):
    assert cat.OUT_MD.read_text(encoding="utf-8") == cat.render(catalog), (
        "regenerar con: uv run python scripts/build_capability_catalog.py"
    )
