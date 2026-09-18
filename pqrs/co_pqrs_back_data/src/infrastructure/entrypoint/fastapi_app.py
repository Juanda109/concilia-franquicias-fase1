"""FastAPI application entrypoint."""

import json
import time

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from infrastructure.core.config import load_audit_min_status, load_cors_settings
from infrastructure.core.logger import (
    bind_correlation,
    clear_correlation,
    configure_logging,
    get_correlation_id,
    get_logger,
    log_execution,
    new_request_id,
)
from infrastructure.entrypoint.api.errors.exceptions import BackDataError
from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import (
    router as health_router,
)
from infrastructure.entrypoint.api.router.v0.consultar_router import (
    router as consultar_router,
)
from infrastructure.observability.error_audit import (
    schedule_error_report,
    schedule_http_error_report,
)
from infrastructure.observability.request_log_capture import (
    finish_request_capture,
    install_capture_handler,
    ship_request_log,
    start_request_capture,
)

configure_logging()
logger = get_logger(__name__)

# Paths excluded from per-request access logging to avoid terminal noise.
_ACCESS_LOG_SKIP_PREFIXES = ("/health", "/docs", "/openapi", "/redoc")

# Minimum HTTP status that triggers an error audit (read once per process).
_AUDIT_MIN_STATUS = load_audit_min_status()
# 406 is audited with richer detail by the validation handler.
_AUDIT_SKIP_STATUS = {406}


async def _correlation_access_middleware(request: Request, call_next):
    """Bind correlation (request id + X-Correlation-Id + customer_id) and log access.

    ``X-Correlation-Id`` is sent by the agent so a customer request can be matched
    across both services. ``customer_id`` comes from the query string. Context is
    always cleared so it never leaks between requests.
    """

    request_id = new_request_id()
    incoming_correlation = request.headers.get("X-Correlation-Id")
    customer_id = request.query_params.get("customer_id")
    bind_correlation(conversation_id=incoming_correlation, customer_id=customer_id)

    path = request.url.path
    method = request.method
    is_excluded = path.startswith(_ACCESS_LOG_SKIP_PREFIXES)
    skip_access_log = is_excluded
    started_at = time.monotonic()
    capture_token = None if is_excluded else start_request_capture(request_id)
    status_for_log: int | None = None
    try:
        response = await call_next(request)
        status_for_log = response.status_code
    except Exception as exc:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        status_for_log = 500
        logger.exception(
            "HTTP %s %s -> error after %.0fms",
            method,
            path,
            elapsed_ms,
        )
        if not is_excluded:
            schedule_error_report(
                error=exc,
                source=f"{method} {path}",
                conversation_id=incoming_correlation,
            )
        raise
    finally:
        # Ship the full per-request log capture (SEPARATE request-logs/ prefix).
        captured = finish_request_capture(capture_token)
        if captured is not None:
            ship_request_log(
                buffer=captured,
                conversation_id=incoming_correlation,
                customer_id=customer_id,
                method=method,
                path=path,
                status_code=status_for_log,
                elapsed_ms=(time.monotonic() - started_at) * 1000,
            )
        clear_correlation()

    if not skip_access_log:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            "HTTP %s %s -> %s %.0fms",
            method,
            path,
            response.status_code,
            elapsed_ms,
        )

    if (
        not is_excluded
        and response.status_code >= _AUDIT_MIN_STATUS
        and response.status_code not in _AUDIT_SKIP_STATUS
    ):
        schedule_http_error_report(
            status_code=response.status_code,
            method=method,
            path=path,
            conversation_id=incoming_correlation,
        )

    return response


def _format_request_body(raw_body: bytes) -> str:
    """Render a request body into a readable log string."""

    if not raw_body:
        return "<empty>"

    decoded_body = raw_body.decode("utf-8", errors="replace")

    try:
        parsed_body = json.loads(decoded_body)
    except json.JSONDecodeError:
        return decoded_body

    return json.dumps(parsed_body, ensure_ascii=False, indent=2)


@log_execution
async def log_request_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    """Log raw inbound payloads when FastAPI rejects the request with 406."""

    raw_body = await request.body()
    logger.warning(
        "Request validation failed method=%s path=%s content_type=%s errors=%s body=\n%s",
        request.method,
        request.url.path,
        request.headers.get("content-type", "<missing>"),
        exc.errors(),
        _format_request_body(raw_body),
    )
    response = await request_validation_exception_handler(request, exc)
    response.status_code = 406
    return response


@log_execution
async def handle_back_data_error(request: Request, exc: BackDataError):
    """Translate application errors into HTTP responses."""

    from fastapi.responses import JSONResponse

    logger.warning(
        "Application error path=%s error_code=%s message=%s",
        request.url.path,
        exc.error_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.http_status_code,
        content={"error": exc.to_dict()["error"]},
    )


@log_execution
def _custom_openapi(app: FastAPI) -> dict:
    """Build the OpenAPI schema replacing autogenerated 422 validation responses with 406."""

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue

            responses = operation.get("responses", {})
            validation_response = responses.pop("422", None)
            if validation_response is not None:
                responses["406"] = validation_response

    app.openapi_schema = openapi_schema
    return app.openapi_schema


@log_execution
def build_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    logger.info("Building FastAPI application instance")
    cors_settings = load_cors_settings()
    app = FastAPI(
        title="co_pqrs_back_data API",
        version="0.1.0",
        description="API for health checks and customer CSV queries.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_settings.allow_origins,
        allow_methods=cors_settings.allow_methods,
        allow_headers=cors_settings.allow_headers,
        expose_headers=cors_settings.expose_headers,
        allow_credentials=cors_settings.allow_credentials,
        max_age=cors_settings.max_age,
    )
    app.middleware("http")(_correlation_access_middleware)
    logger.info("Registered correlation/access middleware")
    install_capture_handler()
    app.add_exception_handler(RequestValidationError, log_request_validation_error)
    app.add_exception_handler(BackDataError, handle_back_data_error)
    app.include_router(health_router)
    app.include_router(consultar_router)
    app.openapi = lambda: _custom_openapi(app)
    return app


app = build_app()

