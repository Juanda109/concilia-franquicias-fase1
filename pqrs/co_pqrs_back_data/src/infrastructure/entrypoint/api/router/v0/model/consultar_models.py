"""Request and response models for customer data routes."""

from typing import Any

from pydantic import BaseModel


class ConsultarResponse(BaseModel):
    data: dict[str, Any]
