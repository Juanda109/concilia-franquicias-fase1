"""La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_release_card as rc  # noqa: E402


def test_card_has_every_block_and_the_core_services():
    card = rc.build()
    for key in ("commit", "rama", "imagenes", "configuracion_agente", "conocimiento_y_guardrails", "datasets", "alertas", "cadencias"):
        assert key in card
    services = {row["service"] for row in card["imagenes"]}
    assert {"co_pqrs_back_agent", "co_pqrs_back_trx_noreconocida", "co_pqrs_back_doble_cobro", "co_pqrs_benchmark"} <= services


def test_card_reads_model_and_gates_from_the_dev_configmap():
    cfg = rc.build()["configuracion_agente"]
    assert cfg["LLM_MODEL"] and cfg["LLM_CLOSURE_ENABLED"] in ("true", "false") and cfg["TRX_FLOW_ENABLED"] in ("true", "false")


def test_card_fingerprints_knowledge_and_datasets():
    card = rc.build()
    assert all(info["sha256"] for info in card["conocimiento_y_guardrails"].values())
    names = {row["dataset"] for row in card["datasets"]}
    assert {"doble_cobro_routing.json", "trx_no_reconocida_routing.json", "adversarial_routing.json",
            "bypass_flows.json", "grounding.json", "canario_rutas_criticas.json"} <= names
    assert all(row["casos"] > 0 for row in card["datasets"])


def test_render_is_markdown_with_the_commit_in_the_title():
    card = rc.build()
    text = rc.render(card)
    assert text.startswith(f"# Ficha de versión · {card['commit']}") and "## Datasets" in text


def test_card_reads_the_real_suspend_flag_not_a_comment():
    cadencias = rc.build()["cadencias"]
    assert cadencias["canario"].endswith("(suspendido)")
    assert cadencias["benchmark"].endswith("(suspendido)")
