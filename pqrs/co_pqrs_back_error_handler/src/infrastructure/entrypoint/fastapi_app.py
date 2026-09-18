"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from infrastructure.core.logger import configure_logging, get_logger, log_execution
from infrastructure.entrypoint.api.errors.exception_handlers import (
    register_exception_handlers,
)
from infrastructure.entrypoint.api.router.router_handler import router as api_router

configure_logging()
logger = get_logger(__name__)


@log_execution
def build_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="co_pqrs_back_error_handler API",
        version="0.1.0",
        description=(
            "API para recibir fallos del agente, recuperar la conversacion "
            "desde OpenSearch y exportar un JSON local con datos para analitica."
        ),
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    logger.info("FastAPI application ready")
    return app


app = build_app()
