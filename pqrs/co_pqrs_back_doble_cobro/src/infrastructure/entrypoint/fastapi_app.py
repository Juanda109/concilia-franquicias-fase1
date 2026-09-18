"""FastAPI application for co_pqrs_back_doble_cobro (MOCK skeleton)."""

from __future__ import annotations

from fastapi import FastAPI, Request

from infrastructure.core.logger import (
    bind_correlation,
    clear_correlation,
    get_logger,
    new_request_id,
)
from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import (
    router as healthcheck_router,
)
from infrastructure.entrypoint.api.router.v0.doble_cobro_router import (
    router as doble_cobro_router,
)

logger = get_logger(__name__)

app = FastAPI(
    title="co_pqrs_back_doble_cobro (MOCK)",
    version="0.1.0",
    description="Esqueleto MOCK del camino de duplicidad en el cobro / doble cobro.",
)


@app.middleware("http")
async def _correlation_middleware(request: Request, call_next):
    """Liga el X-Correlation-Id (conversation_id) que propaga el agente, para que
    las trazas de este servicio queden bajo la conversacion correcta."""
    correlation_id = request.headers.get("X-Correlation-Id")
    bind_correlation(conversation_id=correlation_id or None, request_id=new_request_id())
    try:
        return await call_next(request)
    finally:
        clear_correlation()


app.include_router(healthcheck_router)
app.include_router(doble_cobro_router)

logger.info("co_pqrs_back_doble_cobro app initialized (MOCK skeleton)")
