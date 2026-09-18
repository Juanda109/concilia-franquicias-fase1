"""FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from infrastructure.core.logger import get_logger
from infrastructure.entrypoint.api.errors.exceptions import ErrorHandlerError

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register project-specific exception handlers."""

    @app.exception_handler(ErrorHandlerError)
    async def handle_application_error(
        request: Request,
        exc: ErrorHandlerError,
    ) -> JSONResponse:
        logger.warning(
            "Handled application error path=%s code=%s details=%s",
            request.url.path,
            exc.error_code,
            exc.details,
        )
        return JSONResponse(
            status_code=exc.http_status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled exception path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected internal error occurred.",
                }
            },
        )
