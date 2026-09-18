"""Data-driven builder for the start-phase routing prompt.

Assembles the routing prompt from data so business/domain changes do not require
touching Python:
  - persona + few-shots + fixed output rules -> ``routing_prompt.yml`` (business-editable).
  - per-group ``routing_criteria`` and per-workflow ``description``/``preconditions``/
    ``no_usar``/``contraejemplos`` -> ``general.yml`` (routing catalog).

The guardrail scope suffix is intentionally NOT added here; the agent layer appends it
so this module stays free of guardrail coupling.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml
from domain.workflow.models import WorkflowRoutingEntry
from infrastructure.entrypoint.api.errors.exceptions import ConfigurationError

_PROMPT_FILE = "routing_prompt.yml"


@lru_cache(maxsize=1)
def _load_routing_prompt() -> dict:
    """Load and cache the routing persona/few-shots/rules from ``routing_prompt.yml``."""

    path = Path(__file__).with_name(_PROMPT_FILE)
    if not path.exists():
        raise ConfigurationError(
            "Routing prompt file not found.",
            details={"routing_prompt_path": str(path)},
        )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError(
            "Routing prompt file is invalid.",
            details={"routing_prompt_path": str(path)},
        )
    return data


def _format_few_shots(few_shots: object) -> str:
    """Render the few-shot examples block from the YAML list."""

    if not isinstance(few_shots, list):
        return ""

    blocks: list[str] = []
    index = 1
    for example in few_shots:
        if not isinstance(example, dict):
            continue
        user = str(example.get("user", "")).strip()
        bot = str(example.get("bot", "")).strip()
        if not user or not bot:
            continue
        blocks.append(f"Ejemplo {index}\nUsuario: {user}\nBlue: {bot}")
        index += 1

    if not blocks:
        return ""
    return "<FEW_SHOT_EXAMPLES>\n" + "\n\n".join(blocks) + "\n</FEW_SHOT_EXAMPLES>"


def build_routing_system_prompt() -> str:
    """Build the routing system prompt (persona + few-shots + fixed rules).

    The guardrail scope suffix is appended by the caller.
    """

    data = _load_routing_prompt()
    persona = str(data.get("persona", "")).strip()
    few_shots = _format_few_shots(data.get("few_shots"))
    output_rules = str(data.get("output_rules", "")).strip()

    parts = [part for part in (persona, few_shots, output_rules) if part]
    return "\n\n".join(parts)


def _dedupe_groups(routing_catalog: list[WorkflowRoutingEntry]) -> list[dict]:
    """Return a de-duplicated list of groups with their routing criteria."""

    groups: list[dict] = []
    seen: set[str] = set()
    for entry in routing_catalog:
        if entry.general_workflow_key in seen:
            continue
        seen.add(entry.general_workflow_key)
        groups.append(
            {
                "general_workflow_key": entry.general_workflow_key,
                "general_workflow_label": entry.general_workflow_label,
                "routing_criteria": entry.routing_criteria or "",
            }
        )
    return groups


def build_routing_user_prompt(
    *,
    user_message: str,
    routing_catalog: list[WorkflowRoutingEntry],
) -> str:
    """Build the routing user prompt with the catalog and disambiguation rules."""

    payload = {
        "user_message": user_message,
        "available_groups": _dedupe_groups(routing_catalog),
        "available_workflows": [
            # `steps_preview` se excluye a proposito: describe los PASOS internos de
            # cada flujo, y el ruteo decide A QUE FLUJO entrar, no que paso ejecutar.
            # Solo aporta vocabulario generico (hasta 2.051 tokens cuando entra
            # trx_no_reconocida) y ademas es asimetrico: los FAQ no aportan ninguno
            # porque sus step-id no son numericos. El objeto lo conserva, asi que el
            # fallback lexico (_score_routing_entry) sigue funcionando igual.
            entry.model_dump(exclude={"routing_criteria", "steps_preview"})
            for entry in routing_catalog
        ],
    }

    return (
        "Clasifica la solicitud inicial del usuario usando SOLO el siguiente catalogo.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Como decidir:\n"
        "- Primero ubica la categoria por available_groups.routing_criteria y luego elige el "
        "workflow dentro de esa categoria.\n"
        "- Match positivo: compara el mensaje con description, examples y preconditions del workflow.\n"
        "- NEGATIVOS: si el mensaje encaja en un contraejemplo o en un caso de no_usar, ese NO es el "
        "workflow; rutea al que indica esa nota.\n"
        "- Usa se_confunde_con para separar workflows vecinos.\n"
        "- Si is_match=true, general_workflow_key y workflow deben existir EXACTAMENTE en el catalogo.\n"
        "- Si es un saludo o cortesia sin necesidad concreta, is_match=false y redacta un "
        "clarification_message calido.\n"
        "- Si es ambiguo pero hay un mejor candidato, is_match=true con confidence=low."
    )
