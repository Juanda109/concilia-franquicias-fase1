"""Guardrail : LLM-as-judge de alcance (OPCIONAL, OFF por defecto).

Se activa con GUARDRAIL_JUDGE_ENABLED=true (variable de entorno del proceso o
.env). Si esta desactivado, judge_user_message() devuelve None de inmediato (sin
LLM, sin costo) y el comportamiento queda igual al de Fase 1 + Fase 2.

Los imports pesados (pydantic, strands, openai, config) son lazy: importar este
modulo solo requiere stdlib + logger, por eso sus piezas puras (verdict_to_block,
judge_enabled) son testeables sin el venv.
"""

from __future__ import annotations

import os
import random
import re
import time
import unicodedata

from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

OUT_OF_SCOPE_MESSAGES = (
    "Me encantaría ayudarte con eso, pero mi especialidad son tus finanzas. "
    "Pregúntame sobre tus cuentas, fondos o leasing y nos ponemos manos a la obra. "
    "¿Qué consulta tienes sobre tus productos?",
    "Para darte la mejor atención, prefiero que nos enfoquemos en tus temas bancarios. "
    "Puedo darte información útil sobre tus fondos o cuentas ahora mismo. "
    "¿Qué te gustaría revisar?",
)


def random_out_of_scope_message() -> str:
    """Return a random out-of-scope / off-topic block message."""

    return random.choice(OUT_OF_SCOPE_MESSAGES)

_JUDGE_SYSTEM_PROMPT = (
    "Eres un clasificador de alcance para un asistente de PQRS bancario en español. "
    "Decide si el mensaje del usuario corresponde a temas de banca, productos financieros, "
    "centrales de riesgo, certificados o PQRS (in_scope=true), o si es un tema ajeno al banco "
    "como reservas, restaurantes, comida, recetas, clima, deportes o entretenimiento (in_scope=false). "
    "Un saludo, una cortesia o un mensaje ambiguo que podria ser bancario debe tratarse como "
    "in_scope=true (no lo bloquees). Solo marca in_scope=false cuando el tema sea claramente ajeno "
    "al banco. Responde solo con la estructura solicitada.\n\n"
    "SESGO OBLIGATORIO A in_scope=true. Tu unico objetivo es filtrar temas evidentemente ajenos. "
    "Bloquear a un cliente con un problema real es un error grave; dejar pasar un mensaje ajeno "
    "no lo es, porque el enrutador lo resolvera despues.\n"
    "Es SIEMPRE in_scope=true (nunca lo bloquees) cualquier mensaje que mencione un producto "
    "(cuenta, tarjeta, CDT, credito, fondo, inversion, rendimientos, leasing, seguro, extracto), "
    "dinero o cifras (montos, saldos, cuotas, cobros, deudas, intereses), una queja, reclamo o PQR, "
    "centrales de riesgo, embargos, fraude, bloqueos, o el banco y sus canales (app, linea, oficina, "
    "cajero). Tampoco bloquees quejas sobre la atencion recibida.\n"
    "Ejemplos de in_scope=true: 'adquiri un cdt por el app de 50 millones y no se refleja la "
    "inversion ni los rendimientos'; 'me estan cobrando cuota de manejo'; 'tengo una queja'; "
    "'quitar bloqueo'; 'mi deuda fue traspasada a covinoc'; 'hice un abono a capital'.\n"
    "Ejemplos de in_scope=false: 'quiero reservar una mesa para dos'; 'dame una receta de ajiaco'; "
    "'quien gano el partido'; 'que clima hace manana'.\n"
    "Ante CUALQUIER duda: in_scope=true."
)


def judge_enabled() -> bool:
    """Whether the Fase 3 LLM judge is turned on (OFF by default)."""

    value = os.getenv("GUARDRAIL_JUDGE_ENABLED")
    if value is None:
        try:
            from infrastructure.core.config import load_env_constants

            value = load_env_constants().get("GUARDRAIL_JUDGE_ENABLED")
        except Exception:
            value = None
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


