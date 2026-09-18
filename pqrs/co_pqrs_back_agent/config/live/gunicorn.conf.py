import multiprocessing

from genai.libs.observability import setup_observability
from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID

# TAKE CARE: I have added the alias cfg to config since within the config
# file there can be the config attribute which is expected to be a path.
from src.infrastructure.core.config import genai_config as cfg

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 4 + 1
worker_class = "uvicorn.workers.UvicornWorker"


def post_fork(server, worker):
    worker_pid = worker.pid
    application = cfg.GENAI_PRODUCT
    product = cfg.GENAI_NAME
    service_name = cfg.GENAI_NAME
    service_instance_id = cfg.ECS_CONTAINER_METADATA_URI_V4.rsplit("/", 1)[-1].split(
        "-"
    )[0]

    setup_observability(
        cfg.GENAI_ENVIRONMENT,
        {
            "service.name": cfg.GENAI_NAME,
            SERVICE_INSTANCE_ID: service_instance_id,
            "worker": worker_pid,
            "AppRunner": service_name,
            "Application": application,
            "Product": product,
        },
        logging_level=cfg.DEFAULT_LOGGING_LEVEL,
        kinesis_stream=cfg.GENAI_OTEL_EXPORTER_KINESIS_STREAM,
        kinesis_obfuscate_fields=cfg.GENAI_OTEL_EXPORTER_KINESIS_STREAM_OBFUSCATE_FIELDS,
        otlp_obfuscate_fields=cfg.GENAI_OTEL_EXPORTER_OTLP_STREAM_OBFUSCATE_FIELDS,
    )

    meter = metrics.get_meter(__name__)
    # Crea una métrica de contador con el mismo nombre que en CloudWatch
    counter = meter.create_counter(
        name="gunicorn.worker",  # Reemplaza "MetricName" con el nombre de tu métrica
        description="",
        unit="count",  # Reemplaza "Unit" con la unidad de tu métrica
    )

    counter.add(1)

    server.log.info(
        f"Worker live spawned (instance-id: {service_instance_id} pid: {worker.pid})"
    )
