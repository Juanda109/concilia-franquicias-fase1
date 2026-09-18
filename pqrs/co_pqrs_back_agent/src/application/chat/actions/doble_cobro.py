"""
Actions del workflow Doble Cobro.

Estas acciones son SINCRONAS y solo PINTAN: consumen lo que el hook
(``application/chat/workflows/doble_cobro_hook.py``) ya dejo en
``captured_data``. Ninguna hace E/S ni decide el enrutamiento.
"""

from __future__ import annotations

import json
from typing import Any

from application.chat.actions.registry import register_action
from application.chat.actions.shared.product_selector import (
    ProductSelectorConfig,
    ProductSelectorResult,
    load_product_selector,
)
from domain.conversation.models import Conversation
from domain.workflow.doble_cobro.messages import load_doble_cobro_messages
from infrastructure.core.config import load_transactions_per_page
from infrastructure.core.logger import get_logger, log_execution

logger = get_logger(__name__)

_PRODUCT_STEP = "3.4.0.1"
_GROUPS_STEP = "3.4.0.6"

_TRANSACTIONS_KEY = "dc_transactions"
_TRANSACTIONS_SELECTED_KEY = "dc_transactions_selected"
_TRANSACTIONS_PAGE_KEY = "dc_transactions_page"

# Tamano de pagina del selector. UNICA definicion: el hook la importa de aqui
# en vez de mantener su propia copia. Se configura con TRANSACTIONS_PER_PAGE
# (.env en local, configmap en los demas entornos).
_TRANSACTIONS_PER_PAGE = load_transactions_per_page()
# Debe coincidir con _DC_MAX_TRANSACTIONS del hook: es el tope de
# movimientos que se le ofrecen al cliente en una misma consulta.
_MAX_TRANSACTIONS = 100

_GROUPS_WARNING_KEY = "dc_groups_warning"

# Las marcas y todos los textos del selector viven en messages.yml.
_MSG = load_doble_cobro_messages()
_SEL = _MSG.selector_transacciones

_PRODUCT_SELECTOR_CONFIG = ProductSelectorConfig(
    source_key="dc_products_result",
    products_map_key="doble_cobro_products_map",
    prompt_key=f"dynamic_prompt_{_PRODUCT_STEP}",
    option_labels_key=f"dynamic_option_labels_{_PRODUCT_STEP}",
    option_prefix="producto_",
    prompt=load_doble_cobro_messages().selector_productos.pregunta,
)


