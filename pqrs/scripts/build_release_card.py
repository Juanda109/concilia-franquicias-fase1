#!/usr/bin/env python3
"""Ficha de versión: qué se evaluó y qué se despliega, en un solo artefacto.

Controles KYNS IT 1.6 (trazabilidad productiva) e IT 2.2 (inventario de
configuración). Reúne, desde el repo y sin tocar el clúster:

* el commit y la rama;
* las imágenes que declara el IaC para cada servicio;
* el modelo, los embeddings, el guardrail y los portones del ConfigMap del agente;
* el último commit y la huella SHA-256 del catálogo de ruteo, los prompts, los
  mensajes, los flujos YAML y el guardrail (lo que el LLM "sabe" y lo que lo filtra);
* los datasets de evaluación con su tamaño y huella;
* los umbrales de las alertas y las cadencias del benchmark y el canario.

Uso:
    python scripts/build_release_card.py                      # imprime la ficha
    python scripts/build_release_card.py --out <carpeta>      # escribe ficha_version.json y FICHA_VERSION.md

`co_pqrs_benchmark/scripts/run_all_local.sh` la deja junto a los resultados de
cada corrida, de modo que `catalog_version` (el commit) apunta a una ficha.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "co_pqrs_back_agent"
WF = AGENT / "src" / "domain" / "workflow"
IAC = ROOT / "IaC"

KNOWLEDGE_FILES = {
    "catalogo_ruteo": WF / "general.yml",
    "prompt_ruteo": WF / "routing_prompt.yml",
    "mensajes_generales": WF / "general_messages.yml",
    "pasos_compartidos": WF / "shared_steps.yml",
    "flujo_trx_no_reconocida": WF / "trx_no_reconocida" / "trx_no_reconocida.yml",
    "flujo_doble_cobro": WF / "doble_cobro" / "doble_cobro.yml",
    "guardrail_input_screen": AGENT / "src" / "guardrail" / "input_screen.py",
    "guardrail_judge": AGENT / "src" / "guardrail" / "judge.py",
    "guardrail_scope": AGENT / "src" / "guardrail" / "scope.py",
}
DATASETS = ROOT / "co_pqrs_benchmark" / "datasets"
AGENT_CONFIGMAP = IAC / "backend" / "co_pqrs_back_agent" / "01-configmap.yaml"
ALERTING = IAC / "elk" / "opensearch-analytics" / "12-job-bootstrap-alerting.yaml"
CONFIG_KEYS = ("LLM_MODEL", "LLM_EMBEDDINGS", "GUARDRAIL_JUDGE_ENABLED", "TRX_FLOW_ENABLED",
               "LLM_CLOSURE_ENABLED", "MAX_DAILY_SESSIONS", "MAX_DAILY_CATEGORY_INTERACTIONS",
               "RABBITMQ_ENABLED", "LOCAL_CONTINGENCY_MODE")
ALERT_KEYS = ("CANARIO_PRECISION_THRESHOLD", "ALERT_LOOKBACK", "RUTA_CAIDA_LOOKBACK",
              "RUTA_CAIDA_MIN_CORRIDAS", "ALERT_RECIPIENTS")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else ""


def _last_commit(path: Path) -> str:
    return _git("log", "-1", "--format=%h %cs", "--", str(path.relative_to(ROOT)))


def images() -> list[dict[str, str]]:
    out = []
    for path in sorted(IAC.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^\s*image:\s*([^\s#]+)", text, flags=re.M):
            image = m.group(1)
            if "/pqr-genai/" not in image:
                continue
            name, _, tag = image.rpartition(":")
            out.append({"service": name.rsplit("/", 1)[-1], "tag": tag, "manifest": str(path.relative_to(ROOT))})
    seen, uniq = set(), []
    for row in out:
        key = (row["service"], row["tag"])
        if key not in seen:
            seen.add(key); uniq.append(row)
    return uniq


def _env_values(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    text = path.read_text(encoding="utf-8", errors="replace")
    for key in keys:
        m = re.search(rf"^\s*{key}\s*[=:]\s*\"?([^\"#\n]*)", text, flags=re.M)
        if m:
            values[key] = m.group(1).strip()
        else:
            m = re.search(rf"name:\s*{key}\s*\n\s*value:\s*\"?([^\"\n]*)", text)
            if m:
                values[key] = m.group(1).strip()
    return values


def datasets() -> list[dict[str, object]]:
    rows = []
    for path in sorted(DATASETS.glob("*.json")):
        try:
            n = len(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            n = 0
        rows.append({"dataset": path.name, "casos": n, "sha256": _sha(path), "ultimo_cambio": _last_commit(path)})
    return rows


def schedules() -> dict[str, str]:
    out = {}
    for name, path in (("benchmark", IAC / "backend/co_pqrs_benchmark/01-cronjob.yaml"),
                       ("canario", IAC / "backend/co_pqrs_benchmark/02-cronjob-canario.yaml")):
        if path.exists():
            # Sin comentarios: el manifiesto del canario explica en un comentario
            # como poner "suspend: false", y leerlo daba el canario por activo.
            text = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith("#"))
            m = re.search(r'schedule:\s*"([^"]+)"', text)
            s = re.search(r"suspend:\s*(true|false)", text)
            out[name] = (m.group(1) if m else "?") + (" (suspendido)" if s and s.group(1) == "true" else "")
    return out


def build() -> dict[str, object]:
    return {
        "generada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "rama": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "arbol_limpio": _git("status", "--porcelain", "--untracked-files=no", "--", ".", ":!docs/INFORME_TECNICO_IA.md", ":!docs/INFORME_TECNICO_IA.html") == "",
        "imagenes": images(),
        "configuracion_agente": _env_values(AGENT_CONFIGMAP, CONFIG_KEYS),
        "conocimiento_y_guardrails": {
            name: {"sha256": _sha(path), "ultimo_cambio": _last_commit(path)} for name, path in KNOWLEDGE_FILES.items()
        },
        "datasets": datasets(),
        "alertas": _env_values(ALERTING, ALERT_KEYS),
        "cadencias": schedules(),
    }


def render(card: dict[str, object]) -> str:
    L: list[str] = []
    w = L.append
    w(f"# Ficha de versión · {card['commit']} ({card['rama']})")
    w("")
    w(f"Generada {card['generada']} por `scripts/build_release_card.py`. "
      + ("Árbol limpio." if card["arbol_limpio"] else "**Árbol con cambios sin commit.**"))
    w("")
    w("## Imágenes declaradas en el IaC")
    w("")
    w("| Servicio | Tag | Manifiesto |")
    w("|---|---|---|")
    for row in card["imagenes"]:
        w(f"| {row['service']} | `{row['tag']}` | {row['manifest']} |")
    w("")
    w("## Configuración del agente (ConfigMap de dev)")
    w("")
    w("| Variable | Valor |")
    w("|---|---|")
    for k, v in card["configuracion_agente"].items():
        w(f"| `{k}` | `{v}` |")
    w("")
    w("## Conocimiento y guardrails (lo que el modelo sabe y lo que lo filtra)")
    w("")
    w("| Pieza | SHA-256 (16) | Último cambio |")
    w("|---|---|---|")
    for name, info in card["conocimiento_y_guardrails"].items():
        w(f"| {name} | `{info['sha256']}` | {info['ultimo_cambio']} |")
    w("")
    w("## Datasets de evaluación")
    w("")
    w("| Dataset | Casos | SHA-256 (16) | Último cambio |")
    w("|---|---|---|---|")
    for row in card["datasets"]:
        w(f"| {row['dataset']} | {row['casos']} | `{row['sha256']}` | {row['ultimo_cambio']} |")
    w("")
    w("## Alertas y cadencias")
    w("")
    for k, v in card["alertas"].items():
        w(f"- `{k}` = `{v}`")
    for k, v in card["cadencias"].items():
        w(f"- {k}: `{v}`")
    w("")
    return "\n".join(L)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ficha de versión del agente PQRS")
    parser.add_argument("--out", type=Path, help="carpeta donde dejar ficha_version.json y FICHA_VERSION.md")
    args = parser.parse_args()
    card = build()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "ficha_version.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.out / "FICHA_VERSION.md").write_text(render(card), encoding="utf-8")
        print(f"ficha {card['commit']} escrita en {args.out}")
    else:
        print(render(card))


if __name__ == "__main__":
    main()
