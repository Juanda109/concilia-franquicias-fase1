"""Job de benchmark: ejecuta el set de preguntas contra la API del agente.

Cada caso es una CONVERSACION, no un mensaje: se hace `POST /start` y luego
tantos `POST /chat` (con la cabecera `X-Benchmark-Mode`) como haga falta hasta
que el ruteo decida un workflow o se agoten los turnos. El agente tiene
desenlaces que por diseno piden otro turno -- confirmacion de un candidato
ambiguo, reintento de aclaracion, causal de una PQR "pelada" -- y evaluarlos
tras un solo mensaje los contaba como error de ruteo cuando son una pregunta
todavia abierta.

Se guarda un registro NDJSON por caso: la decision FINAL en los campos planos,
el detalle turno a turno en `turn_log`. El destino (MinIO o disco local) lo
decide `MINIO_ENABLED`; si MinIO falla, se degrada a local dejando traza.

Opcionalmente (`RABBITMQ_ENABLED`), cada caso y el resumen final se publican
tambien como eventos `benchmark.case` / `benchmark.run` en el exchange
`pqr.events`, el mismo que usa el agente para su analitica. Ver `events.py`.
"""

import io
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime

import requests
from src.benchmark.events import (
    BENCHMARK_MODE_HEADERS,
    CASE_ROUTING_KEY,
    RUN_ROUTING_KEY,
    BenchmarkEventPublisher,
    RunContext,
    build_case_event,
    build_run_event,
)
from src.commons.logging_utils import get_logger
from src.commons.object_store import ObjectStore
from src.settings.config import load_settings

settings = load_settings()
logger = get_logger("benchmark")

# `workflow_result` solo puede devolver: un id de workflow en snake_case,
# "pqrs_no_ruteo" (escalamiento a formulario) o "" (sin workflow). Cualquier
# texto libre usado como etiqueta daria MISS siempre.
_VALID_LABEL = re.compile(r"^[a-z0-9_]*$")

# Desenlaces terminales: el turno YA decidio (o descarto) un workflow.
_TERMINAL_OUTCOMES = frozenset({
    "matched", "no_match", "in_flow", "guardrail_blocked", "greeting", "other",
})

# Desenlaces PENDIENTES: el agente contesto pidiendo algo mas al usuario y el
# workflow definitivo todavia no existe. Son la razon de ser del bucle.
# Ver `_resolve_start_phase` en el chat_service del agente.
_PENDING_OUTCOMES = frozenset({
    "confirmation",            # candidato ambiguo (confidence=low) -> Continuar/Salir
    "pqrs_clarify",            # PQR sin causal -> Continuar y luego el motivo
    "clarify_retry",           # primer no-match -> pide reformular
    "clarify_unintelligible",  # entrada sin palabras -> pide reformular
})

_VALID_OUTCOMES = _TERMINAL_OUTCOMES | _PENDING_OUTCOMES | {"trx_canary_enabled"}

# Tipos de fallo de un caso. Los dos primeros son los historicos (ruteo);
# los otros dos los introducen los datasets adversariales y de bypass:
#   leak  -> alguna respuesta del bot contiene algo que el caso prohibe
#            (must_not_contain: numeros de tarjeta, credenciales, prompts...).
#   step  -> la conversacion termino en un paso que el caso prohibe
#            (forbid_steps: terminales de abono, bloqueo, reexpedicion...).
_MISS_KINDS = ("workflow", "outcome", "leak", "step", "invented", "grounding")

# Botones que hacen AVANZAR la conversacion. En la confirmacion oprimir
# "Continuar" es lo unico honesto: mide si la sugerencia del router era
# correcta. "Salir" ruteria a `pqrs_no_ruteo` y daria un acierto falso en todo
# caso cuyo esperado sea justamente ese.
_ADVANCE_OPTION_KEYS = ("continuar",)

# Desenlaces donde reenviar el mismo texto es lo que haria un usuario que
# insiste: agota el reintento de aclaracion y aterriza en el estado terminal.
_RESEND_OUTCOMES = frozenset({"clarify_retry", "clarify_unintelligible"})


def _fmt_tokens(value: int) -> str:
    """13603 -> '13.6k'. Mantiene legible la linea de progreso."""

    return f"{value / 1000:.1f}k" if value >= 1000 else str(value)


def _to_seconds(milliseconds: float) -> float:
    """Milisegundos -> segundos, con 3 decimales.

    La FRONTERA de unidades esta aqui. El agente publica `routing_time_ms` en la
    cabecera `X-Benchmark-Data` y eso no se toca: es el contrato entre los dos
    servicios. Todo lo que el benchmark guarda o imprime va en segundos, y por
    eso los campos de salida terminan en `_s`: un numero suelto llamado
    `routing_time` invita a leer 1200 como 1200 segundos.
    """

    return round(milliseconds / 1000, 3)


def _avg_per_turn(total_seconds: float, turns: int) -> float:
    """Media por turno. Devuelve 0.0 sin turnos, en vez de reventar.

    Se calcula sobre el TOTAL acumulado del caso dividido por sus turnos, no
    como media de medias: un caso de 3 turnos pesa lo que le corresponde.
    """

    return round(total_seconds / turns, 3) if turns else 0.0


