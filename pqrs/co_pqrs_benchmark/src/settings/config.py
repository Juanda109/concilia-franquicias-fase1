from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from src.classes.models import Settings


# Valores que reconocen el tablero y la alerta (source: canario). Un valor
# distinto publicaria eventos validos que nadie veria.
VALID_BENCHMARK_SOURCES = ("benchmark", "canario", "adversarial", "grounding")


def _load_benchmark_source() -> str:
    raw = os.getenv("BENCHMARK_SOURCE", "benchmark").strip() or "benchmark"
    if raw in VALID_BENCHMARK_SOURCES:
        return raw
    logging.getLogger(__name__).warning(
        "BENCHMARK_SOURCE=%r is not one of %s; falling back to 'benchmark'",
        raw,
        VALID_BENCHMARK_SOURCES,
    )
    return "benchmark"


def load_settings() -> Settings:

    load_dotenv()

    return Settings(
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8000"),

        input_json=os.getenv("INPUT_JSON", ".data/input_data/user_input.json"),
        output_json=os.getenv("OUTPUT_JSON", ".data/output_data/user_output.json"),

        # Resumen promediado en texto plano, junto al NDJSON de resultados. Es
        # un fichero aparte y no una linea mas del NDJSON porque responde a otra
        # pregunta: "como fue la corrida", no "que paso en cada caso".
        summary_txt=os.getenv(
            "SUMMARY_TXT", ".data/output_data/user_output_summary.txt"
        ),

        # Techo de turnos por caso. 4 cubre la cadena mas larga que el agente
        # puede pedir (PQR pelada: intro -> Continuar -> causal -> ruteo) con un
        # turno de margen; subirlo solo alarga corridas que ya no van a resolver.
        max_turns=parse_int_env("BENCHMARK_MAX_TURNS", default=4),

        minio_enabled=parse_bool_env("MINIO_ENABLED", default=False),
        minio_endpoint_url=empty_to_none(os.getenv("MINIO_ENDPOINT_URL")),
        minio_bucket=empty_to_none(os.getenv("MINIO_BUCKET")),
        minio_region=os.getenv("MINIO_REGION", "us-east-1"),
        minio_access_key=empty_to_none(os.getenv("MINIO_ACCESS_KEY")),
        minio_secret_key=empty_to_none(os.getenv("MINIO_SECRET_KEY")),
        minio_addressing_style=os.getenv("MINIO_ADDRESSING_STYLE", "path"),

        # Publicacion de eventos benchmark.* por RabbitMQ (fire-and-forget).
        # Apagado por defecto; con la misma variable y valores que el agente.
        rabbitmq_enabled=parse_bool_env("RABBITMQ_ENABLED", default=False),
        rabbitmq_url=empty_to_none(os.getenv("RABBITMQ_URL")),
        rabbitmq_host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        rabbitmq_port=parse_amqp_port_env("RABBITMQ_PORT", default=5672),
        rabbitmq_vhost=os.getenv("RABBITMQ_VHOST", "/"),
        rabbitmq_user=os.getenv("RABBITMQ_USER", "guest"),
        rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        rabbitmq_exchange=os.getenv("RABBITMQ_EXCHANGE", "pqr.events"),
        rabbitmq_exchange_type=os.getenv("RABBITMQ_EXCHANGE_TYPE", "topic"),
        rabbitmq_publish_timeout_seconds=parse_float_env(
            "RABBITMQ_PUBLISH_TIMEOUT_SECONDS", default=5.0
        ),

        # Identidad de la corrida en los eventos. `benchmark` para las corridas
        # a demanda, `canario` para el CronJob de monitoreo.
        benchmark_source=_load_benchmark_source(),
        run_name=empty_to_none(os.getenv("RUN_NAME")),
        catalog_version=os.getenv("CATALOG_VERSION", "unknown").strip() or "unknown",
        environment=os.getenv("ENVIRONMENT", "local").strip() or "local",
    )

def parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw_value}")

def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)

def parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return float(raw_value)


def parse_amqp_port_env(name: str, default: int) -> int:
    """Puerto AMQP tolerante al service-link de Kubernetes.

    Con un Service llamado `rabbitmq` en el namespace, Kubernetes inyecta
    `RABBITMQ_PORT=tcp://<ip>:<puerto>` en cada pod. Se extrae el puerto de
    esa forma o se devuelve el valor por defecto; nunca se revienta por esto.
    Misma tolerancia que `_parse_amqp_port` del agente.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    text = raw_value.strip()
    if text.isdigit():
        return int(text)
    tail = text.rsplit(":", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return default


def empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
