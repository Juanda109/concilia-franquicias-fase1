# /// script
# requires-python = ">=3.11"
# dependencies = ["langfuse>=2.60,<3"]
# ///
"""Publica una corrida del benchmark en Langfuse: trazas + scores por caso.

Cada linea del NDJSON que escribe ``benchmark/job.py`` se convierte en una
traza (input = mensaje del cliente, output = respuesta final del bot) con una
generacion que carga modelo y tokens, y en scores numericos: ``acierto``
(replicando la evaluacion del job, incluida la normalizacion matched/other),
``routing_s`` y ``e2e_s``. Todas las trazas de la corrida comparten el tag
``run:<nombre>`` y la version del catalogo, asi dos corridas se comparan lado
a lado en la UI.

Uso (con el stack de langfuse/compose.yml arriba):

    uv run scripts/publish_to_langfuse.py <corrida.ndjson> \
        --run-name baseline-doble-cobro

Credenciales por variables de entorno (los valores por defecto son los del
compose local): LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from langfuse import Langfuse


def _catalog_version() -> str:
    """SHA corto del repo: liga la corrida a la version del catalogo/prompt."""

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconocida"


def _evaluate(record: dict) -> float | None:
    """Replica ``_evaluate`` del job. ``None`` = caso sin resolver (no puntua)."""

    if record.get("resolution") != "resolved":
        return None

    expected_wf = record.get("workflow_expect", "")
    expected_outcome = record.get("outcome_expect", "")
    result = record.get("workflow_result", "")
    outcome = record.get("routing_outcome", "")

    if expected_outcome == "matched" and outcome == "other" and result:
        outcome = "matched"

    if result != expected_wf:
        return 0.0
    if expected_outcome and outcome != expected_outcome:
        return 0.0
    return 1.0


def publish(path: Path, run_name: str, host: str, public_key: str, secret_key: str) -> int:
    langfuse = Langfuse(host=host, public_key=public_key, secret_key=secret_key)
    version = _catalog_version()
    published = 0
    hits = 0
    scored = 0

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)

            acierto = _evaluate(record)
            trace = langfuse.trace(
                name=f"benchmark:{record.get('workflow_expect') or 'sin_workflow'}",
                input=record.get("user_input", ""),
                output=record.get("user_output", ""),
                session_id=record.get("conversation_id", ""),
                tags=[f"run:{run_name}", f"catalogo:{version}"],
                metadata={
                    "workflow_expect": record.get("workflow_expect", ""),
                    "workflow_result": record.get("workflow_result", ""),
                    "routing_outcome": record.get("routing_outcome", ""),
                    "confidence": record.get("confidence", ""),
                    "resolution": record.get("resolution", ""),
                    "turns": record.get("turns", 0),
                    "outcome_path": record.get("outcome_path", []),
                },
            )
            trace.generation(
                name="routing",
                model=record.get("llm_model") or "desconocido",
                usage={
                    "input": record.get("llm_token_input", 0),
                    "output": record.get("llm_token_output", 0),
                    "unit": "TOKENS",
                },
                metadata={
                    "token_cache_hit_pct": record.get("llm_token_cache_hit_pct", 0),
                },
            )

            if acierto is not None:
                trace.score(name="acierto", value=acierto)
                scored += 1
                hits += int(acierto)
            trace.score(
                name="routing_s", value=float(record.get("routing_time_total_s", 0))
            )
            trace.score(name="e2e_s", value=float(record.get("user_time_total_s", 0)))
            published += 1

    langfuse.flush()

    precision = round(hits / scored * 100, 1) if scored else 0.0
    print(
        f"Publicadas {published} trazas en {host} "
        f"(run:{run_name}, catalogo:{version}) — "
        f"precision {hits}/{scored} = {precision}%"
    )
    return published


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ndjson", type=Path, help="Corrida NDJSON del benchmark")
    parser.add_argument(
        "--run-name",
        default=datetime.now(UTC).strftime("corrida-%Y%m%d-%H%M"),
        help="Nombre de la corrida (tag run:<nombre> en Langfuse)",
    )
    parser.add_argument(
        "--host", default=os.getenv("LANGFUSE_HOST", "http://localhost:3000")
    )
    args = parser.parse_args()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-doble-cobro-poc")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-doble-cobro-poc")

    if not args.ndjson.is_file():
        sys.exit(f"No existe el archivo: {args.ndjson}")

    publish(args.ndjson, args.run_name, args.host, public_key, secret_key)


if __name__ == "__main__":
    main()