def _validate_dataset(input_data) -> int:
    """Avisa de etiquetas que el agente no puede devolver nunca.

    Se ejecuta ANTES de gastar llamadas al LLM: una etiqueta mal escrita se
    detecta en un segundo, no tras veinte minutos de corrida.

    Returns:
        Numero de avisos emitidos.
    """

    warnings = 0
    for index, data in enumerate(input_data, 1):
        expected = data.get("expect_output", "")
        outcome = data.get("expect_outcome", "")
        follow_ups = data.get("follow_ups", [])

        if not _VALID_LABEL.match(expected):
            warnings += 1
            logger.warning(
                "[%d] expect_output no es un id de workflow: %r", index, expected
            )

        adversarial_case = any(
            data.get(k) for k in ("expect_output_any", "expect_outcome_any",
                                  "forbid_workflows", "forbid_steps", "must_not_contain",
                                  "must_not_invent", "must_contain")
        )
        if expected == "" and not outcome and not adversarial_case:
            warnings += 1
            logger.warning(
                "[%d] expect_output vacio sin expect_outcome: no se puede "
                "distinguir saludo de bloqueo ni de confirmacion",
                index,
            )

        if outcome and outcome not in _VALID_OUTCOMES:
            warnings += 1
            logger.warning("[%d] expect_outcome desconocido: %r", index, outcome)

        # Un desenlace PENDIENTE como esperado significa "quiero que el agente se
        # quede preguntando", que casi siempre es un error de escritura del
        # dataset: `expect_outcome` se compara contra el ULTIMO turno.
        if outcome in _PENDING_OUTCOMES:
            warnings += 1
            logger.warning(
                "[%d] expect_outcome=%r es un desenlace intermedio; el benchmark "
                "sigue conversando hasta uno terminal (%s)",
                index,
                outcome,
                ", ".join(sorted(_TERMINAL_OUTCOMES)),
            )

        if follow_ups and not (
            isinstance(follow_ups, list)
            and all(isinstance(item, str) for item in follow_ups)
        ):
            warnings += 1
            logger.warning(
                "[%d] follow_ups debe ser una lista de textos: %r", index, follow_ups
            )

        # Campos de los datasets adversariales / de bypass (todos opcionales).
        for key in ("expect_output_any", "forbid_workflows"):
            values = data.get(key, [])
            if values and not all(_VALID_LABEL.match(v) for v in values):
                warnings += 1
                logger.warning("[%d] %s trae ids que no son workflow: %r", index, key, values)
        for value in data.get("expect_outcome_any", []):
            if value not in _VALID_OUTCOMES:
                warnings += 1
                logger.warning("[%d] expect_outcome_any con desenlace desconocido: %r", index, value)
        for field in ("must_not_contain", "must_not_invent", "must_contain"):
            for pattern in data.get(field, []):
                try:
                    re.compile(pattern)
                except re.error as exc:
                    warnings += 1
                    logger.warning("[%d] %s con regex invalida %r: %s", index, field, pattern, exc)
        if data.get("user_id") is not None and not re.fullmatch(r"\d{1,15}", str(data["user_id"])):
            warnings += 1
            logger.warning("[%d] user_id debe ser numerico: %r", index, data["user_id"])
        if not any(data.get(k) for k in ("expect_output", "expect_outcome", "expect_output_any",
                                          "expect_outcome_any", "forbid_workflows", "forbid_steps",
                                          "must_not_contain")):
            warnings += 1
            logger.warning("[%d] el caso no declara ninguna expectativa", index)

    if warnings:
        logger.warning(
            "Dataset con %d aviso(s): esos casos darian MISS aunque el ruteo "
            "fuese correcto",
            warnings,
        )
    return warnings


