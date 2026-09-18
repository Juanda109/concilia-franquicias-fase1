"""Publicador fire-and-forget de eventos `benchmark.*` hacia RabbitMQ.

El benchmark y el canario publican sus resultados por el MISMO pipeline de
analitica que el agente (exchange `pqr.events` -> Logstash -> OpenSearch), en
dos eventos:

- `benchmark.case`: uno por caso, construido del mismo registro que va al
  NDJSON (`build_case_event`).
- `benchmark.run`: uno por corrida, construido del mismo resumen que va al
  `.txt` (`build_run_event`).

Publicar es opcional y NUNCA puede tumbar ni retrasar la corrida: se activa con
`RABBITMQ_ENABLED`, cada publicacion traga cualquier excepcion tras loguearla,
los timeouts son cortos y el NDJSON/resumen se escriben igual que siempre.

La declaracion del exchange replica EXACTAMENTE la del agente
(`infrastructure/messaging/event_publisher.py`): mismo nombre, tipo `topic`,
`durable=True`. Si difiriera, RabbitMQ rechazaria la segunda declaracion
(PRECONDITION_FAILED) y uno de los dos dejaria de publicar.

`pika` se importa de forma perezosa para poder importar y probar el modulo
sin la dependencia instalada.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from src.classes.models import Settings
from src.commons.logging_utils import get_logger

logger = get_logger("benchmark.events")

# pika loguea cada intento fallido en ERROR con traceback (ocho lineas por
# evento). El aviso propio de `publish` ya dice que paso y por que; el ruido
# de la libreria solo estorba en el log del pod.
logging.getLogger("pika").setLevel(logging.CRITICAL)

CASE_ROUTING_KEY = "benchmark.case"
RUN_ROUTING_KEY = "benchmark.run"

# Cabecera con la que el agente reconoce una conversacion sintetica. Va en
# /start, /chat y /end: en /start marca la conversacion de forma persistente
# (`source=benchmark`) para que TODOS sus eventos conversation.* se desvien a
# los indices del benchmark en vez de contaminar pqr-metrics-*.
BENCHMARK_MODE_HEADERS = {"X-Benchmark-Mode": "true"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RunContext:
    """Identidad de una corrida: lo que comparten todos sus eventos."""

    source: str
    run_name: str
    run_id: str
    catalog_version: str
    environment: str
    flow: str
    started_at: datetime

    @classmethod
    def build(
        cls,
        settings: Settings,
        *,
        input_source: str,
        started_at: datetime | None = None,
    ) -> "RunContext":
        """Deriva la identidad desde la configuracion y el dataset de entrada.

        `flow` es el nombre del dataset sin extension (`doble_cobro_routing`),
        tanto si viene de una ruta local como de una key de MinIO.
        `run_id` = `run_name` + '_' + inicio de la corrida en `YYYYmmddTHHMMSSZ`,
        de modo que dos corridas del mismo dataset no colisionan.
        """

        started = started_at or datetime.now(UTC)
        flow = flow_from_source(input_source)
        run_name = settings.run_name or flow
        return cls(
            source=settings.benchmark_source,
            run_name=run_name,
            run_id=f"{run_name}_{started.strftime('%Y%m%dT%H%M%SZ')}",
            catalog_version=settings.catalog_version,
            environment=settings.environment,
            flow=flow,
            started_at=started,
        )

    def common_fields(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "run_name": self.run_name,
            "run_id": self.run_id,
            "catalog_version": self.catalog_version,
            "environment": self.environment,
            "flow": self.flow,
        }


def flow_from_source(input_source: str) -> str:
    """`input_data/doble_cobro_routing.json` -> `doble_cobro_routing`."""

    name = (input_source or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name or "unknown"


def build_case_event(
    registry: dict[str, Any],
    *,
    run: RunContext,
    case_index: int,
    note: str,
    acierto: bool,
    fail_kind: str | None,
) -> dict[str, Any]:
    """`benchmark.case` a partir del registro que se escribe en el NDJSON.

    `acierto` y `fail_kind` llegan ya calculados por el job (misma evaluacion
    que alimenta su precision): este modulo no re-evalua nada, solo transcribe.
    Un caso sin resolver viaja con `acierto=false` y `fail_kind=null`.
    """

    return {
        "event": CASE_ROUTING_KEY,
        "timestamp": registry.get("timestamp") or _utc_now_iso(),
        **run.common_fields(),
        "case_index": int(case_index),
        "user_input": registry.get("user_input", ""),
        "note": note or "",
        "category": registry.get("category", "") or "",
        "final_step": registry.get("final_step", "") or "",
        "workflow_expect": registry.get("workflow_expect", ""),
        "outcome_expect": registry.get("outcome_expect", ""),
        "workflow_result": registry.get("workflow_result", ""),
        "workflow_llm": registry.get("workflow_llm", ""),
        "routing_outcome": registry.get("routing_outcome", ""),
        "confidence": registry.get("confidence", ""),
        "acierto": bool(acierto),
        "fail_kind": fail_kind if fail_kind in ("workflow", "outcome", "leak", "step", "invented", "grounding") else None,
        "response_source": registry.get("response_source", "") or "",
        "resolution": registry.get("resolution", ""),
        "turns": int(registry.get("turns", 0) or 0),
        "llm_model": registry.get("llm_model", ""),
        "llm_token_input": int(registry.get("llm_token_input", 0) or 0),
        "llm_token_output": int(registry.get("llm_token_output", 0) or 0),
        "llm_token_cached": int(registry.get("llm_token_cached", 0) or 0),
        "llm_token_cache_hit_pct": float(
            registry.get("llm_token_cache_hit_pct", 0.0) or 0.0
        ),
        "routing_time_total_s": float(registry.get("routing_time_total_s", 0.0) or 0.0),
        "user_time_total_s": float(registry.get("user_time_total_s", 0.0) or 0.0),
        "conversation_id": registry.get("conversation_id", ""),
    }


def build_run_event(
    metrics: dict[str, Any],
    *,
    run: RunContext,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """`benchmark.run` a partir del resumen de `_compute_metrics`.

    `precision_workflow_pct` mide solo el ruteo: cuenta como acierto todo caso
    evaluado cuyo workflow coincide aunque el desenlace no (un fallo de
    `outcome` suele ser el umbral de confianza, no un error de ruteo).
    `cache_hit_pct_avg` es el porcentaje de tokens de entrada servidos del
    cache sobre toda la corrida.
    """

    evaluated = int(metrics.get("evaluados", 0) or 0)
    hits = int(metrics.get("aciertos", 0) or 0)
    outcome_misses = int(metrics.get("fallos_outcome", 0) or 0)
    precision_workflow = (
        round((hits + outcome_misses) / evaluated * 100, 1) if evaluated else 0.0
    )

    return {
        "event": RUN_ROUTING_KEY,
        "timestamp": timestamp or _utc_now_iso(),
        **run.common_fields(),
        "cases_total": int(metrics.get("casos", 0) or 0),
        "cases_ok": hits,
        "cases_unresolved": int(metrics.get("sin_resolver", 0) or 0),
        "precision_pct": float(metrics.get("precision_pct", 0.0) or 0.0),
        "precision_workflow_pct": precision_workflow,
        "routing_p50_s": float(metrics.get("ruteo_s_caso_p50", 0.0) or 0.0),
        "routing_p95_s": float(metrics.get("ruteo_s_caso_p95", 0.0) or 0.0),
        "e2e_p50_s": float(metrics.get("e2e_s_caso_p50", 0.0) or 0.0),
        "e2e_p95_s": float(metrics.get("e2e_s_caso_p95", 0.0) or 0.0),
        "tokens_input_total": int(metrics.get("tokens_in_total", 0) or 0),
        "tokens_output_total": int(metrics.get("tokens_out_total", 0) or 0),
        "cache_hit_pct_avg": float(metrics.get("cache_hit_pct", 0.0) or 0.0),
        "llm_model": metrics.get("modelos", "") or "",
        "duration_s": float(metrics.get("duracion_s", 0.0) or 0.0),
    }


def effective_amqp_url(settings: Settings) -> str:
    """URL AMQP, con `RABBITMQ_URL` mandando si esta definida (como el agente)."""

    if settings.rabbitmq_url:
        return settings.rabbitmq_url

    vhost = settings.rabbitmq_vhost
    vhost_path = quote(vhost, safe="") if vhost not in ("", "/") else ""
    return (
        f"amqp://{quote(settings.rabbitmq_user, safe='')}:"
        f"{quote(settings.rabbitmq_password, safe='')}"
        f"@{settings.rabbitmq_host}:{settings.rabbitmq_port}/{vhost_path}"
    )


# Fallos de publicacion seguidos a partir de los cuales se deja de intentar.
MAX_CONSECUTIVE_FAILURES = 3


class BenchmarkEventPublisher:
    """Publica eventos JSON a un exchange topic durable. Sincrono, nunca lanza.

    El job es sincrono, asi que se usa `pika.BlockingConnection`. La conexion
    se abre perezosamente en la primera publicacion y se descarta ante
    cualquier error, de modo que la siguiente publicacion reintenta desde
    cero (un solo intento de conexion, con timeout corto).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: Any | None = None
        self._channel: Any | None = None
        self.published = 0
        self.failed = 0
        # Cortacircuito: tras N fallos de conexion SEGUIDOS se deja de intentar
        # por el resto de la corrida. Sin el, un broker que no rechaza sino que
        # descarta (NetworkPolicy, DNS) cobraria el timeout completo en cada
        # evento y alargaria el job varios minutos.
        self._consecutive_failures = 0
        self._disabled_after_failures = False

    @property
    def enabled(self) -> bool:
        return bool(self._settings.rabbitmq_enabled)

    def _connection_parameters(self) -> Any:
        import pika

        timeout = float(self._settings.rabbitmq_publish_timeout_seconds)
        params = pika.URLParameters(effective_amqp_url(self._settings))
        # Un intento, timeouts cortos: si RabbitMQ no esta, el job sigue.
        params.connection_attempts = 1
        params.socket_timeout = timeout
        params.blocked_connection_timeout = timeout
        # pika espera hasta 15 s por defecto en el handshake; se acota igual.
        params.stack_timeout = timeout
        return params

    def _ensure_channel(self) -> Any:
        if self._channel is not None and self._channel.is_open:
            return self._channel

        import pika

        self._connection = pika.BlockingConnection(self._connection_parameters())
        self._channel = self._connection.channel()
        # Misma declaracion que el agente: nombre, tipo topic y durable=True.
        self._channel.exchange_declare(
            exchange=self._settings.rabbitmq_exchange,
            exchange_type=self._settings.rabbitmq_exchange_type,
            durable=True,
        )
        logger.info(
            "RabbitMQ exchange ready exchange=%s type=%s",
            self._settings.rabbitmq_exchange,
            self._settings.rabbitmq_exchange_type,
        )
        return self._channel

    def publish(self, routing_key: str, payload: dict[str, Any]) -> bool:
        """Publica un evento JSON persistente. Devuelve True si se envio.

        Cualquier excepcion se loguea y se traga; la conexion se reinicia para
        que el siguiente evento vuelva a intentar conectar.
        """

        if not self.enabled or self._disabled_after_failures:
            return False

        try:
            import pika

            channel = self._ensure_channel()
            channel.basic_publish(
                exchange=self._settings.rabbitmq_exchange,
                routing_key=routing_key,
                body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistente, como el agente
                ),
            )
            self.published += 1
            self._consecutive_failures = 0
            logger.debug("Published event routing_key=%s", routing_key)
            return True
        except Exception as exc:
            self.failed += 1
            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self._disabled_after_failures = True
                logger.warning(
                    "RabbitMQ unreachable after %d consecutive failures; "
                    "event publishing disabled for the rest of the run",
                    self._consecutive_failures,
                )
            logger.warning(
                "Failed to publish event routing_key=%s (%s: %s); the run continues",
                routing_key,
                type(exc).__name__,
                str(exc) or repr(exc.args),
            )
            self._reset()
            return False

    def _reset(self) -> None:
        connection = self._connection
        self._connection = None
        self._channel = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                logger.debug("Error while closing RabbitMQ connection", exc_info=True)

    def close(self) -> None:
        """Cierra la conexion (al final de la corrida). Nunca lanza."""

        self._reset()
        if self.enabled:
            logger.info(
                "RabbitMQ events published=%d failed=%d", self.published, self.failed
            )
