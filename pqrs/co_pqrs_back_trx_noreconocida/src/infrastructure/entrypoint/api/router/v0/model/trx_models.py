"""Request/response models for the trx_no_reconocida v0 endpoints (MOCK)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.trx.models import EventoTrx


class TrxRequest(BaseModel):
    """Common request payload for the mock endpoints."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(description="Identificador del cliente.")
    evento: EventoTrx | None = Field(
        default=None, description="Suceso confirmado (una de las 4 opciones)."
    )
    descripcion: str | None = Field(
        default=None, description="Texto libre del cliente."
    )
    product_id: str | None = Field(
        default=None,
        description="Identificador del producto elegido para consultar transacciones.",
    )


class TrxResponse(BaseModel):
    """Mock response envelope."""

    model_config = ConfigDict(extra="forbid")

    status: str
    id_message: int | None = None
    step: str
    detail: str
    data: dict = Field(default_factory=dict)
