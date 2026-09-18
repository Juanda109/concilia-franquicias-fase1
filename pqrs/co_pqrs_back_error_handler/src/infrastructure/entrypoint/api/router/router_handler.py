"""Compose the API routers."""

from fastapi import APIRouter

from infrastructure.entrypoint.api.router.healthcheck.healthcheck_router import (
    router as healthcheck_router,
)
from infrastructure.entrypoint.api.router.v0.error_report_router import (
    router as error_report_router,
)
from infrastructure.entrypoint.api.router.v0.request_log_router import (
    router as request_log_router,
)
from infrastructure.entrypoint.api.router.v0.trace_event_router import (
    router as trace_event_router,
)

router = APIRouter()
router.include_router(healthcheck_router)
router.include_router(error_report_router)
router.include_router(trace_event_router)
router.include_router(request_log_router)
