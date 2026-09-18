from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # API configuration
    api_base_url: str
    
    # Files configuration
    input_json: str
    output_json: str
    summary_txt: str

    # Benchmark run configuration
    max_turns: int
    
    # MinIO configuration
    minio_enabled: bool
    minio_endpoint_url: str | None
    minio_bucket: str | None
    minio_region: str
    minio_access_key: str | None
    minio_secret_key: str | None
    minio_addressing_style: str

    # RabbitMQ event publishing (benchmark.case / benchmark.run). Mismos
    # nombres y valores por defecto que el agente: el exchange lo declara quien
    # llegue primero y ambos deben coincidir (topic, durable) o RabbitMQ rechaza
    # la segunda declaracion.
    rabbitmq_enabled: bool
    rabbitmq_url: str | None
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_vhost: str
    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_exchange: str
    rabbitmq_exchange_type: str
    rabbitmq_publish_timeout_seconds: float

    # Identidad de la corrida en los eventos.
    benchmark_source: str
    run_name: str | None
    catalog_version: str
    environment: str
