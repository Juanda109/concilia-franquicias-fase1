from genai.libs.observability.instrumentation import setup_instruments
from genai.libs.observability.logging import setup_logging
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# TAKE CARE: I have added the alias cfg to config since within the config
# file there can be the config attribute which is expected to be a path.
from src.infrastructure.core.config import genai_config as cfg

bind = "0.0.0.0:8000"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"


def post_fork(server, worker):
    service_instance_id = "local"
    worker_pid = worker.pid
    application = cfg.GENAI_PRODUCT
    product = cfg.GENAI_NAME
    service_name = cfg.GENAI_NAME

    setup_logging(logging_level=cfg.DEFAULT_LOGGING_LEVEL)
    setup_instruments()

    resource = Resource(
        attributes={
            "service.name": cfg.GENAI_NAME,
            SERVICE_INSTANCE_ID: service_instance_id,
            "worker": worker_pid,
            "AppRunner": service_name,
            "Application": application,
            "Product": product,
        }
    )

    trace_provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    trace_provider.add_span_processor(processor)
    trace.set_tracer_provider(trace_provider)

    reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    server.log.info(
        f"Worker local spawned (instance-id: {service_instance_id} pid: {worker.pid})"
    )
