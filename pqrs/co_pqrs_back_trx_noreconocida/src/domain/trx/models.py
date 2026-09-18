"""Domain models for the unrecognized-transaction (trx_no_reconocida) path."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The 4 events the agent asks the customer to confirm before analysis.
EventoTrx = Literal[
    "cambiazo",
    "hurto_o_perdida",
    "ingenieria_social",
    "compra_presencial_o_internet",
]


class TrxCase(BaseModel):
    """Input describing a customer's unrecognized-transaction case."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(description="Identificador del cliente.")
    evento: EventoTrx | None = Field(
        default=None,
        description="Suceso confirmado por el cliente (una de las 4 opciones).",
    )
    descripcion: str | None = Field(
        default=None,
        description="Texto libre del cliente sobre la transacción no reconocida.",
    )
    product_id: str | None = Field(
        default=None,
        description="Identificador del producto elegido para revisar transacciones.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Contexto técnico adicional para reglas y mocks internos.",
    )


class TrxResult(BaseModel):
    """Generic response envelope used by the trx service endpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "ok",
        "not_found",
        "unavailable",
        "mock",
        "error",
        "REDIRECT_PQR",
        "APPROVED",
    ]
    id_message: int | None = Field(
        default=None,
        description="Identificador funcional del mensaje del flujo (>= 200).",
    )
    step: str = Field(description="Etapa lógica que este endpoint representará.")
    detail: str = Field(description="Mensaje explicativo del mock / TODO.")
    data: dict = Field(default_factory=dict, description="Datos simulados (vacío por ahora).")
