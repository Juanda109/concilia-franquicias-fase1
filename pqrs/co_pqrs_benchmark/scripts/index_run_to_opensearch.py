#!/usr/bin/env python3
"""Indexa una corrida del benchmark (NDJSON) en OpenSearch como eventos.

Reproduce en LOCAL lo que en OKD hace el camino RabbitMQ -> Logstash: convierte
cada linea del NDJSON en un ``benchmark.case`` y el resumen en un
``benchmark.run`` con las MISMAS funciones del publicador
(``src/benchmark/events.py``), aplica las plantillas de indice del IaC y hace
el bulk al indice mensual ``pqr-benchmark-runs-YYYY.MM``. Asi el tablero de
OpenSearch Dashboards se puede construir y ver antes de desplegar nada en dev.

Lo unico que Logstash haria y aqui se imita a mano es copiar ``timestamp`` a
``@timestamp``.

Uso (desde co_pqrs_benchmark/, con el OpenSearch local de
co_pqrs_back_opensearch/os-local.yml arriba):

    python scripts/index_run_to_opensearch.py \\
        datasets/corridas/2026-09-07_local_llm_real/doble_cobro_llm_real.ndjson \\
        --run-name techo-llm-real --catalog-version 9b7dda0 \\
        --summary datasets/corridas/2026-09-07_local_llm_real/doble_cobro_llm_real_summary.txt

    python scripts/index_run_to_opensearch.py --apply-templates-only

Variables: OS_URL (https://localhost:9200), OS_USER (admin), OS_PASS (admin),
OS_VERIFY_SSL (false). El dataset se usa para recuperar la ``nota`` de cada
caso; por defecto datasets/doble_cobro_routing.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import urllib3

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.benchmark.events import (  # noqa: E402
    CASE_ROUTING_KEY,
    RUN_ROUTING_KEY,
    RunContext,
    build_case_event,
    build_run_event,
    flow_from_source,
)
from src.benchmark.job import _compute_metrics, _evaluate  # noqa: E402

REPO_ROOT = ROOT_DIR.parent
TEMPLATES_CONFIGMAP = (
    REPO_ROOT / "IaC/elk/opensearch-analytics/05-configmap-index-templates.yaml"
)
# Nombres de las plantillas tal como las crea el Job de bootstrap del IaC.
TEMPLATE_KEYS = {
    "pqr-benchmark-runs": "pqr-benchmark-runs-template.json",
    "pqr-benchmark-conversations": "pqr-benchmark-conversations-template.json",
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# OpenSearch
# ---------------------------------------------------------------------------


class OpenSearchLocal:
    def __init__(self) -> None:
        self.url = os.getenv("OS_URL", "https://localhost:9200").rstrip("/")
        self.auth = (os.getenv("OS_USER", "admin"), os.getenv("OS_PASS", "admin"))
        self.verify = os.getenv("OS_VERIFY_SSL", "false").lower() in ("1", "true", "yes")

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = requests.request(
            method,
            f"{self.url}{path}",
            auth=self.auth,
            verify=self.verify,
            timeout=30,
            **kwargs,
        )
        if response.status_code >= 300:
            raise SystemExit(
                f"OpenSearch {method} {path} -> HTTP {response.status_code}: "
                f"{response.text[:400]}"
            )
        return response

    def apply_templates(self) -> None:
        """Las mismas plantillas que el Job de bootstrap, leidas del ConfigMap."""

        import yaml

        configmap = yaml.safe_load(TEMPLATES_CONFIGMAP.read_text())
        data = configmap["data"]
        for name, key in TEMPLATE_KEYS.items():
            body = json.loads(data[key])
            self.request("PUT", f"/_index_template/{name}", json=body)
            print(f"plantilla {name}: OK ({body['index_patterns']})")

    def bulk(self, index: str, docs: list[dict[str, Any]]) -> int:
        lines: list[str] = []
        for doc in docs:
            lines.append(json.dumps({"index": {"_index": index}}))
            lines.append(json.dumps(doc, ensure_ascii=False, default=str))
        payload = "\n".join(lines) + "\n"
        response = self.request(
            "POST",
            "/_bulk?refresh=true",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
        )
        result = response.json()
        if result.get("errors"):
            failed = [
                item["index"].get("error")
                for item in result["items"]
                if item["index"].get("error")
            ]
            raise SystemExit(f"bulk con errores ({len(failed)}): {failed[:3]}")
        return len(docs)


# ---------------------------------------------------------------------------
# NDJSON -> eventos
# ---------------------------------------------------------------------------


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _duration_from_summary(path: Path | None, fallback: float) -> float:
    if path is None or not path.exists():
        return fallback
    match = re.search(r"duracion_s\s*:\s*([\d.]+)", path.read_text())
    return float(match.group(1)) if match else fallback


def _load_notes(dataset: Path) -> dict[str, str]:
    """question -> nota, para rellenar el campo ``note`` como hace el job."""

    if not dataset.exists():
        return {}
    return {
        str(item.get("question", "")).strip(): str(item.get("nota", "") or "")
        for item in json.loads(dataset.read_text())
    }


def _empty_stats(total: int) -> dict[str, Any]:
    """Mismas claves que inicializa ``process_questions``."""

    return {
        "total": total,
        "ok": 0,
        "miss": 0,
        "miss_workflow": 0,
        "miss_outcome": 0,
        "unresolved": 0,
        "unresolved_max_turns": 0,
        "unresolved_needs_follow_up": 0,
        "skipped": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_cached": 0,
        "models": set(),
        "routing_s": [],
        "user_s": [],
        "routing_s_sum": 0.0,
        "user_s_sum": 0.0,
        "turns": [],
    }


def events_from_ndjson(
    ndjson: Path,
    *,
    run: RunContext,
    notes: dict[str, str],
    duration_s: float,
    run_timestamp: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [json.loads(line) for line in ndjson.read_text().splitlines() if line.strip()]
    stats = _empty_stats(len(rows))
    docs: list[dict[str, Any]] = []

    for index, registry in enumerate(rows, 1):
        resolved = registry.get("resolution") == "resolved"
        hit, miss_kind = False, ""
        if resolved:
            hit, miss_kind, _ = _evaluate(
                registry.get("workflow_expect", ""),
                registry.get("outcome_expect", ""),
                registry,
            )
            if hit:
                stats["ok"] += 1
            else:
                stats["miss"] += 1
                stats[f"miss_{miss_kind}"] += 1
        else:
            stats["unresolved"] += 1
            if registry.get("resolution") == "max_turns":
                stats["unresolved_max_turns"] += 1
            elif registry.get("resolution") == "needs_follow_up":
                stats["unresolved_needs_follow_up"] += 1

        stats["tokens_in"] += int(registry.get("llm_token_input", 0) or 0)
        stats["tokens_out"] += int(registry.get("llm_token_output", 0) or 0)
        stats["tokens_cached"] += int(registry.get("llm_token_cached", 0) or 0)
        if registry.get("llm_model"):
            stats["models"].add(registry["llm_model"])
        routing_s = float(registry.get("routing_time_total_s", 0.0) or 0.0)
        user_s = float(registry.get("user_time_total_s", 0.0) or 0.0)
        stats["routing_s"].append(routing_s)
        stats["user_s"].append(user_s)
        stats["routing_s_sum"] += routing_s
        stats["user_s_sum"] += user_s
        stats["turns"].append(int(registry.get("turns", 0) or 0))

        event = build_case_event(
            registry,
            run=run,
            case_index=index,
            note=notes.get(str(registry.get("user_input", "")).strip(), ""),
            acierto=hit,
            fail_kind=miss_kind if (resolved and not hit) else None,
        )
        event["@timestamp"] = event["timestamp"]  # lo que haria Logstash
        docs.append(event)

    metrics = _compute_metrics(stats, duration_s)
    run_event = build_run_event(metrics, run=run, timestamp=run_timestamp)
    run_event["@timestamp"] = run_event["timestamp"]
    docs.append(run_event)
    return docs, metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ndjson", nargs="?", help="NDJSON de la corrida")
    parser.add_argument("--run-name", help="run_name del evento (default: nombre del NDJSON)")
    parser.add_argument("--source", default="benchmark", choices=("benchmark", "canario"))
    parser.add_argument("--catalog-version", default="unknown")
    parser.add_argument("--environment", default="local")
    parser.add_argument("--flow", help="flow del evento (default: doble_cobro_routing)")
    parser.add_argument("--summary", type=Path, help="resumen .txt para leer duracion_s")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT_DIR / "datasets/doble_cobro_routing.json",
        help="dataset con las notas de cada caso",
    )
    parser.add_argument("--apply-templates-only", action="store_true")
    parser.add_argument("--skip-templates", action="store_true")
    args = parser.parse_args()

    client = OpenSearchLocal()
    if not args.skip_templates:
        client.apply_templates()
    if args.apply_templates_only:
        return
    if not args.ndjson:
        parser.error("falta el NDJSON de la corrida")

    ndjson = Path(args.ndjson)
    rows = [json.loads(line) for line in ndjson.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit("NDJSON vacio")

    started = _parse_ts(rows[0]["timestamp"])
    finished = _parse_ts(rows[-1]["timestamp"])
    run_name = args.run_name or ndjson.stem
    flow = args.flow or flow_from_source(str(args.dataset))
    run = RunContext(
        source=args.source,
        run_name=run_name,
        run_id=f"{run_name}_{started.strftime('%Y%m%dT%H%M%SZ')}",
        catalog_version=args.catalog_version,
        environment=args.environment,
        flow=flow,
        started_at=started,
    )
    duration_s = _duration_from_summary(
        args.summary, round((finished - started).total_seconds(), 1)
    )

    docs, metrics = events_from_ndjson(
        ndjson,
        run=run,
        notes=_load_notes(args.dataset),
        duration_s=duration_s,
        run_timestamp=finished.isoformat(),
    )
    index = f"pqr-benchmark-runs-{finished.strftime('%Y.%m')}"
    count = client.bulk(index, docs)
    print(
        f"{index}: {count} docs ({count - 1} {CASE_ROUTING_KEY} + 1 {RUN_ROUTING_KEY}) "
        f"run_id={run.run_id} precision={metrics['precision_pct']}% "
        f"p95 ruteo={metrics['ruteo_s_caso_p95']}s e2e={metrics['e2e_s_caso_p95']}s"
    )


if __name__ == "__main__":
    main()
