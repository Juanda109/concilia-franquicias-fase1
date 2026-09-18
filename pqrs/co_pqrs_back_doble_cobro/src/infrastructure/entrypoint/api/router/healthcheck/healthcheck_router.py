"""Health check route."""

from fastapi import APIRouter, status
from pydantic import BaseModel

from infrastructure.core.logger import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


class HealthcheckResponse(BaseModel):
    status: str


@router.get("", status_code=status.HTTP_200_OK, summary="Health check")
async def health_check() -> HealthcheckResponse:
    """Return the API availability status."""

    logger.info("Health check requested")
    return HealthcheckResponse(status="ok")
