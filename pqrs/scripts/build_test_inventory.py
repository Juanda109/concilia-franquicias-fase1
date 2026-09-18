#!/usr/bin/env python3
"""Inventario de tests por control KYNS IT, generado desde las suites.

Recorre los ficheros de test de los servicios, lee cada test (función o
método) con la primera línea de su docstring, o la de su clase o módulo si no
tiene, y lo asigna a controles según el fichero. El resultado es el anexo del
informe técnico que pide RCS: qué prueba existe, qué demuestra y cómo se corre.

    python scripts/build_test_inventory.py            # escribe docs/INVENTARIO_TESTS.md
    python scripts/build_test_inventory.py --json     # y docs/inventario_tests.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "docs" / "INVENTARIO_TESTS.md"
OUT_JSON = ROOT / "docs" / "inventario_tests.json"

SERVICES = {
    "co_pqrs_back_agent": "cd co_pqrs_back_agent && RABBITMQ_ENABLED=false uv run pytest -q",
    "co_pqrs_benchmark": "cd co_pqrs_benchmark && uv run --python 3.14 --with pyyaml --with pytest --with-requirements requirements.txt pytest -q",
    "co_pqrs_back_trx_noreconocida": "cd co_pqrs_back_trx_noreconocida && uv run pytest -q",
    "co_pqrs_back_doble_cobro": "cd co_pqrs_back_doble_cobro && uv run pytest -q",
    "co_pqrs_back_data": "cd co_pqrs_back_data && uv run pytest -q",
    "co_pqrs_back_error_handler": "cd co_pqrs_back_error_handler && uv sync --extra test && uv run pytest -q",
}

# fichero (regex sobre la ruta relativa) -> controles que evidencia
CONTROL_MAP: list[tuple[str, list[str]]] = [
    (r"test_adversarial\.py", ["IT1.4", "IT3.4", "IT3.5", "IT4.3"]),
    (r"test_grounding\.py", ["IT1.3"]),
    (r"test_dataset_trx_no_reconocida\.py|test_dataset_configmap\.py", ["IT1.2"]),
    (r"test_release_card\.py", ["IT1.6", "IT2.2"]),
    (r"test_events\.py|test_job_events\.py|test_job\.py|test_metrics", ["IT1.2", "IT2.3"]),
    (r"test_catalogo_capacidades\.py", ["IT4.2"]),
    (r"test_integridad_financiera\.py", ["IT3.3", "IT4.4", "IT4.5"]),
    (r"test_category_cap_flow\.py|test_limit_category\.py", ["IT4.6"]),
    (r"test_hardening\.py", ["IT4.4", "IT4.5"]),
    (r"test_trx_flow\.py|test_trx_orchestration\.py|test_trx_state\.py|test_trx_autorizacion", ["IT4.2", "IT4.5", "IT4.7"]),
    (r"test_doble_cobro_flow\.py", ["IT4.2", "IT4.4", "IT4.5"]),
    (r"test_event_source\.py|test_metrics_events\.py", ["IT4.7", "IT2.3"]),
    (r"test_trace_sanitizer\.py|trazas_sin_secretos|test_commercial_info_trace|test_aso_debug\.py|test_aso_client\.py", ["IT3.2", "IT3.6", "IT3.7"]),
    (r"guardrail", ["IT3.5", "IT1.4"]),
    (r"test_qa_routing_cases\.py|test_centrales_routing_gate\.py|test_pqrs_no_ruteo\.py", ["IT1.2"]),
    (r"test_trx_canary_gate\.py", ["IT2.6"]),
    (r"test_workflow_actions\.py|test_product_options\.py", ["IT4.2"]),
    (r"test_chat_service\.py", ["IT1.2", "IT4.5"]),
    (r"test_tantia_export\.py|tantia", ["IT4.8"]),
]


def first_line(doc: str | None) -> str:
    if not doc:
        return ""
    line = doc.strip().splitlines()[0].strip()
    return re.sub(r"\s+", " ", line)


def collect(service: str) -> list[dict]:
    base = ROOT / service
    rows = []
    for path in sorted(base.rglob("test_*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(path.relative_to(ROOT))
        module_doc = first_line(ast.get_docstring(tree))
        controls = sorted({c for pattern, cs in CONTROL_MAP if re.search(pattern, rel) for c in cs})

        def add(name: str, doc: str, cls_doc: str = "") -> None:
            rows.append({
                "service": service, "file": rel, "test": name,
                "proves": doc or cls_doc or module_doc, "controls": controls,
            })

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                add(node.name, first_line(ast.get_docstring(node)))
            elif isinstance(node, ast.ClassDef):
                cls_doc = first_line(ast.get_docstring(node))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                        add(f"{node.name}::{sub.name}", first_line(ast.get_docstring(sub)), cls_doc)
    return rows


def render(rows: list[dict]) -> str:
    L = ["# Inventario de tests por control KYNS IT", "",
         "> Generado por `scripts/build_test_inventory.py` desde las suites. Cada test aparece con la primera",
         "> línea de su docstring (o la de su clase o módulo) y los controles que evidencia según su fichero.",
         "> Un test sin control asignado es cobertura funcional general.", ""]
    by_service: dict[str, list[dict]] = {}
    for r in rows:
        by_service.setdefault(r["service"], []).append(r)
    L += ["## Resumen", "", "| Servicio | Tests | Con control asignado | Cómo se corre |", "|---|---|---|---|"]
    for s, rs in by_service.items():
        L.append(f"| {s} | {len(rs)} | {sum(1 for r in rs if r['controls'])} | `{SERVICES[s]}` |")
    L.append("")
    per_control: dict[str, list[dict]] = {}
    for r in rows:
        for c in r["controls"]:
            per_control.setdefault(c, []).append(r)
    L += ["## Tests por control", ""]
    for c in sorted(per_control):
        rs = per_control[c]
        files = sorted({r["file"] for r in rs})
        L += [f"### {c} · {len(rs)} tests en {len(files)} ficheros", ""]
        for f in files:
            L.append(f"- `{f}`")
        L.append("")
    L += ["## Detalle", ""]
    for s, rs in by_service.items():
        L += [f"### {s}", "", "| Fichero | Test | Qué demuestra | Controles |", "|---|---|---|---|"]
        for r in rs:
            L.append(f"| {r['file'].replace(s + '/', '')} | `{r['test']}` | {r['proves'].replace('|', '/')} | {', '.join(r['controls']) or '-'} |")
        L.append("")
    return "\n".join(L)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = [r for s in SERVICES for r in collect(s)]
    OUT_MD.write_text(render(rows), encoding="utf-8")
    if args.json:
        OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    covered = sum(1 for r in rows if r["controls"])
    print(f"{OUT_MD.relative_to(ROOT)}: {len(rows)} tests, {covered} con control")


if __name__ == "__main__":
    main()
