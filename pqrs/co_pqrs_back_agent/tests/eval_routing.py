#!/usr/bin/env python3
"""Harness de evaluacion del ruteo con CASOS REALES de produccion.

Mide las capas que se pueden evaluar sin LLM (captacion de intencion determinista:
saludo y meta-peticion) y valida estaticamente que el catalogo tenga los negativos
(contraejemplos / no_usar) de los pares que fallaron en produccion.

Uso:
    cd co_pqrs_back_agent && PYTHONPATH=src uv run python tests/eval_routing.py

Dataset: tests/data/routing_eval_cases.json (extraido del consolidado de interacciones).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import unicodedata
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "eval_fixtures" / "routing_eval_cases.json"
CATALOG = ROOT.parent / "src" / "domain" / "workflow" / "general.yml"


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def load_cases() -> list[dict]:
    with DATA.open(encoding="utf-8") as handle:
        return json.load(handle)


def eval_intent_capture(cases: list[dict]) -> dict:
    """Saludo y meta-peticion: capas deterministas (red de seguridad del LLM)."""
    from application.chat.chat_service import (
        _is_bare_pqrs_request as bare,
        _is_pure_greeting as greeting,
    )

    report: dict[str, dict] = {}
    for categoria, fn in (("saludo", greeting), ("meta_peticion", bare)):
        subset = [c for c in cases if c["categoria"] == categoria]
        fails = [c["mensaje"] for c in subset if not fn(c["mensaje"])]
        report[categoria] = {
            "total": len(subset),
            "ok": len(subset) - len(fails),
            "fallos": fails,
        }
    return report


def eval_catalog_negatives() -> dict:
    """Valida que el catalogo excluya explicitamente los casos que fallaron."""
    text = _norm(CATALOG.read_text(encoding="utf-8"))
    # Frases/temas que NO deben caer en cada flujo (evidencia de produccion).
    expectativas = {
        "centrales: desembargo/no-embargo": r"desembargo|no presenta embargos|certificado de embargo",
        "centrales: levantamiento cautelares": r"medidas cautelares|levantamiento de medidas",
        "centrales: bloqueo de cuenta": r"bloqueo de (mi )?cuenta|congelamiento",
        "centrales: paz y salvo": r"paz y salvo",
        "txnr: suscripciones recurrentes": r"suscripcion|afiliacion|domiciliacion",
        "txnr: seguros no autorizados": r"seguro",
    }
    return {k: bool(re.search(p, text)) for k, p in expectativas.items()}


def eval_disambiguation_rules() -> dict:
    """Valida que el prompt instruya a PREGUNTAR en los pares ambiguos reales."""
    prompt = _norm((CATALOG.parent / "routing_prompt.yml").read_text(encoding="utf-8"))
    return {
        "desambigua en vez de adivinar": "desambigua en vez de adivinar" in prompt,
        "fraude sin transaccion concreta": bool(re.search(r"sin una transaccion concreta", prompt)),
        "cobro unico vs recurrente": bool(re.search(r"cobro unico o si es un cobro que se le repite", prompt)),
        "embargo consulta vs gestion": bool(re.search(r"motivo y la entidad de su embargo", prompt)),
        "few-shots de casos reales": bool(re.search(r"levantamiento de medidas cautelares", prompt)),
    }


def main() -> int:
    cases = load_cases()
    print("=" * 68)
    print(f"EVALUACION DE RUTEO — {len(cases)} casos reales de produccion")
    print("=" * 68)

    intent = eval_intent_capture(cases)
    total_ok = total = 0
    print("\n## 1) Captacion de intencion (determinista)")
    for categoria, res in intent.items():
        pct = 100 * res["ok"] / res["total"] if res["total"] else 0
        print(f"  {categoria:15s} {res['ok']:3d}/{res['total']:3d}  ({pct:5.1f}%)")
        for msg in res["fallos"][:8]:
            print(f"      FALLA: {msg[:78]}")
        if len(res["fallos"]) > 8:
            print(f"      ... y {len(res['fallos']) - 8} mas")
        total_ok += res["ok"]
        total += res["total"]

    print("\n## 2) Negativos en el catalogo (lo que NO debe entrar a cada flujo)")
    cat = eval_catalog_negatives()
    for nombre, presente in cat.items():
        print(f"  {'OK  ' if presente else 'FALTA'}  {nombre}")

    print("\n## 3) Desambiguacion (preguntar en vez de adivinar)")
    dis = eval_disambiguation_rules()
    for nombre, presente in dis.items():
        print(f"  {'OK  ' if presente else 'FALTA'}  {nombre}")

    pct = 100 * total_ok / total if total else 0
    print("\n" + "=" * 68)
    print(f"RESUMEN captacion de intencion: {total_ok}/{total} ({pct:.1f}%)")
    print(f"RESUMEN negativos catalogo:     {sum(cat.values())}/{len(cat)}")
    print(f"RESUMEN desambiguacion:         {sum(dis.values())}/{len(dis)}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