def _log_header(*, mode: str, source: str, target: str, total: int) -> None:
    """Cabecera unica con todo lo que define la corrida."""

    logger.info("=" * 66)
    logger.info("Benchmark PQRS  |  modo=%s", mode)
    logger.info("  api       : %s", settings.api_base_url)
    logger.info("  entrada   : %s  (%d casos)", source, total)
    logger.info("  salida    : %s", target)
    logger.info("  max turnos: %d por caso", settings.max_turns)
    logger.info("=" * 66)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Percentil por indice mas cercano sobre una lista YA ordenada.

    Sin interpolacion a proposito: con decenas de casos, interpolar sugiere una
    precision que el tamano de muestra no sostiene.
    """

    if not sorted_values:
        return 0.0
    index = min(int(len(sorted_values) * fraction), len(sorted_values) - 1)
    return round(sorted_values[index], 3)


def _compute_metrics(stats: dict, elapsed_s: float) -> dict:
    """Todas las cifras derivadas de la corrida, en un solo sitio.

    El log y el fichero .txt leen de AQUI. Calcularlas dos veces era la via
    segura para que el resumen en pantalla y el fichero acabaran discrepando.

    Las medias "por turno" dividen el acumulado de toda la corrida entre el
    numero TOTAL de turnos, no entre casos ni como media de medias: asi un caso
    de tres turnos pesa lo que le corresponde.
    """

    evaluated = stats["ok"] + stats["miss"]
    turns = stats["turns"]
    total_turns = sum(turns)
    cases = len(turns)
    routing = sorted(stats["routing_s"])
    user = sorted(stats["user_s"])

    return {
        "modelos": ", ".join(sorted(stats["models"])) or "(desconocido)",
        "casos": stats["total"],
        "evaluados": evaluated,
        "aciertos": stats["ok"],
        "precision_pct": round(stats["ok"] / evaluated * 100, 1) if evaluated else 0.0,
        "fallos": stats["miss"],
        "fallos_workflow": stats["miss_workflow"],
        "fallos_outcome": stats["miss_outcome"],
        "fallos_leak": stats.get("miss_leak", 0),
        "fallos_step": stats.get("miss_step", 0),
        "fallos_invented": stats.get("miss_invented", 0),
        "fallos_grounding": stats.get("miss_grounding", 0),
        "sin_resolver": stats["unresolved"],
        "sin_resolver_turnos_agotados": stats["unresolved_max_turns"],
        "sin_resolver_falta_follow_up": stats["unresolved_needs_follow_up"],
        "saltados": stats["skipped"],

        "turnos_total": total_turns,
        "turnos_por_caso": round(total_turns / cases, 2) if cases else 0.0,
        "casos_multiturno": sum(1 for value in turns if value > 1),

        "tokens_in_total": stats["tokens_in"],
        "tokens_in_cacheados": stats["tokens_cached"],
        "cache_hit_pct": (
            round(stats["tokens_cached"] / stats["tokens_in"] * 100, 1)
            if stats["tokens_in"] else 0.0
        ),
        "tokens_out_total": stats["tokens_out"],
        "tokens_in_por_turno": _avg_per_turn(stats["tokens_in"], total_turns),
        "tokens_out_por_turno": _avg_per_turn(stats["tokens_out"], total_turns),
        "tokens_in_por_caso": _avg_per_turn(stats["tokens_in"], cases),
        "tokens_out_por_caso": _avg_per_turn(stats["tokens_out"], cases),

        "ruteo_s_por_turno": _avg_per_turn(stats["routing_s_sum"], total_turns),
        "e2e_s_por_turno": _avg_per_turn(stats["user_s_sum"], total_turns),
        "ruteo_s_caso_p50": _percentile(routing, 0.50),
        "ruteo_s_caso_p95": _percentile(routing, 0.95),
        "e2e_s_caso_p50": _percentile(user, 0.50),
        "e2e_s_caso_p95": _percentile(user, 0.95),
        "duracion_s": round(elapsed_s, 1),
    }


def _log_summary(stats: dict, elapsed_s: float) -> None:
    """Resumen final: responde '¿como fue la corrida?' sin abrir el JSON."""

    m = _compute_metrics(stats, elapsed_s)
    evaluated = m["evaluados"]
    accuracy = m["precision_pct"]
    p50_routing = m["ruteo_s_caso_p50"]
    p50_user = m["e2e_s_caso_p50"]
    avg_turns = m["turnos_por_caso"]
    multi_turn = m["casos_multiturno"]
    total_turns = m["turnos_total"]
    avg_routing_turn = m["ruteo_s_por_turno"]
    avg_user_turn = m["e2e_s_por_turno"]

    logger.info("=" * 66)
    logger.info("Resumen")
    logger.info(
        "  casos         : %d  (evaluados %d, sin resolver %d, saltados %d)",
        stats["total"],
        evaluated,
        stats["unresolved"],
        stats["skipped"],
    )
    logger.info("  aciertos      : %d  (%.1f%% de los evaluados)", stats["ok"], accuracy)
    # Separar los dos tipos importa: un fallo de workflow es un error de ruteo
    # real; uno de outcome suele ser el umbral de confianza (el modelo acerto
    # pero pidio confirmacion en vez de entrar al flujo).
    logger.info(
        "  fallos        : %d  (workflow %d, outcome %d)",
        stats["miss"],
        stats["miss_workflow"],
        stats["miss_outcome"],
    )
    # "Sin resolver" NO es un error de ruteo: es una conversacion que seguia
    # abierta al agotarse los turnos, o que pedia un dato que el dataset no
    # trae. Mezclarlo con los fallos era exactamente el sesgo que se corrigio.
    if stats["unresolved"]:
        logger.info(
            "  sin resolver  : %d  (turnos agotados %d, falta follow_up %d)",
            stats["unresolved"],
            stats["unresolved_max_turns"],
            stats["unresolved_needs_follow_up"],
        )
    logger.info(
        "  turnos        : %.2f por caso  (%d caso(s) con mas de uno)",
        avg_turns,
        multi_turn,
    )
    logger.info(
        "  tokens in/out : %s / %s  (total)",
        f"{m['tokens_in_total']:,}",
        f"{m['tokens_out_total']:,}",
    )
    logger.info(
        "  cache prompt  : %s de %s tokens de entrada servidos del cache (%.1f%%)",
        f"{m['tokens_in_cacheados']:,}",
        f"{m['tokens_in_total']:,}",
        m["cache_hit_pct"],
    )
    logger.info(
        "  tokens/turno  : %s in  /  %s out  (media de %d turnos)",
        f"{m['tokens_in_por_turno']:,.1f}",
        f"{m['tokens_out_por_turno']:,.1f}",
        total_turns,
    )
    logger.info(
        "  tiempo/turno  : ruteo %.2f s  ·  extremo a extremo %.2f s  (media de %d turnos)",
        avg_routing_turn,
        avg_user_turn,
        total_turns,
    )
    logger.info(
        "  tiempo/caso   : ruteo p50 %.2f s / p95 %.2f s  ·  e2e p50 %.2f s / p95 %.2f s",
        p50_routing,
        m["ruteo_s_caso_p95"],
        p50_user,
        m["e2e_s_caso_p95"],
    )
    logger.info(
        "  duracion      : %dm %02ds  (%.1f s)",
        int(elapsed_s // 60),
        int(elapsed_s % 60),
        elapsed_s,
    )
    logger.info("=" * 66)


def _build_summary_text(stats: dict, elapsed_s: float, *, source: str) -> str:
    """Resumen promediado de la corrida, en texto plano.

    Formato `clave : valor`, una por linea, para que sirva a la vez de lectura
    rapida y de fuente para un `grep`/`diff` entre corridas. Lee de
    `_compute_metrics`, igual que el log, asi que ambos no pueden discrepar.

    Se incluye el MODELO y el dataset de origen a proposito: dos corridas con
    modelos o lotes distintos no son comparables, y sin ese dato en el propio
    fichero es imposible saberlo despues.
    """

    m = _compute_metrics(stats, elapsed_s)

    def section(title: str) -> str:
        return f"\n--- {title} ---"

    def row(key: str, value) -> str:
        if isinstance(value, float):
            value = f"{value:,.2f}" if abs(value) < 10000 else f"{value:,.0f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        return f"{key:<28}: {value}"

    lines = [
        "=" * 62,
        "BENCHMARK PQRS - RESUMEN PROMEDIADO",
        "=" * 62,
        row("generado", datetime.now(UTC).isoformat(timespec="seconds")),
        row("api", settings.api_base_url),
        row("modelo", m["modelos"]),
        row("dataset", source),
        row("max_turnos", settings.max_turns),
        row("duracion_s", m["duracion_s"]),

        section("ACIERTO"),
        row("casos", m["casos"]),
        row("evaluados", m["evaluados"]),
        row("aciertos", m["aciertos"]),
        row("precision_pct", m["precision_pct"]),
        row("fallos", m["fallos"]),
        row("fallos_workflow", m["fallos_workflow"]),
        row("fallos_outcome", m["fallos_outcome"]),
        row("fallos_leak", m["fallos_leak"]),
        row("fallos_step", m["fallos_step"]),
        row("fallos_invented", m["fallos_invented"]),
        row("fallos_grounding", m["fallos_grounding"]),
        row("sin_resolver", m["sin_resolver"]),
        row("  turnos_agotados", m["sin_resolver_turnos_agotados"]),
        row("  falta_follow_up", m["sin_resolver_falta_follow_up"]),
        row("saltados", m["saltados"]),

        section("TURNOS"),
        row("turnos_total", m["turnos_total"]),
        row("turnos_por_caso", m["turnos_por_caso"]),
        row("casos_multiturno", m["casos_multiturno"]),

        section("TOKENS"),
        row("tokens_in_total", m["tokens_in_total"]),
        row("tokens_in_cacheados", m["tokens_in_cacheados"]),
        row("cache_hit_pct", m["cache_hit_pct"]),
        row("tokens_out_total", m["tokens_out_total"]),
        row("tokens_in_por_turno", m["tokens_in_por_turno"]),
        row("tokens_out_por_turno", m["tokens_out_por_turno"]),
        row("tokens_in_por_caso", m["tokens_in_por_caso"]),
        row("tokens_out_por_caso", m["tokens_out_por_caso"]),

        section("TIEMPOS (segundos)"),
        row("ruteo_s_por_turno", m["ruteo_s_por_turno"]),
        row("e2e_s_por_turno", m["e2e_s_por_turno"]),
        row("ruteo_s_caso_p50", m["ruteo_s_caso_p50"]),
        row("ruteo_s_caso_p95", m["ruteo_s_caso_p95"]),
        row("e2e_s_caso_p50", m["e2e_s_caso_p50"]),
        row("e2e_s_caso_p95", m["e2e_s_caso_p95"]),
        "",
        "Nota: 'por_turno' divide el acumulado de la corrida entre el numero",
        "TOTAL de turnos; 'por_caso' entre el numero de casos. El total mezcla",
        "cuanto cuesta una interaccion con cuantas hicieron falta.",
        "=" * 62,
        "",
    ]
    return "\n".join(lines)


def _extract_options(content: dict) -> list[dict]:
    """Botones del mensaje, normalizados a {key, label}."""

    return [
        {"key": option.get("key", ""), "label": option.get("label", "")}
        for option in (content.get("options") or [])
    ]


def _is_terminal(bench: dict) -> bool:
    """Si el turno cerro el ruteo o dejo la conversacion esperando al usuario.

    Un `workflow_result` no vacio manda sobre el desenlace: el turno en que el
    usuario acepta la confirmacion entra al flujo pero deja `routing_outcome`
    en "other", asi que mirar solo el desenlace lo daria por no resuelto.
    """

    if bench.get("workflow_result"):
        return True
    return bench.get("routing_outcome", "") not in _PENDING_OUTCOMES


def _next_reply(
    *,
    outcome: str,
    question: str,
    options: list[dict],
    follow_ups: list[str],
    turn_index: int,
) -> tuple[str | None, str]:
    """Que responder a un turno que todavia no decidio workflow.

    El dataset manda: si el caso trae `follow_ups`, se usa el que corresponde a
    este turno. Si no, entra el piloto automatico, que solo sabe avanzar de dos
    formas -- oprimir el boton afirmativo, o reenviar el texto original.

    Returns:
        (respuesta, origen). La respuesta es None cuando no hay forma honesta de
        seguir: ahi el caso queda "sin resolver" en vez de alimentar ruido al
        router.
    """

    scripted_index = turn_index - 1
    if scripted_index < len(follow_ups):
        return follow_ups[scripted_index], "dataset"

    for option in options:
        if option["key"] in _ADVANCE_OPTION_KEYS:
            return option["label"] or option["key"], "autopilot"

    if outcome in _RESEND_OUTCOMES:
        return question, "autopilot"

    # Texto libre pendiente (p. ej. el causal de una PQR): reenviar la pregunta
    # original volveria a disparar la misma aclaracion en bucle. Lo unico util
    # es que el dataset traiga la respuesta.
    return None, ""


def _evaluate(
    expected_wf: str,
    expected_outcome: str,
    bench: dict,
) -> tuple[bool, str, str]:
    """Compara la decision FINAL del agente con lo esperado.

    Cubre los tres valores posibles de `workflow_result` de forma uniforme: un
    id de workflow, `pqrs_no_ruteo`, o "" (sin workflow). Cuando se espera "",
    el desenlace es lo unico que distingue un saludo de un bloqueo, por eso
    `expect_outcome` manda en ese caso.

    Returns:
        (acierto, tipo de fallo, motivo). Los dos ultimos van vacios si acierta.
    """

    result = bench.get("workflow_result", "")
    outcome = bench.get("routing_outcome", "")

    # Entrar al flujo tras aceptar la confirmacion deja el desenlace en "other"
    # (el agente fija "other" al iniciar el turno y la rama afirmativa no lo
    # sobrescribe). Para el dataset eso es un match: se llego al workflow.
    if expected_outcome == "matched" and outcome == "other" and result:
        outcome = "matched"

    if result != expected_wf:
        return False, "workflow", (
            f"workflow esperado={expected_wf or '(ninguno)'} "
            f"obtenido={result or '(ninguno)'}"
        )

    if expected_outcome and outcome != expected_outcome:
        return False, "outcome", (
            f"outcome esperado={expected_outcome} obtenido={outcome or '(vacio)'}"
        )

    return True, "", ""


def _evaluate_case(
    data: dict, bench: dict, turn_log: list[dict], start_output: str = ""
) -> tuple[bool, str, str]:
    """Evaluacion completa de un caso: ruteo + prohibiciones + grounding.

    Orden de prioridad de los fallos, de mas grave a menos:
      1. leak      - una respuesta del bot contiene algo prohibido (``must_not_contain``).
      2. invented  - el bot afirmo algo que no esta en su fuente (``must_not_invent``).
      3. step      - la conversacion termino en un paso prohibido (``forbid_steps``).
      4. workflow / outcome - el ruteo no llego a donde el caso acepta.
      5. grounding - falta algo que la fuente obligaba a decir (``must_contain``).

    ``start_output`` es el saludo de ``POST /start``: forma parte de lo que el
    cliente lee, asi que entra en las tres comprobaciones de texto.

    La aceptacion del ruteo admite alternativas: ``expect_output_any`` (varios
    destinos validos) y ``expect_outcome_any`` (varios desenlaces validos, p. ej.
    ``guardrail_blocked`` o ``no_match``). Si el caso solo trae los campos
    historicos, se comporta exactamente como ``_evaluate``.
    """

    result = bench.get("workflow_result", "")
    outcome = bench.get("routing_outcome", "")
    final_step = bench.get("current_step", "")

    # 1) Contenido prohibido en CUALQUIER respuesta del bot (texto y botones).
    texts = [str(start_output or "")]
    for turn in turn_log:
        texts.append(str(turn.get("user_output", "")))
        texts.extend(str(label) for label in turn.get("user_options", []))
    haystack = "\n".join(texts)
    for pattern in data.get("must_not_contain", []):
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return False, "leak", f"la respuesta contiene {match.group(0)!r} (prohibido: {pattern})"

    # 1b) Afirmaciones sin fuente (grounding): datos, promesas o nombres que el
    # bot no tenia de donde sacar.
    for pattern in data.get("must_not_invent", []):
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return False, "invented", f"la respuesta afirma {match.group(0)!r} sin fuente (must_not_invent: {pattern})"

    # 2) Paso terminal prohibido (abonos, bloqueos, reexpediciones...).
    forbid_steps = data.get("forbid_steps", [])
    if forbid_steps and final_step in forbid_steps:
        return False, "step", f"termino en el paso prohibido {final_step}"

    # 3) Workflow prohibido.
    if result and result in data.get("forbid_workflows", []):
        return False, "workflow", f"ruteo al workflow prohibido {result}"

    # 4) Aceptacion del ruteo.
    output_any = list(data.get("expect_output_any", []))
    outcome_any = list(data.get("expect_outcome_any", []))
    if output_any or outcome_any:
        if outcome == "other" and result and "matched" in outcome_any:
            outcome = "matched"
        if (result in output_any) or (outcome in outcome_any):
            return _grounding_check(data, haystack)
        # El campo historico sigue valiendo como alternativa mas.
        if data.get("expect_output") or data.get("expect_outcome"):
            hit, kind, why = _evaluate(data.get("expect_output", ""), data.get("expect_outcome", ""), bench)
            if hit:
                return _grounding_check(data, haystack)
        kind = "outcome" if outcome_any and not output_any else "workflow"
        return False, kind, (
            f"workflow={result or '(ninguno)'} desenlace={outcome or '(vacio)'}; "
            f"aceptados: workflows {output_any or '-'}, desenlaces {outcome_any or '-'}"
        )

    if data.get("expect_output") or data.get("expect_outcome"):
        hit, kind, why = _evaluate(data.get("expect_output", ""), data.get("expect_outcome", ""), bench)
        return _grounding_check(data, haystack) if hit else (hit, kind, why)

    # Solo prohibiciones (p. ej. bypass): si no se violo ninguna, acierta.
    return _grounding_check(data, haystack)


def _grounding_check(data: dict, haystack: str) -> tuple[bool, str, str]:
    """Lo que la fuente obligaba a decir tiene que estar en alguna respuesta."""

    for pattern in data.get("must_contain", []):
        if not re.search(pattern, haystack, flags=re.IGNORECASE):
            return False, "grounding", f"falta en la respuesta lo que la fuente exige: {pattern}"
    return True, "", ""


def _post_chat(conversation_id: str, content: str) -> tuple[dict, dict, dict, float]:
    """Un turno contra `/chat` en modo benchmark.

    Returns:
        (cuerpo, cabecera de benchmark, contenido del mensaje, ms de ida y vuelta).

    Raises:
        RuntimeError: si el agente no responde 200/201.
    """

    init_time = time.time()
    response = requests.post(
        f"{settings.api_base_url}/chat",
        json={"conversation_id": conversation_id, "content": content},
        headers=BENCHMARK_MODE_HEADERS,
        timeout=(5, 150),  # > _BENCHMARK_TIMEOUT_SECONDS del agente
    )
    user_time_ms = round((time.time() - init_time) * 1000, 2)

    if response.status_code not in (200, 201):
        raise RuntimeError(f"/chat HTTP {response.status_code}: {response.text[:160]}")

    response_data = response.json()
    bench = json.loads(response.headers.get("X-Benchmark-Data", "{}"))
    content_data = (response_data.get("message") or {}).get("content") or {}
    return response_data, bench, content_data, user_time_ms


def _run_case(question: str, follow_ups: list[str], user_id: str | None = None) -> dict:
    """Conversa con el agente hasta el desenlace terminal o el techo de turnos.

    Returns:
        Un dict con la conversacion, el ultimo `bench` recibido, el detalle de
        cada turno y por que se detuvo (`resolution`).

    Raises:
        RuntimeError: si `/start` o algun `/chat` no responde como se espera.
    """

    # El dataset puede fijar el cliente (grounding del saludo: con nombre, sin
    # nombre, persona juridica); si no, uno aleatorio que no existe en ninguna
    # fuente de datos.
    user_id = str(user_id) if user_id else str(uuid.uuid4().int)[:8]
    # La cabecera va tambien en /start: ahi el agente marca la conversacion
    # como sintetica (source=benchmark) para toda su vida, no solo este turno.
    request_start = requests.post(
        f"{settings.api_base_url}/start",
        json={"user_id": user_id},
        headers=BENCHMARK_MODE_HEADERS,
        timeout=(5, 60),
    )
    if request_start.status_code not in (200, 201):
        raise RuntimeError(f"/start HTTP {request_start.status_code}")

    start_body = request_start.json()
    conversation_id = start_body.get("conversation_id")
    if not conversation_id:
        raise RuntimeError("/start sin conversation_id")
    # El saludo tambien lo lee el cliente: el dataset de grounding comprueba que
    # use el nombre cuando la fuente lo tiene y que no invente uno cuando no.
    start_output = str(((start_body.get("message") or {}).get("content") or {}).get("label", "") or "")

    turn_log: list[dict] = []
    bench: dict = {}
    response_data: dict = {}
    content_data: dict = {}
    resolution = "unresolved_max_turns"
    reply = question
    reply_source = "dataset"

    for turn_index in range(1, settings.max_turns + 1):
        response_data, bench, content_data, user_time_ms = _post_chat(
            conversation_id, reply
        )

        if not bench:
            # Sin cabecera no hay desenlace que leer: seguir conversando seria
            # avanzar a ciegas. Se corta y el caso queda sin resolver.
            logger.warning(
                # NO existe ninguna variable BENCHMARK_MODE_ENABLED: el agente
                # activa la captura solo con la cabecera x-benchmark-mode de esta
                # peticion. Si falta la respuesta, la causa esta en el agente, no
                # en su configuracion.
                "sin cabecera X-Benchmark-Data (turno %d): el agente no cerro la "
                "ventana de captura en ese turno, o no recibio la cabecera "
                "x-benchmark-mode (proxy que la elimina)",
                turn_index,
            )

        options = _extract_options(content_data)
        turn_log.append({
            "turn":             turn_index,
            "reply_source":     reply_source,
            "user_input":       reply,
            "workflow_result":  bench.get("workflow_result", ""),
            "workflow_llm":     bench.get("workflow_llm", ""),
            "routing_outcome":  bench.get("routing_outcome", ""),
            "confidence":       bench.get("confidence", ""),
            # Categorias que eligio el Nivel 1 (vacio si el pre-filtro esta
            # apagado). Sin esto, un enrutador que devuelve vacio no distingue
            # "el modelo no supo" de "el grupo correcto no estaba en el catalogo".
            "prefilter_groups": bench.get("prefilter_groups", []),
            "llm_token_input":  bench.get("llm_token_input", 0),
            "llm_token_output": bench.get("llm_token_output", 0),
            # SUBCONJUNTO de llm_token_input servido desde el cache de prefijo,
            # no un sumando aparte. Es la diferencia entre "subieron los tokens"
            # y "subio la factura", que no es lo mismo.
            "llm_token_cached": bench.get("llm_token_cached", 0),
            # Segundos desde aqui hacia abajo (ver _to_seconds).
            "routing_time_s":   _to_seconds(bench.get("routing_time_ms", 0)),
            "user_time_s":      _to_seconds(user_time_ms),
            "user_output":      content_data.get("label", ""),
            "user_options":     [option["label"] for option in options],
            # Quien redacto el texto: "model" (LLM), "local_fallback_*" o ""
            # (texto aprobado del YAML). Lo reporta el agente en la cabecera.
            "response_source":  bench.get("response_source", ""),
        })

        # Con follow_ups del dataset se sigue conversando AUNQUE el ruteo ya
        # sea terminal: es lo que permite a los casos de bypass empujar dentro
        # del flujo ("confirmame el abono", "salta ese paso") y medir donde
        # termina la conversacion. Sin follow_ups, el comportamiento historico.
        scripted_left = (turn_index - 1) < len(follow_ups)
        if not bench or (_is_terminal(bench) and not scripted_left):
            resolution = "resolved" if bench else "unresolved_no_header"
            break

        reply, reply_source = _next_reply(
            outcome=bench.get("routing_outcome", ""),
            question=question,
            options=options,
            follow_ups=follow_ups,
            turn_index=turn_index,
        )
        if reply is None:
            resolution = "unresolved_needs_follow_up"
            break
    else:
        # Se agoto el techo de turnos. Si el ultimo turno ya era terminal (caso
        # de bypass con follow_ups hasta el final), el caso SI queda resuelto.
        resolution = "resolved" if (bench and _is_terminal(bench)) else "unresolved_max_turns"

    _post_end(conversation_id)

    return {
        "conversation_id": conversation_id,
        "start_output":    start_output,
        "bench":           bench,
        "response_data":   response_data,
        "content_data":    content_data,
        "turn_log":        turn_log,
        "resolution":      resolution,
    }


def _post_end(conversation_id: str) -> None:
    """Cierra formalmente la conversacion sintetica. Fail-open.

    Sin este cierre la conversacion queda `Active` hasta que mantenimiento la
    recoja; con el, el agente emite su `conversation.closed` de inmediato y
    con la marca de benchmark. Si /end falla, el caso YA esta medido: se deja
    traza y se sigue.
    """

    try:
        response = requests.post(
            f"{settings.api_base_url}/end",
            json={"conversation_id": conversation_id},
            headers=BENCHMARK_MODE_HEADERS,
            timeout=(5, 30),
        )
        if response.status_code not in (200, 201):
            logger.warning(
                "/end HTTP %d para %s; la conversacion queda para mantenimiento",
                response.status_code,
                conversation_id,
            )
    except requests.RequestException as exc:
        logger.warning("/end fallo para %s: %s", conversation_id, exc)


def process_questions(
    input_data,
    write_line,
    *,
    publisher: BenchmarkEventPublisher | None = None,
    run: RunContext | None = None,
) -> dict:
    """Procesa cada caso, registra una linea por caso y devuelve estadisticas.

    Args:
        input_data: Lista de casos con `question`, `expect_output` y,
            opcionalmente, `expect_outcome` y `follow_ups` (las respuestas que
            debe dar el usuario simulado si el agente pide mas informacion).
        write_line: Sumidero del registro NDJSON (buffer de MinIO o archivo local).
        publisher: Publicador de eventos `benchmark.case` (opcional). Nunca
            lanza; si falta o esta apagado, no se publica nada.
        run: Identidad de la corrida que comparten todos los eventos.

    Returns:
        Estadisticas agregadas de la corrida para el resumen final.
    """

    total = len(input_data)
    width = len(str(total))
    stats = {
        "total": total,
        "ok": 0,
        "miss": 0,
        "miss_workflow": 0,
        "miss_outcome": 0,
        "miss_leak": 0,
        "miss_step": 0,
        "miss_invented": 0,
        "miss_grounding": 0,
        "unresolved": 0,
        "unresolved_max_turns": 0,
        "unresolved_needs_follow_up": 0,
        "skipped": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_cached": 0,
        # Modelos vistos en la corrida. Comparar dos corridas sin saber con que
        # modelo se hizo cada una es comparar nada.
        "models": set(),
        # Totales por caso, en segundos, para la mediana.
        "routing_s": [],
        "user_s": [],
        # Acumulados de TODA la corrida, para la media por turno global. Se
        # acumulan aparte de `routing_s` porque la media por turno divide entre
        # turnos, no entre casos.
        "routing_s_sum": 0.0,
        "user_s_sum": 0.0,
        "turns": [],
    }

    for question_num, data in enumerate(input_data, 1):
        question = data.get("question", "").strip()
        expect_output = data.get("expect_output", "")
        expect_outcome = data.get("expect_outcome", "")
        follow_ups = data.get("follow_ups") or []

        try:
            # En vuelo: solo en DEBUG, para identificar una pregunta colgada sin
            # ensuciar la salida normal.
            logger.debug("[%d/%d] -> %s", question_num, total, question[:60])

            case = _run_case(question, follow_ups, user_id=data.get("user_id"))

            bench = case["bench"]
            turn_log = case["turn_log"]
            resolved = case["resolution"] == "resolved"
            # Un caso adversarial puede aceptar un desenlace PENDIENTE (p. ej.
            # "clarify_retry" ante basura): si la conversacion quedo ahi, se
            # evalua en vez de contarse como abierta.
            if (
                not resolved
                and bench
                and bench.get("routing_outcome", "") in data.get("expect_outcome_any", [])
            ):
                resolved = True

            tokens_in = sum(turn["llm_token_input"] for turn in turn_log)
            tokens_out = sum(turn["llm_token_output"] for turn in turn_log)
            tokens_cached = sum(turn["llm_token_cached"] for turn in turn_log)
            turns_n = len(turn_log)
            # TOTAL del caso: la suma de sus turnos.
            routing_s = round(sum(turn["routing_time_s"] for turn in turn_log), 3)
            user_s = round(sum(turn["user_time_s"] for turn in turn_log), 3)
            # MEDIA POR TURNO: lo que tarda una interaccion suelta. Es la cifra
            # comparable entre casos, porque el total depende de cuantos turnos
            # necesito el caso -- un caso de 3 turnos no es "mas lento", es mas
            # largo.
            routing_s_avg = _avg_per_turn(routing_s, turns_n)
            user_s_avg = _avg_per_turn(user_s, turns_n)

            json_registry = {
                "conversation_id":  case["conversation_id"],
                "timestamp":        datetime.now(UTC).isoformat(),

                "workflow_expect":  expect_output,
                "outcome_expect":   expect_outcome,
                # Datasets adversariales: categoria del caso y paso en el que
                # termino la conversacion (lo reporta el agente en la cabecera).
                "category":         str(data.get("category", "") or ""),
                "final_step":       bench.get("current_step", ""),
                "response_source":  bench.get("response_source", ""),
                "workflow_result":  bench.get("workflow_result", ""),
                "workflow_llm":     bench.get("workflow_llm", ""),
                "routing_outcome":  bench.get("routing_outcome", ""),
                "confidence":       bench.get("confidence", ""),

                "llm_model":        bench.get("llm_model", ""),
                # Acumulados de toda la conversacion, no del ultimo turno.
                "llm_token_input":  tokens_in,
                "llm_token_output": tokens_out,
                "llm_token_cached": tokens_cached,
                "llm_token_cache_hit_pct": (
                    round(tokens_cached / tokens_in * 100, 1) if tokens_in else 0.0
                ),
                # Media por turno: la cifra comparable entre casos. El total
                # mezcla "cuanto gasta una interaccion" con "cuantos turnos
                # necesito el caso"; un caso de 3 turnos no gasta mas por turno,
                # gasta 3 veces.
                "llm_token_input_avg_turn":  _avg_per_turn(tokens_in, turns_n),
                "llm_token_output_avg_turn": _avg_per_turn(tokens_out, turns_n),

                # Totales del caso y media por turno, en segundos.
                "routing_time_total_s":    routing_s,
                "routing_time_avg_turn_s": routing_s_avg,
                "user_time_total_s":       user_s,
                "user_time_avg_turn_s":    user_s_avg,
                "status":           case["response_data"].get("status", ""),

                "turns":            len(turn_log),
                "resolution":       case["resolution"],
                "outcome_path":     [turn["routing_outcome"] for turn in turn_log],

                "user_input":       question,
                "start_output":     case.get("start_output", ""),
                "user_output":      case["content_data"].get("label", ""),
                "user_options": [
                    option.get("label", "")
                    for option in (case["content_data"].get("options") or [])
                ],
                "turn_log":         turn_log,
            }

            write_line(json.dumps(json_registry, ensure_ascii=False) + "\n")

            stats["turns"].append(turns_n)
            stats["tokens_in"] += tokens_in
            stats["tokens_out"] += tokens_out
            stats["tokens_cached"] += tokens_cached
            if bench.get("llm_model"):
                stats["models"].add(bench["llm_model"])
            stats["user_s"].append(user_s)
            stats["user_s_sum"] += user_s
            stats["routing_s_sum"] += routing_s
            if routing_s:
                stats["routing_s"].append(routing_s)

            # Una conversacion que quedo abierta NO se evalua: contarla como
            # fallo de ruteo era el sesgo que este bucle corrige.
            if not resolved:
                stats["unresolved"] += 1
                if case["resolution"] == "unresolved_needs_follow_up":
                    stats["unresolved_needs_follow_up"] += 1
                else:
                    stats["unresolved_max_turns"] += 1
                hit, miss_kind, reason = False, "", ""
            else:
                hit, miss_kind, reason = _evaluate_case(data, bench, turn_log, case.get("start_output", ""))
                stats["ok" if hit else "miss"] += 1
                if not hit:
                    stats[f"miss_{miss_kind}"] += 1

            if resolved:
                verdict = "OK" if hit else "MISS"
            else:
                verdict = "OPEN"

            # Mismo registro que el NDJSON y misma evaluacion que la precision:
            # el evento no recalcula nada. Fire-and-forget.
            if publisher is not None and run is not None:
                try:
                    publisher.publish(
                        CASE_ROUTING_KEY,
                        build_case_event(
                            json_registry,
                            run=run,
                            case_index=question_num,
                            note=data.get("nota", ""),
                            acierto=hit,
                            fail_kind=miss_kind if (resolved and not hit) else None,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 - el evento nunca altera el conteo
                    # El caso ya esta en el NDJSON y en stats: un fallo al
                    # construir el evento no puede contarlo como saltado.
                    logger.warning(
                        "benchmark.case not published for case %d (%s: %s)",
                        question_num,
                        type(exc).__name__,
                        exc,
                    )

            logger.info(
                "[%*d/%d] %-4s %-30s %-18s %6s>%-5s  t%d  "
                "rt %5.2fs  tt %5.2fs  x/turno %5.2fs",
                width,
                question_num,
                total,
                verdict,
                bench.get("workflow_result") or "(sin workflow)",
                f"{bench.get('routing_outcome', '?')}/{bench.get('confidence', '?')}",
                _fmt_tokens(tokens_in),
                _fmt_tokens(tokens_out),
                turns_n,
                routing_s,
                user_s,
                # Media por turno extremo a extremo: en un caso de un solo turno
                # coincide con `tt`, y en uno de tres se ve de golpe si tardo
                # porque cada turno es lento o porque hubo tres.
                user_s_avg,
            )

            indent = " " * (width * 2 + 4)

            # El camino solo aporta cuando hubo mas de un turno: ahi esta la
            # diferencia entre "el router acerto de una" y "acerto tras insistir".
            if len(turn_log) > 1:
                logger.info(
                    "%s camino: %s",
                    indent,
                    " > ".join(
                        turn["routing_outcome"] or "?" for turn in turn_log
                    ),
                )

            # Detalle SOLO cuando falla: el motivo exacto y lo que dijo el LLM
            # antes de los overrides (keyword-gate, pqrs_no_ruteo, cap).
            if resolved and not hit:
                logger.info(
                    "%s %s  |  llm=%s",
                    indent,
                    reason,
                    bench.get("workflow_llm") or "-",
                )
            elif case["resolution"] == "unresolved_needs_follow_up":
                logger.info(
                    "%s el agente pidio texto libre y el caso no trae "
                    "follow_ups: %r",
                    indent,
                    (case["content_data"].get("label") or "")[:80],
                )
            elif case["resolution"] == "unresolved_max_turns":
                logger.info(
                    "%s sin desenlace tras %d turno(s) (BENCHMARK_MAX_TURNS)",
                    indent,
                    len(turn_log),
                )

            # El registro completo ya va al archivo de salida; aqui solo bajo demanda.
            logger.debug("registro: %s", json.dumps(json_registry, ensure_ascii=False))

        except RuntimeError as exc:
            stats["skipped"] += 1
            logger.warning("[%d/%d] %s - se salta", question_num, total, exc)
        except requests.RequestException as exc:
            stats["skipped"] += 1
            logger.warning("[%d/%d] error de red: %s", question_num, total, exc)
        except Exception:
            stats["skipped"] += 1
            logger.exception("[%d/%d] error inesperado", question_num, total)

    return stats


def _publish_run_event(
    publisher: BenchmarkEventPublisher, run: RunContext, stats: dict, elapsed_s: float
) -> None:
    """`benchmark.run` desde el mismo resumen que el log y el .txt. Nunca lanza."""

    try:
        publisher.publish(
            RUN_ROUTING_KEY,
            build_run_event(_compute_metrics(stats, elapsed_s), run=run),
        )
    except Exception:
        logger.warning("No se pudo construir el evento benchmark.run", exc_info=True)
    finally:
        publisher.close()


def run_benchmark():
    object_store = None
    minio_enabled = False

    # Eventos benchmark.* por RabbitMQ: opcional y fire-and-forget. Se
    # construye siempre (inerte con RABBITMQ_ENABLED=false) para que el
    # camino de codigo sea uno solo.
    publisher = BenchmarkEventPublisher(settings)
    if publisher.enabled:
        logger.info(
            "RABBITMQ_ENABLED=true -> eventos a exchange=%s (source=%s)",
            settings.rabbitmq_exchange,
            settings.benchmark_source,
        )

    # Respeta el flag MINIO_ENABLED del ConfigMap; si es false, se trabaja en local
    # sin intentar construir el cliente S3.
    if settings.minio_enabled:
        try:
            object_store = ObjectStore(settings)
            minio_enabled = True
        except Exception:
            # Degradar a local cambia el destino de la salida: dejar traza completa.
            logger.warning(
                "MinIO no disponible (endpoint=%s bucket=%s) -> se continua en modo LOCAL",
                settings.minio_endpoint_url,
                settings.minio_bucket,
                exc_info=True,
            )
    else:
        logger.info("MINIO_ENABLED=false -> modo LOCAL")

    # ── MINIO MODE ──────────────────────────────────────────────
    if minio_enabled:
        input_key = settings.input_json
        output_key = settings.output_json

        if not object_store.exists(input_key):
            raise FileNotFoundError(f"Input object not found in MinIO: {input_key}")

        input_data = object_store.read_json(input_key)
        _validate_dataset(input_data)
        _log_header(
            mode=f"MinIO (bucket={settings.minio_bucket})",
            source=input_key,
            target=output_key,
            total=len(input_data),
        )

        started = time.time()
        run = RunContext.build(settings, input_source=input_key)
        output_buffer = io.StringIO()
        stats = process_questions(
            input_data, output_buffer.write, publisher=publisher, run=run
        )

        elapsed = time.time() - started

        object_store.write_bytes(
            key=output_key,
            data=output_buffer.getvalue().encode("utf-8"),
            content_type="application/x-ndjson",
        )
        logger.info("Salida escrita en MinIO: %s", output_key)

        # El resumen no puede tumbar la corrida: los resultados ya estan
        # escritos, y perder el .txt es molesto, no grave.
        try:
            object_store.write_bytes(
                key=settings.summary_txt,
                data=_build_summary_text(
                    stats, elapsed, source=input_key
                ).encode("utf-8"),
                content_type="text/plain; charset=utf-8",
            )
            logger.info("Resumen escrito en MinIO: %s", settings.summary_txt)
        except Exception:
            logger.warning(
                "No se pudo escribir el resumen en MinIO (key=%s); los resultados "
                "SI estan en %s",
                settings.summary_txt,
                output_key,
                exc_info=True,
            )

        _log_summary(stats, elapsed)
        _publish_run_event(publisher, run, stats, elapsed)

    # ── LOCAL MODE ──────────────────────────────────────────────
    else:
        input_path = settings.input_json
        output_path = settings.output_json

        # Create the directories if they do not exist (fully local).
        # `dirname` puede venir vacio si la ruta no lleva carpeta: makedirs("")
        # lanzaria FileNotFoundError.
        for directory in (os.path.dirname(input_path), os.path.dirname(output_path)):
            if directory:
                os.makedirs(directory, exist_ok=True)

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Local input file not found: {input_path}")

        with open(input_path, mode="r", encoding="utf-8") as input_file:
            input_data = json.load(input_file)

        _validate_dataset(input_data)
        _log_header(
            mode="LOCAL",
            source=input_path,
            target=output_path,
            total=len(input_data),
        )

        started = time.time()
        run = RunContext.build(settings, input_source=input_path)
        with open(output_path, mode="w", encoding="utf-8") as output_file:

            def write_line(line):
                output_file.write(line)
                output_file.flush()

            stats = process_questions(
                input_data, write_line, publisher=publisher, run=run
            )

        elapsed = time.time() - started
        logger.info("Salida escrita en local: %s", output_path)

        try:
            summary_dir = os.path.dirname(settings.summary_txt)
            if summary_dir:
                os.makedirs(summary_dir, exist_ok=True)
            with open(settings.summary_txt, mode="w", encoding="utf-8") as summary_file:
                summary_file.write(
                    _build_summary_text(stats, elapsed, source=input_path)
                )
            logger.info("Resumen escrito en local: %s", settings.summary_txt)
        except OSError:
            logger.warning(
                "No se pudo escribir el resumen (%s); los resultados SI estan en %s",
                settings.summary_txt,
                output_path,
                exc_info=True,
            )

        _log_summary(stats, elapsed)
        _publish_run_event(publisher, run, stats, elapsed)


def main() -> None:
    run_benchmark()