# Red de seguridad determinista contra falsos positivos del juez.
#
# Caso real (2026-08-20, conversacion 98909004_20260820): el juez marco
# in_scope=false para "adquiri un cdt por el app, de 50 millones, se vencia el 5
# de julio, a la fecha no se a reflejado en mi cuenta la inversion ni los
# rendimientos, en el banco no me dan razon y por la linea tampoco" y el cliente
# recibio el mensaje de fuera de alcance. El costo de un falso positivo (echar a
# un cliente con una queja real) es muy superior al de dejar pasar un mensaje
# ajeno, que de todas formas el router resolvera con is_match=false.
#
# Por eso: si el texto contiene CUALQUIER senal bancaria, el juez NO puede
# bloquear. El juez sigue encendido para lo que si es claramente ajeno
# ("quiero una hamburguesa", "que clima hace").
_BANKING_SIGNAL_WORDS: frozenset[str] = frozenset(
    {
        # Productos
        "cuenta", "cuentas", "ahorro", "ahorros", "corriente", "tarjeta", "tarjetas",
        "credito", "creditos", "debito", "cdt", "cdts", "fondo", "fondos", "inversion",
        "inversiones", "rendimiento", "rendimientos", "leasing", "hipotecario",
        "hipoteca", "libranza", "nomina", "seguro", "seguros", "poliza", "prestamo",
        "cupo", "extracto", "extractos", "certificado", "certificados", "portafolio",
        "cartera", "obligacion", "obligaciones", "producto", "productos",
        # Dinero y movimientos
        "plata", "dinero", "peso", "pesos", "millon", "millones", "saldo", "saldos",
        "cuota", "cuotas", "pago", "pagos", "pagar", "abono", "abonos", "cobro",
        "cobros", "cobrando", "deuda", "deudas", "interes", "intereses", "mora",
        "desembolso", "retiro", "retiros", "consignacion", "transferencia",
        "transferencias", "giro", "transaccion", "transacciones", "movimiento",
        "movimientos", "descuento", "descuentos", "debitaron", "cobraron",
        "capital", "plazo", "vencimiento", "vencia", "vence",
        # PQRS
        "queja", "quejas", "reclamo", "reclamos", "reclamacion", "pqr", "pqrs",
        "peticion", "tutela", "radicar", "radique", "inconformidad",
        # Centrales de riesgo y entidades
        "datacredito", "transunion", "cifin", "central", "centrales", "reporte",
        "reportado", "embargo", "embargada", "embargado", "desembargo", "covinoc",
        "banco", "bbva", "sucursal", "oficina", "cajero", "corresponsal",
        # Fraude
        "fraude", "estafa", "robo", "robaron", "suplantacion", "clonaron",
        "clonada", "reconozco", "reconocida", "reconocido", "bloqueo", "bloquear",
        "bloqueada", "bloqueado", "clave", "token",
        # Canales
        "app", "aplicacion", "linea", "sucursal", "cajero",
    }
)

_MONEY_PATTERN = re.compile(r"\$|\d[\d.,]{2,}|\b\d{4,}\b")


def _normalize_signal_text(text: str) -> str:
    """Lowercase + strip accents so 'crédito' matche 'credito'."""

    lowered = (text or "").casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def banking_signal_hits(text: str) -> list[str]:
    """Banking signals found in the text (empty list when there are none)."""

    normalized = _normalize_signal_text(text)
    tokens = set(re.findall(r"[a-z]+", normalized))
    hits = sorted(tokens & _BANKING_SIGNAL_WORDS)
    if _MONEY_PATTERN.search(normalized):
        hits.append("<monto/cifra>")
    return hits


def has_banking_signals(text: str) -> bool:
    """Whether the text carries any banking signal (product, money, PQRS, entity)."""

    return bool(banking_signal_hits(text))