def _format_amount(value: Any) -> str:
    """Formato colombiano para cargos: $ -8.500,00."""

    try:
        amount = abs(float(value))
        formatted = (
            f"{amount:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        return f"$ -{formatted}"
    except (TypeError, ValueError):
        return str(value)


def _format_time(value: Any) -> str:
    """Formatea una hora ISO/HH:MM en formato de 12 horas."""

    text = str(value or "").strip()
    if not text:
        return ""

    # Si llega ISO: 2026-08-20T16:30:00
    if len(text) >= 16 and text[10] in {"T", " "}:
        text = text[11:16]

    if len(text) < 5 or text[2] != ":":
        return str(value or "").strip()

    try:
        hour = int(text[:2])
        minute = int(text[3:5])
    except ValueError:
        return str(value or "").strip()

    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {suffix}"


def _load_json(conversation: Conversation, key: str, default: Any) -> Any:
    raw = conversation.captured_data.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


@register_action("mostrar_productos_activos_dc")
@log_execution
def mostrar_productos_activos_dc(
    conversation: Conversation,
    **_: object,
) -> ProductSelectorResult:
    """Pinta los productos que el hook precargo desde :8006."""

    result = load_product_selector(
        conversation=conversation,
        config=_PRODUCT_SELECTOR_CONFIG,
    )

    logger.info(
        "DOBLE_COBRO PRODUCT SELECTOR conversation_id=%s success=%s products=%s reason=%s",
        conversation.conversation_id,
        result.success,
        len(result.products),
        result.reason,
    )
    return result


@register_action("mostrar_grupos_doble_cobro")
@log_execution
def mostrar_grupos_doble_cobro(
    conversation: Conversation,
    **_: object,
) -> int:
    """Pinta transacciones individuales con paginación y selección persistente."""

    transactions: list[dict[str, Any]] = _load_json(
        conversation,
        _TRANSACTIONS_KEY,
        [],
    )

    selected = set(
        _load_json(
            conversation,
            _TRANSACTIONS_SELECTED_KEY,
            [],
        )
    )

    try:
        page = int(
            conversation.captured_data.get(
                _TRANSACTIONS_PAGE_KEY
            )
            or 0
        )
    except (TypeError, ValueError):
        page = 0

    total = len(transactions)

    total_pages = max(
        1,
        (total + _TRANSACTIONS_PER_PAGE - 1)
        // _TRANSACTIONS_PER_PAGE,
    )

    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    start = page * _TRANSACTIONS_PER_PAGE
    end = min(
        start + _TRANSACTIONS_PER_PAGE,
        total,
    )

    visible = transactions[start:end]

    labels: list[str] = []
    keys: list[str] = []

    # ---------------------------------------------------------------
    # Transacciones
    # ---------------------------------------------------------------
    for transaction in visible:
        selection_id = str(
            transaction.get("selection_id")
            or ""
        )

        mark = (
            _SEL.marca_seleccionada
            if selection_id in selected
            else _SEL.marca_sin_seleccionar
        )

        merchant = str(
            transaction.get("merchant")
            or _SEL.sin_comercio
        )

        amount = _format_amount(
            transaction.get("amount")
        )

        last_four = str(
            transaction.get("last_four")
            or ""
        ).strip()

        time = _format_time(
            transaction.get("time")
        )

        detail_parts = []

        if last_four:
            detail_parts.append(
                f"•{last_four}"
            )

        if time:
            detail_parts.append(
                time
            )

        detail = " · ".join(detail_parts)

        plantilla = (
            _SEL.etiqueta if detail else _SEL.etiqueta_sin_detalle
        )

        labels.append(
            plantilla.format(
                marca=mark,
                comercio=merchant,
                monto=amount,
                detalle=detail,
            )
        )
        keys.append(selection_id)

    # ---------------------------------------------------------------
    # Navegación: solo se pinta el sentido que existe, para que el
    # cliente no vea un botón que no lleva a ninguna parte.
    # ---------------------------------------------------------------
    if page > 0:
        labels.append(_SEL.botones.pagina_anterior)
        keys.append("pagina_anterior")

    if end < total:
        labels.append(_SEL.botones.pagina_siguiente)
        keys.append("mas_movimientos")

    # ---------------------------------------------------------------
    # Acciones finales
    # ---------------------------------------------------------------
    # La ficha muestra el conteo en el propio boton ("Reportar 2 cobros") y lo
    # deja generico mientras no haya nada marcado, que es la senal que usa el
    # front para pintarlo inhabilitado.
    if selected:
        unidad = (
            _SEL.botones.unidad_singular
            if len(selected) == 1
            else _SEL.botones.unidad_plural
        )
        labels.append(
            _SEL.botones.reportar_contador.format(
                cantidad=len(selected),
                unidad=unidad,
            )
        )
    else:
        labels.append(_SEL.botones.reportar)

    keys.append("reportar_seleccionados")

    labels.append(_SEL.botones.no_encuentro)
    keys.append("no_encuentro")

    conversation.captured_data[
        f"dynamic_option_labels_{_GROUPS_STEP}"
    ] = json.dumps(
        labels,
        ensure_ascii=False,
    )

    conversation.captured_data[
        f"dynamic_option_keys_{_GROUPS_STEP}"
    ] = json.dumps(
        keys,
        ensure_ascii=False,
    )

    # ---------------------------------------------------------------
    # Prompt
    # ---------------------------------------------------------------
    transaction_date = str(
        conversation.flow_answers.get(
            "doble_cobro_fecha"
        )
        or ""
    )

    prompt = _SEL.pregunta

    warning = conversation.captured_data.pop(_GROUPS_WARNING_KEY, None)
    if warning:
        prompt = f"{warning}\n\n{prompt}"

    if total > _TRANSACTIONS_PER_PAGE:
        prompt += "\n\n" + _SEL.paginacion.format(
            desde=start + 1,
            hasta=end,
            total=total,
            pagina=page + 1,
            paginas=total_pages,
        )

    if transaction_date:
        prompt += "\n\n" + _SEL.fecha.format(fecha=transaction_date)

    prompt += "\n\n" + _SEL.seleccionadas.format(cantidad=len(selected))

    if total >= _MAX_TRANSACTIONS:
        prompt += "\n\n" + _SEL.tope_alcanzado.format(tope=_MAX_TRANSACTIONS)

    conversation.captured_data[
        f"dynamic_prompt_{_GROUPS_STEP}"
    ] = prompt

    logger.info(
        "DOBLE_COBRO TRANSACTION SELECTOR "
        "conversation_id=%s page=%s/%s "
        "visible=%s total=%s selected=%s",
        conversation.conversation_id,
        page + 1,
        total_pages,
        len(visible),
        total,
        len(selected),
    )

    return len(visible)
