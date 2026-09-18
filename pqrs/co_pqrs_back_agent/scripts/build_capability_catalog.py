#!/usr/bin/env python3
"""Catálogo de capacidades del agente, generado desde el YAML y el código.

Control KYNS IT 4 (autonomía e integridad financiera): el modelo probabilístico
no decide ni ejecuta acciones con impacto financiero. Este script hace explícito
lo que el diseño ya cumple:

* **Rutas**: los workflows a los que el LLM puede enrutar (``general.yml``).
* **Acciones**: la *allowlist* de todo ``action:`` declarado en los YAML, con su
  clase de efecto, dónde se resuelve y qué servicio toca. Una acción que no esté
  en ``ACTION_CLASSES`` hace fallar el test de contrato: no hay acción sin
  clasificar.
* **Puertas obligatorias**: para cada acción con efecto (escribir la ficha del
  caso, bloquear una tarjeta) se calculan TODOS los caminos del YAML desde el
  inicio del flujo hasta ella y los pasos por los que pasan todos. Así se
  demuestra, sin correr nada, que no hay atajo hacia el abono ni al bloqueo.
* **Parámetros**: los límites configurables que leen los gates (``_trx_env``)
  y los topes diarios.

Salida: ``docs/CATALOGO_CAPACIDADES.md`` y ``docs/catalogo_capacidades.json``.
El test ``tests/test_domain/test_workflow/test_catalogo_capacidades.py`` falla si
el catálogo generado no coincide con el que está en git (regenerar con
``uv run python scripts/build_capability_catalog.py``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

AGENT = Path(__file__).resolve().parents[1]
WF = AGENT / "src" / "domain" / "workflow"
CHAT_SERVICE = AGENT / "src" / "application" / "chat" / "chat_service.py"
ENV_EXAMPLE = AGENT / ".env.example"
OUT_MD = AGENT.parent / "docs" / "CATALOGO_CAPACIDADES.md"
OUT_JSON = AGENT.parent / "docs" / "catalogo_capacidades.json"

CLASS_LABELS = {
    "lectura": "Lectura de datos. Sin efecto sobre el cliente ni sus productos.",
    "presentacion": "Construye el mensaje que se muestra. Sin efecto.",
    "validacion": "Regla determinista que decide el siguiente paso. Sin efecto.",
    "derivacion": "Cambia de flujo. Sin efecto.",
    "escritura_caso": "Escribe la ficha del caso en OpenSearch. No mueve dinero: el abono lo ejecuta el RPA de Tantia fuera del agente.",
    "accion_producto": "Acción sobre un producto del cliente (POST al ASO vía back_trx). Exige autorización del cliente en la App.",
}
EFFECT_CLASSES = ("escritura_caso", "accion_producto")

WA = "workflow_actions.py (if-chain)"
REG = "actions/doble_cobro.py (registro)"
HOOK = "workflows/doble_cobro_hook.py (prefetch por paso)"
CS = "chat_service._prefetch_trx_data_if_needed (gate por paso)"

# ALLOWLIST. accion -> (clase, donde se resuelve, servicio que toca, nota)
ACTION_CLASSES: dict[str, tuple[str, str, str, str]] = {
    # centrales de riesgo / consultas
    "consultar_productos_cliente": ("lectura", WA, "back_data", "productos del cliente para el selector"),
    "consultar_productos_consulta_sin_permiso": ("lectura", WA, "back_data", ""),
    "consultar_centrales_producto_seleccionado": ("lectura", WA, "back_data", ""),
    "consultar_todos_productos_centrales": ("lectura", WA, "back_data", ""),
    "consultar_todos_productos_centrales_sin_notificacion": ("lectura", WA, "back_data", ""),
    "consultar_notificacion_producto_seleccionado": ("lectura", WA, "back_data", ""),
    "build_satisfaction_check_message": ("presentacion", WA, "-", ""),
    "build_satisfaction_si_message": ("presentacion", WA, "-", ""),
    "build_satisfaction_no_message": ("presentacion", WA, "-", ""),
    "goto_centrales_de_riesgo": ("derivacion", WA, "-", ""),
    "goto_extractos_bancarios": ("derivacion", WA, "-", ""),
    # transaccion no reconocida
    "consultar_recurrencia_salesforce": ("lectura", CS, "back_trx /validar-recurrencia", "gate 2.4.0.1: recurrencia Salesforce y del bot"),
    "verificar_productos_trx": ("lectura", CS, "back_trx /productos-activos", "gate 2.4.0.1.4"),
    "mostrar_productos_activos_trx": ("lectura", WA, "-", "selector dinámico con lo ya leído"),
    "consultar_movimientos_trx": ("lectura", CS, "back_trx /movimientos-aso (ASO financial-overview + transactions)", "gate 2.4.0.1.8, vigencia por franquicia"),
    "mostrar_movimientos_trx": ("presentacion", WA, "-", ""),
    "consultar_detalle_trx": ("lectura", CS, "back_trx /detalle (ASO operations)", "gate 2.4.0.1.10"),
    "confirmar_movimiento_trx": ("presentacion", WA, "-", "el cliente confirma que NO reconoce ese movimiento"),
    "validar_pendiente_trx": ("validacion", CS, "-", "gate 2.4.0.1.12: compra con TDC pendiente"),
    "bloqueo_temporal_trx": ("accion_producto", CS, "back_trx /bloqueo (ASO)", "gate 2.4.0.1.16.2; antes 2.4.0.1.16.1 pide autorización en la App; candado durable contra reejecución"),
    "bloqueo_permanente_trx": ("accion_producto", CS, "back_trx /bloqueo (ASO)", "gate 2.4.0.1.17.2; antes 2.4.0.1.17.1 pide autorización en la App; candado durable contra reejecución"),
    "mostrar_bloqueo_temporal_trx": ("presentacion", WA, "-", ""),
    "mostrar_bloqueo_definitivo_trx": ("presentacion", WA, "-", ""),
    "validar_investigacion_trx": ("validacion", CS, "-", "gate 2.4.0.1.19: presencial / reversada / procede"),
    "mostrar_trx_no_reconocida": ("presentacion", WA, "-", ""),
    "mostrar_trx_reversada": ("presentacion", WA, "-", ""),
    "registrar_devolucion_trx": ("escritura_caso", WA + " + " + CS, "OpenSearch trx-no-reconocida-cases", "hito `devolucion` y fila para el CSV de Tantia; idempotente por huella statementId|movementId"),
    "cierre_bucle_trx": ("validacion", CS, "-", "gate 2.4.0.1.20.0: otra transacción o fin"),
    # doble cobro
    "mostrar_productos_activos_dc": ("lectura", REG, "back_doble_cobro /productos-activos", ""),
    "validar_vigencia_doble_cobro": ("validacion", HOOK, "back_doble_cobro /validar-vigencia", "7 días hábiles de conciliación"),
    "validar_recurrencia_doble_cobro": ("validacion", HOOK, "OpenSearch trx-no-reconocida-cases", "reportes previos del cliente"),
    "mostrar_grupos_doble_cobro": ("lectura", HOOK, "back_doble_cobro /grupos-duplicados (ASO)", "paginado, selección múltiple"),
    "registrar_caso_doble_cobro": ("escritura_caso", HOOK, "OpenSearch trx-no-reconocida-cases", "solo grupos con 2+ cargos iguales; reemplaza el reporte previo equivalente"),
    "consultar_estado_doble_cobro": ("lectura", HOOK, "OpenSearch trx-no-reconocida-cases", ""),
}

# Puertas por las que TODO camino del YAML tiene que pasar antes de la acción.
FINANCIAL_GATES: dict[str, dict[str, Any]] = {
    "registrar_devolucion_trx": {
        "flow": "trx_no_reconocida",
        "gates": {
            "2.4.0.1.3": "el cliente confirma datos de contacto y el tope de 3 transacciones de $35.000 a $500.000",
            "2.4.0.1.6": "rango de valor: fuera de $35.000-$500.000 va al formulario",
            "2.4.0.1.11": "el cliente confirma que NO reconoce el movimiento",
            "2.4.0.1.12": "regla: compra con TDC pendiente no procede",
            "2.4.0.1.13": "el cliente pide investigar",
            "2.4.0.1.19": "regla: presencial / reversada / procede",
        },
    },
    "bloqueo_temporal_trx": {
        "flow": "trx_no_reconocida",
        "gates": {
            "2.4.0.1.11": "el cliente confirma que NO reconoce el movimiento",
            "2.4.0.1.15": "el cliente elige el tipo de bloqueo",
            "2.4.0.1.16": "el cliente confirma apagar la tarjeta",
            "2.4.0.1.16.1": "autorización del cliente en la App (subida de nivel)",
        },
    },
    "bloqueo_permanente_trx": {
        "flow": "trx_no_reconocida",
        "gates": {
            "2.4.0.1.11": "el cliente confirma que NO reconoce el movimiento",
            "2.4.0.1.15": "el cliente elige el tipo de bloqueo",
            "2.4.0.1.17": "el cliente confirma el bloqueo definitivo",
            "2.4.0.1.17.1": "autorización del cliente en la App (subida de nivel)",
        },
    },
    "registrar_caso_doble_cobro": {
        "flow": "doble_cobro",
        "gates": {
            "3.4.0.3": "regla: vigencia de la fecha (conciliación de 7 días hábiles)",
            "3.4.0.5": "regla: reportes previos equivalentes",
            "3.4.0.6": "el cliente selecciona los cobros y pulsa reportar",
        },
    },
}

# Pasos con efecto a los que el codigo NUNCA puede saltar directamente.
NO_DIRECT_JUMP_STEPS = ("2.4.0.1.16.2", "2.4.0.1.17.2", "2.4.0.1.20", "3.4.0.7")


# --------------------------------------------------------------------------- lectura

def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def routes() -> list[dict[str, str]]:
    catalog = load_yaml(WF / "general.yml")["welcome"]["groups"]
    out = []
    for group in catalog:
        for option in group.get("options") or []:
            out.append({
                "group": group["key"], "key": option["key"], "workflow": option.get("workflow", ""),
                "limit_category": option.get("limit_category") or group.get("limit_category") or "",
                "label": option.get("label", ""),
            })
    return out


def flow_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(WF.rglob("*.yml")):
        if path.name in ("general.yml", "general_messages.yml", "routing_prompt.yml", "shared_steps.yml"):
            continue
        files[path.stem] = path
    return files


def flow_steps(path: Path) -> tuple[str, dict[str, dict]]:
    data = load_yaml(path)
    return str(data.get("start_step", "")), dict(data.get("steps") or {})


def yaml_actions() -> dict[str, list[str]]:
    """accion -> [flujo:paso, ...] para todo action: declarado en los YAML."""

    found: dict[str, list[str]] = {}
    for flow, path in flow_files().items():
        _, steps = flow_steps(path)
        for step_id, step in steps.items():
            action = str((step or {}).get("action") or "").strip()
            if action:
                found.setdefault(action, []).append(f"{flow}:{step_id}")
    shared = load_yaml(WF / "shared_steps.yml") or {}
    for step_id, step in shared.items():
        action = str((step or {}).get("action") or "").strip()
        if action:
            found.setdefault(action, []).append(f"shared:{step_id}")
    return found


# --------------------------------------------------------------------------- caminos

def edges(steps: dict[str, dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {s: set() for s in steps}
    for step_id, step in steps.items():
        step = step or {}
        for option in step.get("options") or []:
            nxt = str(option.get("next_step") or "")
            if nxt in steps:
                out[step_id].add(nxt)
        nxt = str(step.get("next_step") or "")
        if nxt in steps:
            out[step_id].add(nxt)
    return out


def all_paths(graph: dict[str, set[str]], start: str, target: str, limit: int = 20000) -> list[list[str]]:
    paths: list[list[str]] = []
    stack = [(start, [start])]
    while stack and len(paths) < limit:
        node, path = stack.pop()
        if node == target:
            paths.append(path)
            continue
        for nxt in sorted(graph.get(node, ())):
            if nxt not in path:
                stack.append((nxt, path + [nxt]))
    return paths


def gate_analysis() -> dict[str, dict[str, Any]]:
    files = flow_files()
    out: dict[str, dict[str, Any]] = {}
    for action, spec in FINANCIAL_GATES.items():
        start, steps = flow_steps(files[spec["flow"]])
        targets = [s for s, st in steps.items() if str((st or {}).get("action") or "") == action]
        graph = edges(steps)
        paths: list[list[str]] = []
        for target in targets:
            paths.extend(all_paths(graph, start, target))
        mandatory = set.intersection(*(set(p[:-1]) for p in paths)) if paths else set()
        expected = set(spec["gates"])
        out[action] = {
            "flow": spec["flow"], "steps": targets, "paths": len(paths),
            "mandatory": sorted(mandatory), "expected_gates": sorted(expected),
            "missing_gates": sorted(expected - mandatory),
            "shortest": min((len(p) for p in paths), default=0),
        }
    return out


def direct_jumps() -> dict[str, list[str]]:
    """Asignaciones current_step = "<paso con efecto>" en el codigo (deben ser cero)."""

    out: dict[str, list[str]] = {}
    for path in (AGENT / "src" / "application").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for step in NO_DIRECT_JUMP_STEPS:
            if re.search(rf'current_step\s*=\s*"{re.escape(step)}"', text):
                out.setdefault(step, []).append(str(path.relative_to(AGENT)))
    return out


# --------------------------------------------------------------------------- parametros

def trx_parameters() -> list[tuple[str, str]]:
    text = CHAT_SERVICE.read_text(encoding="utf-8")
    seen: dict[str, str] = {}
    for name, default in re.findall(r'_trx_env\(\s*"([A-Z0-9_]+)"\s*,\s*"([^"]*)"\s*\)', text):
        seen.setdefault(name, default)
    return sorted(seen.items())


def daily_limits() -> list[tuple[str, str]]:
    out = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith(("MAX_DAILY_", "MAX_TRX_", "TRX_FLOW_ENABLED", "LLM_CLOSURE_ENABLED")):
            key, _, value = line.partition("=")
            out.append((key.strip(), value.strip()))
    return out


# --------------------------------------------------------------------------- salida

def build() -> dict[str, Any]:
    declared = yaml_actions()
    actions = []
    for action in sorted(set(declared) | set(ACTION_CLASSES)):
        cls, where, service, note = ACTION_CLASSES.get(action, ("SIN_CLASIFICAR", "?", "?", ""))
        actions.append({
            "action": action, "class": cls, "where": where, "service": service, "note": note,
            "declared_in": declared.get(action, []),
        })
    return {
        "routes": routes(),
        "actions": actions,
        "classes": CLASS_LABELS,
        "gates": gate_analysis(),
        "direct_jumps": direct_jumps(),
        "trx_parameters": trx_parameters(),
        "daily_limits": daily_limits(),
    }


def render(cat: dict[str, Any]) -> str:
    lines: list[str] = []
    w = lines.append
    w("# Catálogo de capacidades del agente PQRS")
    w("")
    w("> Generado por `co_pqrs_back_agent/scripts/build_capability_catalog.py` a partir de")
    w("> `general.yml`, los YAML de cada flujo y `chat_service.py`. No editar a mano: el test")
    w("> `test_catalogo_capacidades.py` falla si este fichero no coincide con lo generado.")
    w("")
    w("Evidencia del control **KYNS IT 4** (restricción de autonomía): el LLM solo elige la ruta,")
    w("valida texto libre y clasifica opciones. Toda acción con efecto está en la *allowlist* de")
    w("abajo, la ejecuta código determinista y solo se alcanza tras las puertas que se listan.")
    w("")
    w("## 1. Qué decide el modelo y qué no")
    w("")
    w("| Punto | Lo decide el LLM | Lo decide código |")
    w("|---|---|---|")
    w("| Ruteo inicial | `is_match`, `workflow`, `confidence` | umbral de confianza, confirmación en `low`, aclaración determinista, formulario como último recurso |")
    w("| Texto libre en un paso (fecha, monto) | extrae y normaliza | la fecha se reparsea con `_trx_parse_date`; futura o ilegible se repregunta |")
    w("| Opción de un paso `choice` | clasifica el texto contra las opciones | el `next_step` lo fija el YAML |")
    w("| Cierre de guía rápida | redacta solo si `LLM_CLOSURE_ENABLED=true` (apagado por defecto) | el texto aprobado del YAML |")
    w("| Cualquier acción con efecto | **nunca** | gates de `chat_service` / hooks, con fail-closed |")
    w("")
    w("## 2. Rutas a las que puede enrutar")
    w("")
    w("| Grupo | Opción | Workflow | Categoría de tope diario |")
    w("|---|---|---|---|")
    for r in cat["routes"]:
        w(f"| {r['group']} | {r['key']} | `{r['workflow']}` | {r['limit_category'] or '-'} |")
    w("")
    w("## 3. Allowlist de acciones")
    w("")
    w("Clases de efecto:")
    w("")
    for cls, label in cat["classes"].items():
        w(f"- **{cls}**: {label}")
    w("")
    w("| Acción | Clase | Dónde se resuelve | Servicio | Declarada en | Nota |")
    w("|---|---|---|---|---|---|")
    for a in cat["actions"]:
        w(f"| `{a['action']}` | {a['class']} | {a['where']} | {a['service']} | {', '.join(a['declared_in']) or '-'} | {a['note']} |")
    w("")
    n_effect = sum(1 for a in cat["actions"] if a["class"] in EFFECT_CLASSES)
    w(f"{len(cat['actions'])} acciones, {n_effect} con efecto (`escritura_caso`, `accion_producto`). Ninguna sin clasificar."
      if not any(a["class"] == "SIN_CLASIFICAR" for a in cat["actions"]) else "**HAY ACCIONES SIN CLASIFICAR.**")
    w("")
    w("## 4. Puertas obligatorias antes de cada acción con efecto")
    w("")
    w("Se calculan todos los caminos simples del YAML desde el inicio del flujo hasta el paso de la")
    w("acción. *Pasos por los que pasan todos* es la intersección; las puertas esperadas deben estar")
    w("dentro. El código añade salidas (fail-closed, formulario), nunca atajos: no existe ninguna")
    w("asignación directa de `current_step` a un paso con efecto.")
    w("")
    for action, g in cat["gates"].items():
        w(f"### `{action}` ({g['flow']}, paso {', '.join(g['steps'])})")
        w("")
        w(f"- Caminos desde el inicio: {g['paths']} (el más corto, {g['shortest']} pasos).")
        w(f"- Pasos por los que pasan todos: {', '.join(g['mandatory']) or '(ninguno)'}")
        w("- Puertas esperadas:")
        for step, why in FINANCIAL_GATES[action]["gates"].items():
            mark = "✓" if step not in g["missing_gates"] else "✗ FALTA"
            w(f"  - {mark} `{step}`: {why}")
        w("")
    dj = cat["direct_jumps"]
    w("Saltos directos del código a pasos con efecto: " + ("**ninguno**." if not dj else f"**{dj}**"))
    w("")
    w("## 5. Parámetros que leen los gates")
    w("")
    w("| Variable | Valor por defecto en código |")
    w("|---|---|")
    for name, default in cat["trx_parameters"]:
        w(f"| `{name}` | `{default}` |")
    w("")
    w("Topes y portones en `.env.example` del agente:")
    w("")
    w("| Variable | Valor de ejemplo |")
    w("|---|---|")
    for name, value in cat["daily_limits"]:
        w(f"| `{name}` | `{value}` |")
    w("")
    w("Los topes del flujo TXNR que vienen del propio YAML: hasta 3 transacciones por trámite y")
    w("valores entre $35.000 y $500.000 (paso 2.4.0.1.6); fuera de eso, formulario PQR.")
    w("")
    return "\n".join(lines)


def main() -> None:
    cat = build()
    OUT_MD.write_text(render(cat), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missing = [a["action"] for a in cat["actions"] if a["class"] == "SIN_CLASIFICAR"]
    print(f"{OUT_MD.relative_to(AGENT.parent)} y .json regenerados; acciones={len(cat['actions'])} sin clasificar={missing}")
    for action, g in cat["gates"].items():
        print(f"  {action}: caminos={g['paths']} faltan={g['missing_gates']}")
    print(f"  saltos directos: {cat['direct_jumps'] or 'ninguno'}")


if __name__ == "__main__":
    main()
