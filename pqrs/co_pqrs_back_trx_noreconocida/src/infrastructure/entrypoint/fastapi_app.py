"""FastAPI application for co_pqrs_back_trx_noreconocida (MOCK skeleton)."""

from __future__ import annotations

from fastapi import FastAPI, Request
import os

from infrastructure.core.config import load_trx_flow_settings

from infrastructure.core.logger import (
    bind_correlation,
    clear_correlation,
    get_logger,
    new_request_id,
)
from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import (
    router as healthcheck_router,
)
from infrastructure.entrypoint.api.router.v0.trx_router import router as trx_router

logger = get_logger(__name__)

app = FastAPI(
    title="co_pqrs_back_trx_noreconocida (MOCK)",
    version="0.1.0",
    description="Esqueleto MOCK del camino de transacción no reconocida.",
)


@app.middleware("http")
async def _correlation_middleware(request: Request, call_next):
    """Liga el X-Correlation-Id (conversation_id) que propaga el agente, para que
    las trazas ASO/Postgres del back_trx queden bajo la conversacion correcta."""
    correlation_id = request.headers.get("X-Correlation-Id")
    bind_correlation(conversation_id=correlation_id or None, request_id=new_request_id())
    try:
        return await call_next(request)
    finally:
        clear_correlation()


app.include_router(healthcheck_router)
app.include_router(trx_router)

logger.info("co_pqrs_back_trx_noreconocida app initialized (MOCK skeleton)")


@app.on_event("startup")
def _log_startup_env() -> None:
    """Log DIAS env values from the running process (reloader child).

    This helps confirm which process (parent vs child) sees the mounted .env/configmap.
    """
    try:
        flow = load_trx_flow_settings()
        env_file = os.getenv("ENV_FILE") or "/app/.env or .env"
        dias_dev = os.getenv("DIAS_HABILES_DEVOLUCION") or str(flow.dias_habiles_devolucion)
        dias_tar = os.getenv("DIAS_HABILES_TARJETA") or "(not set)"
        logger.info(
            "startup env: DIAS_HABILES_DEVOLUCION=%s DIAS_HABILES_TARJETA=%s ENV_FILE=%s",
            dias_dev,
            dias_tar,
            env_file,
        )
    except Exception:
        logger.exception("failed to log startup env values")
