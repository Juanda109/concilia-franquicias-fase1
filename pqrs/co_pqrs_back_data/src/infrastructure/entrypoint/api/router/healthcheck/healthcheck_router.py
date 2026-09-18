"""Health check routes."""

from fastapi import APIRouter, status

from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.router.healthcheck.model.response_model import (
    HealthcheckResponse,
)

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Health check",
    response_model=HealthcheckResponse,
)
@log_execution
async def health_check() -> HealthcheckResponse:
    """Return the API availability status."""

    logger.info("Health check requested")
    return HealthcheckResponse(status="ok")

