"""Nivel 1 (pre-filtro): recorta el catalogo de ruteo a las categorias probables.

ADITIVO: no modifica el prompt ni la decision de ruteo existentes. Solo reduce la
lista de WorkflowRoutingEntry que recibe `route_initial_workflow_with_usage`, de
modo que el Nivel 2 sea el ruteo actual, sin cambios, sobre menos candidatos.
"""

from __future__ import annotations

import json

from domain.workflow.models import WorkflowRoutingEntry

# Categorias que SIEMPRE se conservan aunque el pre-filtro no las elija.
# `pqrs` (centrales_de_riesgo) es el destino de 9 de las 12 reglas cross-group
# del catalogo (`no_usar` / `contraejemplos`): si se filtra, esas fronteras
# quedan huerfanas. Cuesta ~1.240 tokens y evita el grueso del error en cascada.
ALWAYS_KEEP_GROUPS: frozenset[str] = frozenset({"pqrs"})

# Tope de categorias que el pre-filtro puede conservar (ademas de ALWAYS_KEEP).
MAX_PREFILTER_GROUPS = 2


def build_group_prefilter_prompt(
    *,
    user_message: str,
    routing_catalog: list[WorkflowRoutingEntry],
) -> str:
    """Prompt minimo del Nivel 1: solo las categorias y su criterio de ruteo."""

    seen: set[str] = set()
    groups: list[dict[str, str]] = []
    for entry in routing_catalog:
        if entry.general_workflow_key in seen:
            continue
        seen.add(entry.general_workflow_key)
        groups.append(
            {
                "key": entry.general_workflow_key,
                "label": entry.general_workflow_label,
                "criterio": entry.routing_criteria or "",
            }
        )

    payload = {"user_message": user_message, "categorias": groups}
    return (
        "Elige las categorias mas probables para la solicitud del usuario usando "
        "SOLO este catalogo.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Reglas:\n"
        "- Devuelve hasta 2 claves en group_keys, la mejor primero.\n"
        "- Usa EXACTAMENTE las claves del catalogo.\n"
        "- Si dudas entre dos categorias, incluye ambas; no arriesgues una sola.\n"
        "- No elijas el tramite concreto: solo la categoria."
    )


def filter_catalog_by_groups(
    *,
    routing_catalog: list[WorkflowRoutingEntry],
    group_keys: list[str],
) -> list[WorkflowRoutingEntry]:
    """Recorta el catalogo a las categorias elegidas. Falla ABIERTO."""

    if not group_keys:
        return routing_catalog

    keep = set(group_keys[:MAX_PREFILTER_GROUPS]) | ALWAYS_KEEP_GROUPS
    filtered = [
        entry for entry in routing_catalog if entry.general_workflow_key in keep
    ]
    # Nunca devolver un catalogo vacio: ante cualquier rareza, el completo.
    return filtered or routing_catalog