def verdict_to_block(in_scope: bool, reason: str = "", text: str = "") -> str | None:
    """Map a scope verdict to a block message (out-of-scope) or None (allowed).

    Fails OPEN toward the customer: even when the judge says out-of-scope, a text
    with banking signals is never blocked (see _BANKING_SIGNAL_WORDS).
    """

    if in_scope:
        return None
    hits = banking_signal_hits(text)
    if hits:
        logger.warning(
            "Scope judge said out-of-scope but text has banking signals; "
            "OVERRIDING to allow reason=%s signals=%s",
            reason,
            hits[:8],
        )
        return None
    logger.info("Scope judge blocked out-of-scope input reason=%s", reason)
    return random_out_of_scope_message()


def _judge_base_url(endpoint: str) -> str:
    """Normalize the endpoint into an OpenAI-compatible base URL (mirrors the main agent)."""

    endpoint = endpoint.strip().rstrip("/")
    low = endpoint.casefold()
    if low.endswith("/openai/v1"):
        return f"{endpoint}/"
    if "openai.azure.com" in low and "/openai/" not in low:
        return f"{endpoint}/openai/v1/"
    return f"{endpoint}/"


def _build_judge_agent():
    """Build a Strands agent for scope judging using the same env as the main agent."""

    import openai
    from pydantic import BaseModel, ConfigDict, Field
    from strands import Agent
    from strands.models import OpenAIModel

    from infrastructure.core.config import load_env_constants

    constants = load_env_constants()
    ssl_verify = constants.get("SSL_VERIFY", "true").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }

    class ScopeJudgeVerdict(BaseModel):
        model_config = ConfigDict(extra="forbid")

        in_scope: bool = Field(
            description="True si el mensaje es de banca/PQRS; False si es ajeno al banco."
        )
        reason: str = Field(default="", description="Breve justificacion.")

    client = openai.AsyncOpenAI(
        api_key=constants["API_KEY"],
        base_url=_judge_base_url(constants["ENDPOINT"]),
        http_client=openai.DefaultAsyncHttpxClient(verify=ssl_verify),
        # Hard cap so the scope judge cannot hang the turn (fails open on error).
        timeout=120,
        max_retries=1,
    )
    agent = Agent(
        model=OpenAIModel(client=client, model_id=constants["LLM_MODEL"]),
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        callback_handler=None,
        name="Scope Judge",
        description="Clasifica si el mensaje del usuario esta dentro del alcance del banco.",
    )
    return agent, ScopeJudgeVerdict


async def judge_user_message(text: str) -> str | None:
    """Return a block message if the LLM judge marks the input out-of-scope.

    No-op (returns None) when disabled or on any error (fail-open).
    """

    if not judge_enabled():
        return None
    # Lazy import to keep this module importable with stdlib only.
    from infrastructure.observability.trace_audit import schedule_trace_event

    schedule_trace_event(
        event_type="llm",
        operation="guardrail_judge",
        outcome="started",
        request_summary={"text_length": len(text or "")},
        tags=["llm", "guardrail"],
    )
    start = time.perf_counter()
    try:
        agent, verdict_model = _build_judge_agent()
        result = await agent.invoke_async(text, structured_output_model=verdict_model)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        verdict = result.structured_output
        if verdict is None:
            schedule_trace_event(
                event_type="llm",
                operation="guardrail_judge",
                outcome="fallback_no_output",
                elapsed_ms=elapsed_ms,
                tags=["llm", "guardrail"],
            )
            return None
        block = verdict_to_block(
            bool(verdict.in_scope), getattr(verdict, "reason", ""), text
        )
        schedule_trace_event(
            event_type="llm",
            operation="guardrail_judge",
            outcome="ok",
            elapsed_ms=elapsed_ms,
            response_summary={"in_scope": bool(verdict.in_scope), "blocked": block is not None},
            tags=["llm", "guardrail"],
        )
        return block
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception("Scope judge failed; failing open (allowing input)")
        try:
            schedule_trace_event(
                event_type="llm",
                operation="guardrail_judge",
                outcome="error",
                elapsed_ms=elapsed_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
                tags=["llm", "guardrail"],
            )
        except Exception:  # noqa: BLE001
            pass
        return None
