"""Detección de grupos de cobros duplicados sobre los movimientos del día.

Se aplican dos criterios distintos, a propósito:

* Al BUSCAR se admite un margen (``amount_tolerance``) alrededor del monto que
  escribió el cliente, porque rara vez lo recuerda al peso exacto.
* Al AGRUPAR se exige monto idéntico, mismo comercio y la misma fecha. Un cobro
  duplicado real es el mismo importe cobrado dos veces el mismo día; cualquier
  margen en el monto produciría falsos positivos sobre compras distintas del
  mismo comercio.

La hora NO interviene en el criterio: dos cargos iguales del mismo comercio en
la misma fecha se consideran duplicados aunque estén separados por horas, porque
el comercio puede reprocesar el cobro mucho después del intento original.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

DEFAULT_AMOUNT_TOLERANCE = 2000.0
MIN_GROUP_SIZE = 2

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")


def normalize_merchant(value: Any) -> str:
    """Clave comparable del comercio: sin tildes, mayúsculas y sin puntuación.

    El ASO devuelve el mismo comercio con espaciado y acentos inconsistentes
    entre operaciones, así que comparar el texto crudo parte grupos legítimos.
    """

    text = str(value or "").strip().upper()
    if not text:
        return ""

    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALPHANUMERIC.sub(" ", ascii_text).strip()


def filter_by_amount(
    movements: list[dict[str, Any]],
    *,
    target_amount: float,
    tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
) -> list[dict[str, Any]]:
    """Movimientos cuyo importe cae dentro de ``tolerance`` del monto buscado."""

    result: list[dict[str, Any]] = []
    for movement in movements:
        amount = movement.get("amount")
        if amount is None:
            continue
        if abs(float(amount) - target_amount) <= tolerance:
            result.append(movement)
    return result


def _group_key(movement: dict[str, Any]) -> tuple[str, float, str] | None:
    """Comercio normalizado + importe exacto + fecha. None si falta alguno."""

    merchant = normalize_merchant(movement.get("merchant"))
    amount = movement.get("amount")
    day = str(movement.get("date") or "").strip()

    if not merchant or amount is None or not day:
        return None

    return merchant, round(float(amount), 2), day


def _sort_key(movement: dict[str, Any]) -> str:
    """Ordena por hora cuando existe; los movimientos sin hora quedan al final."""

    timestamp = movement.get("timestamp")
    return timestamp.isoformat() if timestamp is not None else "~"


def find_duplicate_groups(
    movements: list[dict[str, Any]],
    *,
    min_group_size: int = MIN_GROUP_SIZE,
) -> list[dict[str, Any]]:
    """Agrupa los movimientos que parecen el mismo cobro repetido.

    Un grupo exige mismo comercio, mismo importe y misma fecha. Los movimientos
    sin fecha se descartan: son la única pieza que el criterio no puede suponer.
    La hora es opcional; solo se usa para ordenar y para mostrarle al cliente
    cuándo ocurrieron los cargos.
    """

    buckets: dict[tuple[str, float, str], list[dict[str, Any]]] = {}

    for movement in movements:
        key = _group_key(movement)
        if key is not None:
            buckets.setdefault(key, []).append(movement)

    groups: list[dict[str, Any]] = []
    for (merchant, amount, day), bucket in buckets.items():
        if len(bucket) < min_group_size:
            continue

        bucket.sort(key=_sort_key)
        times = [
            movement["timestamp"].isoformat()
            for movement in bucket
            if movement.get("timestamp") is not None
        ]

        groups.append(
            {
                "group_id": "",
                "merchant": bucket[0].get("merchant") or merchant,
                "amount": amount,
                "date": day,
                "count": len(bucket),
                "total_amount": round(amount * len(bucket), 2),
                "first_seen": times[0] if times else "",
                "last_seen": times[-1] if times else "",
                "movement_ids": [str(item.get("id") or "") for item in bucket],
                "movements": bucket,
            }
        )

    # Primero los grupos más recientes: es lo que el cliente tiene fresco.
    groups.sort(key=lambda group: group["first_seen"], reverse=True)
    for position, group in enumerate(groups, start=1):
        group["group_id"] = f"grupo_{position}"
    return groups
