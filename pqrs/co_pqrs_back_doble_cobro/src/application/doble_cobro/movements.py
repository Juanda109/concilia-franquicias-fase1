"""Traducción de ``/cards/v2/operations`` al movimiento que consume el flujo.

Equivale a ``aso_rules.parse_movimientos_operations`` de
``co_pqrs_back_trx_noreconocida``, pero devuelve ``merchant``/``amount``/
``timestamp`` porque el detector de duplicados necesita marca de tiempo. Se
mantiene una copia propia en vez de importar del otro servicio: cada
``co_pqrs_back_*`` es un proyecto ``uv`` independiente y este contrato va a
evolucionar por su cuenta.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# El nombre del comercio viaja en el 5.º bloque de ``observations`` en el ASO
# real; ``descProvision`` allí trae un estado ("ACEPTADA"), no un comercio.
_MERCHANT_OBSERVATION_BLOCK = 4
_MIN_OBSERVATION_BLOCKS = 5


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_amount(operation: dict[str, Any]) -> float | None:
    raw = (operation.get("amountOperation") or {}).get("amount")
    try:
        return abs(float(str(raw).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _parse_timestamp(operation: dict[str, Any]) -> datetime | None:
    """Combina ``dateOper`` (AAAA-MM-DD) con ``hourOperation`` (HHMMSS)."""

    day = _text(operation.get("dateOper") or operation.get("operationDate"))[:10]
    if not day:
        return None

    hour = "".join(ch for ch in _text(operation.get("hourOperation")) if ch.isdigit())
    hour = hour[:6].ljust(6, "0")

    try:
        return datetime.strptime(f"{day} {hour}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None


def _parse_merchant(operation: dict[str, Any]) -> str:
    blocks = _text(operation.get("observations")).split("|")
    if len(blocks) >= _MIN_OBSERVATION_BLOCKS:
        merchant = blocks[_MERCHANT_OBSERVATION_BLOCK].strip()
        if merchant:
            return merchant

    return (
        _text(operation.get("descProvision"))
        or _text(operation.get("placeOperation"))
        or _text(operation.get("concept"))
        or "Sin descripción"
    )


def parse_operations(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Aplana la respuesta del ASO a una lista de movimientos normalizados."""

    movements: list[dict[str, Any]] = []

    for block in (payload or {}).get("data") or []:
        if not isinstance(block, dict):
            continue

        for operation in block.get("operations") or []:
            if not isinstance(operation, dict):
                continue

            timestamp = _parse_timestamp(operation)
            movements.append(
                {
                    "id": _text(operation.get("id")),
                    "merchant": _parse_merchant(operation),
                    "amount": _parse_amount(operation),
                    "timestamp": timestamp,
                    "date": timestamp.date().isoformat() if timestamp else "",
                    "time": timestamp.strftime("%H:%M") if timestamp else "",
                    "currency": _text(
                        (operation.get("amountOperation") or {}).get("currency")
                    ),
                    "place": _text(operation.get("placeOperation")),
                    "status": _text(
                        operation.get("responseOperati")
                        or operation.get("observation_desc")
                    ),
                    # Operación ENTERA tal como la devolvió el ASO. El registro
                    # del caso la guarda sin tocar, igual que transacción no
                    # reconocida, para que el job de exportación pueda leer de
                    # ella los campos que el CSV de Tantia exige (número de
                    # extracto, número de operación, intereses...). Aplanarla
                    # aquí dejaría esas columnas vacías.
                    "raw": operation,
                }
            )

    return movements
