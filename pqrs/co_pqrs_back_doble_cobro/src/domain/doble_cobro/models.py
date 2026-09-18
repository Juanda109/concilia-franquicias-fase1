"""Domain models for the duplicate-charge (doble_cobro) path."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DobleCobroResult(BaseModel):
    """Generic response envelope used by the doble_cobro service endpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "not_found", "unavailable", "mock", "error"]
    step: str = Field(description="Etapa lógica que este endpoint representa.")
    detail: str | None = Field(default=None, description="Mensaje legible para logs/UI.")
    data: dict[str, Any] = Field(default_factory=dict)


class ValidityRequest(BaseModel):
    """Entrada de la validación de vigencia de la fecha reportada."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    transaction_date: str = Field(description="Fecha reportada (DD/MM/AAAA o AAAA-MM-DD).")
    product_type: str = Field(
        default="ACCOUNT",
        description="ACCOUNT o CARD: define la ventana de conciliación aplicable.",
    )
    card_brand: str = Field(
        default="",
        description="VISA o MASTER. Vacío cuando el producto es una cuenta.",
    )


class DuplicateSearchRequest(BaseModel):
    """Entrada de la búsqueda de grupos de cobros duplicados."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str
    transaction_date: str = Field(description="Fecha reportada (DD/MM/AAAA o AAAA-MM-DD).")
    amount: float = Field(gt=0, description="Monto que indicó el cliente.")
    card_id: str = Field(default="", description="PAN cuando el producto es tarjeta.")
    account_id: str = Field(default="", description="Contrato cuando es cuenta.")
