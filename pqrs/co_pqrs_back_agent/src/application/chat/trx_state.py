"""Estado secuencial del caso TXNR, persistido en `conversation.captured_data`.

`captured_data` ya se persiste por turno en el índice de conversaciones, así que
NO usamos memoria de proceso (seguro para múltiples usuarios en paralelo).
Todas las funciones son puras sobre el objeto conversación (duck-typed: requiere
`.captured_data` dict).
"""

from __future__ import annotations

from typing import Any

# _json en el nombre A PROPOSITO: la clave vieja "trx_case_state" quedo
# mapeada como OBJETO en los indices existentes (local y dev) por el bug del
# aplanado; reusar el nombre con un string provoca mapper_parsing_exception y
# tumba el guardado del turno entero. Clave nueva = mapping nuevo, sin chocar.
TRX_STATE_KEY = "trx_case_state_json"

# Campos que se reinician por-transacción dentro del bucle "una a la vez".
_PER_TX_FIELDS = (
    "producto",
    "fecha",
    "vigencia",
    "card_id",
    "movimiento",
    "movimientos",
    "detalle",
    "validaciones",
    "bloqueo",
)


def _serializar(data: Any, state: dict[str, Any]) -> None:
    """Guarda el estado como STRING JSON — la convención de captured_data.

    Un dict anidado NO sobrevive al viaje por OpenSearch: la capa de
    persistencia lo APLANA en claves con puntos escapados
    (``trx_case_state．subida_nivel．challenge``) y al recargar la clave
    original ya no existe -> el estado vuelve vacío. Con la ceremonia OOB
    eso perdía el challenge entre turnos y todo bloqueo caía a "denied"
    (bug cazado en el E2E local del 28/08). Todo valor complejo de
    captured_data viaja como JSON string (trx_products_result, etc.);
    este estado sigue la misma regla.
    """
    import json

    data[TRX_STATE_KEY] = json.dumps(state, ensure_ascii=False)


def get_trx_state(conversation: Any) -> dict[str, Any]:
    """Devuelve el estado TXNR (dict), creándolo vacío si no existe."""
    import json

    data = getattr(conversation, "captured_data", None)
    if data is None:
        return {}
    if TRX_STATE_KEY not in data:
        # siembra la clave (contrato histórico: leer crea el estado vacío)
        data[TRX_STATE_KEY] = "{}"
    state = data.get(TRX_STATE_KEY)
    if isinstance(state, str):
        try:
            parsed = json.loads(state)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    if isinstance(state, dict):
        # legado (pre-arreglo): dict en memoria dentro del mismo turno
        return state
    return {}


def update_trx_state(conversation: Any, **fields: Any) -> dict[str, Any]:
    """Actualiza (merge superficial) el estado TXNR y lo devuelve."""
    state = get_trx_state(conversation)
    for key, value in fields.items():
        state[key] = value
    _serializar(conversation.captured_data, state)
    return state


def reset_per_tx(conversation: Any) -> None:
    """Limpia los campos por-transacción para arrancar limpia la siguiente."""
    state = get_trx_state(conversation)
    for field in _PER_TX_FIELDS:
        state.pop(field, None)
    _serializar(conversation.captured_data, state)


def trx_snapshot(conversation: Any) -> dict[str, Any]:
    """Copia serializable del estado (para el registro durable / traza)."""
    return dict(get_trx_state(conversation))
