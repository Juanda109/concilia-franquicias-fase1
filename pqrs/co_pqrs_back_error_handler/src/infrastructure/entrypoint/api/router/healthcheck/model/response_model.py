"""Healthcheck response model."""

from pydantic import BaseModel


class HealthcheckResponse(BaseModel):
    """Simple health response."""

    status: str
