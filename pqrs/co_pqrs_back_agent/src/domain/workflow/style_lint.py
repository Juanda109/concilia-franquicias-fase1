"""Lint de estilo del copy del bot: tuteo consistente y promesas controladas.

Escanea SOLO las superficies que ve el cliente (``question``, ``label`` y
``message`` de los YAML de workflows). Los campos internos del catalogo
(``description``, ``preconditions``, ``examples``...) hablan del cliente en
tercera persona y "su cuenta" es correcto ahi: quedan fuera a proposito.

Dos familias de reglas:

* ``usted_*`` / ``posesivo_usted``: el bot tutea. Cualquier forma de usted
  (pronombre, imperativo en -e, clitico "-nos/-me" de cortesia, posesivo
  "su/sus" sobre cosas del cliente) es una inconsistencia de tono.
* ``promesa_abono``: las frases que prometen dinero solo pueden vivir en
  pasos terminales de confirmacion (``*.aprobado``, ``*.pendiente``,
  ``*.recurrente``). Una promesa en cualquier otro paso es un riesgo de
  negocio, no de estilo.

Sin I/O de red y sin LLM: apto para pytest y para el job de benchmark.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

_WORKFLOW_DIR = Path(__file__).resolve().parent

# Formas de usted que no deberian aparecer en el copy. Los imperativos se
# listan verbo a verbo (la conjugacion en -e choca con subjuntivos legitimos,
# asi que solo entran verbos que el bot usa como instruccion directa).
_USTED_PRONOUN = re.compile(r"\busted(?:es)?\b", re.IGNORECASE)
_USTED_IMPERATIVES = re.compile(
    r"\b(?:seleccione|ingrese|escriba|consulte|verifique|complete|revise|"
    r"indique|espere|intente|comun[ií]quese|dir[ií]jase|ac[eé]rquese|"
    r"cu[eé]nten?(?:os|me)|d[ií]gan?(?:os|me)|ind[ií]quenos)\b",
    re.IGNORECASE,
)
_USTED_POSSESSIVE = re.compile(
    r"\bsus?\s+(?:cuenta|tarjeta|producto|movimiento|solicitud|dinero|"
    r"extracto|clave|caso|reporte|reclamo|compra)s?\b",
    re.IGNORECASE,
)

# Promesas de dinero: solo en terminales de confirmacion.
_PROMISES = re.compile(
    r"(?:realizaremos el abono|realizamos el abono|abono a tu cuenta|"
    r"ver[aá]s reflejado el dinero|te devolveremos el dinero|"
    r"abonaremos)",
    re.IGNORECASE,
)
_PROMISE_ALLOWED_SUFFIXES = (".aprobado", ".pendiente", ".recurrente")

# Campos de un paso cuyo texto ve el cliente.
_USER_FACING_STEP_FIELDS = ("question",)


@dataclass(frozen=True)
class Violation:
    file: str
    step_id: str
    field: str
    rule: str
    excerpt: str

    def __str__(self) -> str:  # pragma: no cover - solo para reportes
        return f"{self.file} [{self.step_id}] {self.field}: {self.rule} -> {self.excerpt!r}"


def _is_subjunctive(text: str, match_start: int) -> bool:
    """"que un equipo revise tu caso" es subjuntivo, no imperativo de usted.

    Un "que" en la misma frase (desde el ultimo punto, dos puntos o salto de
    linea) delante del verbo marca subjuntivo con otro sujeto y se descarta.
    """

    clause = re.split(r"[.:\n]", text[:match_start])[-1]
    return re.search(r"\bque\b", clause, re.IGNORECASE) is not None


def check_text(text: str) -> list[tuple[str, str]]:
    """Reglas de tuteo sobre un texto. Devuelve (regla, extracto)."""

    findings: list[tuple[str, str]] = []
    for rule, pattern in (
        ("usted_pronombre", _USTED_PRONOUN),
        ("usted_imperativo", _USTED_IMPERATIVES),
        ("posesivo_usted", _USTED_POSSESSIVE),
    ):
        for match in pattern.finditer(text or ""):
            if rule == "usted_imperativo" and _is_subjunctive(text, match.start()):
                continue
            start = max(match.start() - 25, 0)
            findings.append((rule, text[start : match.end() + 25].strip()))
    return findings


def check_promise(step_id: str, text: str) -> list[tuple[str, str]]:
    """Una promesa de abono fuera de un terminal de confirmacion es hallazgo."""

    if step_id.endswith(_PROMISE_ALLOWED_SUFFIXES):
        return []
    return [
        ("promesa_abono", match.group(0))
        for match in _PROMISES.finditer(text or "")
    ]


def _iter_step_texts(
    definition: dict[str, Any],
) -> Iterator[tuple[str, str, str]]:
    """(step_id, campo, texto) de cada superficie visible de un flujo."""

    for step_id, step in (definition.get("steps") or {}).items():
        if not isinstance(step, dict):
            continue
        for field in _USER_FACING_STEP_FIELDS:
            value = step.get(field)
            if isinstance(value, str):
                yield str(step_id), field, value
        for option in step.get("options") or []:
            if isinstance(option, dict) and isinstance(option.get("label"), str):
                yield str(step_id), "options.label", option["label"]


def _iter_catalog_messages(definition: Any) -> Iterator[tuple[str, str, str]]:
    """Los ``message:`` del catalogo (general.yml) los ve el cliente."""

    if isinstance(definition, dict):
        for key, value in definition.items():
            if key == "message" and isinstance(value, str):
                yield "(catalogo)", "message", value
            else:
                yield from _iter_catalog_messages(value)
    elif isinstance(definition, list):
        for item in definition:
            yield from _iter_catalog_messages(item)


def iter_workflow_files(workflow_dir: Path | None = None) -> Iterator[Path]:
    base = workflow_dir or _WORKFLOW_DIR
    for path in sorted(base.rglob("*.yml")):
        if path.name != "routing_prompt.yml":  # persona del router, no copy
            yield path


def lint_workflows(workflow_dir: Path | None = None) -> list[Violation]:
    """Corre todas las reglas sobre todos los flujos. Vacio = todo en orden."""

    base = workflow_dir or _WORKFLOW_DIR
    violations: list[Violation] = []

    for path in iter_workflow_files(base):
        try:
            definition = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            violations.append(
                Violation(str(path.relative_to(base)), "-", "-", "yaml_ilegible", "")
            )
            continue

        rel = str(path.relative_to(base))
        surfaces: list[tuple[str, str, str]] = []
        if isinstance(definition, dict) and "steps" in definition:
            surfaces.extend(_iter_step_texts(definition))
        if path.name == "general.yml":
            surfaces.extend(_iter_catalog_messages(definition))

        for step_id, field, text in surfaces:
            for rule, excerpt in check_text(text):
                violations.append(Violation(rel, step_id, field, rule, excerpt))
            for rule, excerpt in check_promise(step_id, text):
                violations.append(Violation(rel, step_id, field, rule, excerpt))

    return violations
