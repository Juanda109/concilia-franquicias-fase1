"""FastAPI application entrypoint."""

import json
import time

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from infrastructure.core.config import (
    load_audit_min_status,
    load_cors_settings,
)
from infrastructure.core.logger import (
    clear_correlation,
    configure_logging,
    get_correlation_id,
    get_logger,
    log_execution,
    new_request_id,
)
from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import (
    router as health_router,
)
from infrastructure.entrypoint.api.router.v0.chat_router import router as chat_router
from infrastructure.observability.benchmark_context import (
    BENCHMARK_HEADER,
    BENCHMARK_REQUEST_HEADER,
    encode_header,
    finish_capture,
    start_capture,
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

# Validation (406) is audited with richer detail by the validation handler, so
# the middleware skips it to avoid double-reporting.
_AUDIT_SKIP_STATUS = {406}


def _audit_conversation_id() -> str | None:
    """Return the bound conversation id, or None when not set."""

    correlation_id = get_correlation_id()
    return correlation_id if correlation_id and correlation_id != "-" else None


async def _correlation_access_middleware(request: Request, call_next):
    """Bind a request id and log one access line per request (path + status + ms).

    The correlation block (cid/cust) is bound deeper, inside the route/service
    once the conversation id is known; this middleware guarantees every request
    is traceable and that context never leaks between requests.
    """

    request_id = new_request_id()
    path = request.url.path
    method = request.method
    is_excluded = path.startswith(_ACCESS_LOG_SKIP_PREFIXES)
    skip_access_log = is_excluded
    started_at = time.monotonic()
    audit_conv_id: str | None = None
    capture_token = None if is_excluded else start_request_capture(request_id)
    benchmark_token = (
        start_capture() if request.headers.get(BENCHMARK_REQUEST_HEADER) else None
    )
    benchmark_data: dict | None = None
    conv_for_log: str | None = None
    conv_for_log: str | None = None
    status_for_log: int | None = None
    try:
        response = await call_next(request)
        audit_conv_id = _audit_conversation_id()
        conv_for_log = audit_conv_id
        status_for_log = response.status_code
    except Exception as exc:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        conv_for_log = _audit_conversation_id()
        status_for_log = 500
        logger.exception(
            "HTTP %s %s -> error after %.0fms",
            method,
            path,
            elapsed_ms,
        )
        if not is_excluded:
            # E2E audit: capture every unhandled exception with its traceback.
            schedule_error_report(
                conversation_id=conv_for_log,
                error=exc,
                source=f"{method} {path}",
            )
        raise
    finally:
        # Un turno de chat que respondio bien lleva SIEMPRE la cabecera del
        # benchmark, aunque no haya pasado por el ruteo (transiciones de paso,
        # pregunta de satisfaccion). Con error o en otras rutas, solo si se cerro.
        benchmark_data = finish_capture(
            benchmark_token,
            complete_in_flow=(
                method == "POST"
                and path.endswith("/chat")
                and status_for_log is not None
                and status_for_log < 400
            ),
        )
        # Ship the full per-request log capture (SEPARATE request-logs/ prefix).
        captured = finish_request_capture(capture_token)
        if captured is not None:
            ship_request_log(
                buffer=captured,
                conversation_id=conv_for_log,
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
        # E2E audit: capture every error response (4xx/5xx), e.g. a malformed
        # conversation id (404/409) that never raised an exception.
        schedule_http_error_report(
            conversation_id=audit_conv_id,
            status_code=response.status_code,
            method=method,
            path=path,
        )
    if benchmark_data:
        response.headers[BENCHMARK_HEADER] = encode_header(benchmark_data)

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

    # E2E audit: malformed payloads (e.g. a bad/letters conversation id) never
    # raise an exception, so capture them here with field-level detail.
    try:
        conversation_id = None
        try:
            parsed_body = json.loads(raw_body) if raw_body else {}
            if isinstance(parsed_body, dict):
                conversation_id = parsed_body.get("conversation_id")
        except json.JSONDecodeError:
            parsed_body = None
        schedule_http_error_report(
            conversation_id=str(conversation_id) if conversation_id else None,
            status_code=406,
            method=request.method,
            path=request.url.path,
            detail="Request validation failed",
            extra_context={
                "validation_errors": _jsonable_validation_errors(exc),
                "request_body": _format_request_body(raw_body),
            },
        )
    except Exception:
        logger.exception("Failed to audit a validation error")

    response = await request_validation_exception_handler(request, exc)
    response.status_code = 406

    # Friendly message when the user message exceeds the allowed length, so the
    # frontend can show actionable text instead of a raw validation error.
    if _has_content_too_long_error(exc):
        return JSONResponse(
            status_code=406,
            content={
                "detail": _jsonable_validation_errors(exc),
                "message": (
                    "Tu mensaje es muy largo. Por favor, resúmelo e inténtalo de nuevo."
                ),
            },
        )

    return response


def _has_content_too_long_error(exc: RequestValidationError) -> bool:
    """Whether the validation failure is a too-long `content` field."""

    for error in exc.errors():
        loc = error.get("loc", ())
        if error.get("type") == "string_too_long" and loc and str(loc[-1]) == "content":
            return True
    return False


def _jsonable_validation_errors(exc: RequestValidationError) -> list[dict]:
    """Return validation errors as JSON-serializable dicts (drop non-serializable ctx)."""

    serializable_errors: list[dict] = []
    for error in exc.errors():
        serializable_errors.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return serializable_errors


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
        title="agentepqr API",
        version="0.1.0",
        description="Base API for health checks and chat message intake.",
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
    logger.info(
        "Registered CORS middleware allow_origins=%s allow_methods=%s allow_headers=%s allow_credentials=%s",
        cors_settings.allow_origins,
        cors_settings.allow_methods,
        cors_settings.allow_headers,
        cors_settings.allow_credentials,
    )
    app.add_exception_handler(RequestValidationError, log_request_validation_error)
    logger.info("Registered request validation handler")
    app.include_router(health_router)
    logger.info("Registered health router")
    app.include_router(chat_router)
    logger.info("Registered chat router")
    app.openapi = lambda: _custom_openapi(app)
    logger.info("Registered custom OpenAPI handler for 406 validation responses")
    return app


app = build_app()
