"""
Selector dinámico de productos reutilizable.

No contiene reglas de negocio de TXNR ni Doble Cobro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from domain.conversation.models import Conversation
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProductSelectorConfig:
    """
    Configuración del selector.

    El selector no conoce el workflow.
    """

    source_key: str
    products_map_key: str
    prompt_key: str
    option_labels_key: str
    option_prefix: str = "producto_"
    prompt: str = (
        "Selecciona el producto donde tienes la novedad:"
    )


@dataclass(frozen=True)
class ProductSelectorResult:
    success: bool
    products: list[dict[str, Any]]
    reason: str | None = None


def _safe_string(value: Any) -> str:
    return str(value or "").strip()


def _last_four(value: Any) -> str:
    normalized = _safe_string(value)

    if not normalized:
        return ""

    return normalized[-4:]


def normalize_financial_products(
    payload: Any,
) -> list[dict[str, Any]]:
    """
    Normaliza:

        {
            "data": {
                "products": [...]
            }
        }

    a la estructura común del selector.
    """

    if not isinstance(payload, dict):
        return []

    data = payload.get("data") or {}

    if not isinstance(data, dict):
        return []

    products = data.get("products") or []

    if not isinstance(products, list):
        return []

    normalized: list[dict[str, Any]] = []

    for entry in products:

        if not isinstance(entry, dict):
            continue

        product_id = _safe_string(
            entry.get("product_id")
            or entry.get("key_id")
            or entry.get("card_id")
            or entry.get("contract_id")
        )

        if not product_id:
            continue

        key_id = _safe_string(
            entry.get("key_id")
            or product_id
        )

        contract_id = _safe_string(
            entry.get("contract_id")
            or entry.get("card_id")
            or product_id
        )

        last_four = _safe_string(
            entry.get("last_four")
            or entry.get("last_four_pan_id")
        )

        last_four_pan_id = _safe_string(
            entry.get("last_four_pan_id")
            or entry.get("last_four")
        )

        commercial_product_desc = (
            _safe_string(
                entry.get(
                    "commercial_product_desc"
                )
                or entry.get(
                    "product_desc"
                )
            )
            or "Producto financiero"
        )

        account_status_type_desc = _safe_string(
            entry.get(
                "account_status_type_desc"
            )
        )

        normalized.append(
            {
                "product_id": product_id,
                "key_id": key_id,
                "contract_id": contract_id,
                # PAN de la tarjeta, tal cual. Se propaga aparte de
                # `contract_id` (que lo absorbe como respaldo) porque quien
                # consulta movimientos de tarjeta necesita el PAN y no puede
                # distinguirlo de un numero de contrato de cuenta.
                "card_id": _safe_string(entry.get("card_id")),
                "last_four": last_four,
                "last_four_pan_id": last_four_pan_id,
                "commercial_product_desc": (
                    commercial_product_desc
                ),
                "account_status_type_desc": (
                    account_status_type_desc
                ),
                "product_type": _safe_string(
                    entry.get("product_type")
                ),
                "sub_product_type": _safe_string(
                    entry.get("sub_product_type")
                ),
                "card_brand": _safe_string(
                    entry.get("card_brand")
                ),
                "currency": _safe_string(
                    entry.get("currency")
                ),
            }
        )

    return normalized


def build_product_selection_prompt(
    products: list[dict[str, Any]],
    prompt: str,
) -> str:
    """
    El prompt lo define el workflow.

    `products` se mantiene como argumento para conservar
    una interfaz genérica y facilitar futuras variantes.
    """

    _ = products

    return _safe_string(prompt) or (
        "Selecciona el producto donde tienes la novedad:"
    )


def build_product_option_labels(
    products: list[dict[str, Any]],
) -> list[str]:

    labels: list[str] = []

    for product in products:

        product_type = (
            _safe_string(
                product.get(
                    "commercial_product_desc"
                )
                or product.get(
                    "product_desc"
                )
            )
            or "Producto financiero"
        )

        last_four = _last_four(
            product.get("last_four")
            or product.get(
                "last_four_pan_id"
            )
        )

        if last_four:
            labels.append(
                f"{product_type} •{last_four}"
            )
        else:
            labels.append(
                product_type
            )

    return labels


def resolve_selected_product(
    products: list[dict[str, Any]],
    selected_key: str | None,
    option_prefix: str = "producto_",
) -> dict[str, Any] | None:

    selected = _safe_string(
        selected_key
    )

    if not selected:
        return None

    if not selected.startswith(
        option_prefix
    ):
        return None

    suffix = selected[
        len(option_prefix):
    ]

    try:
        position = int(suffix) - 1
    except (
        TypeError,
        ValueError,
    ):
        return None

    if position < 0:
        return None

    if position >= len(products):
        return None

    return products[position]


def load_product_selector(
    conversation: Conversation,
    config: ProductSelectorConfig,
) -> ProductSelectorResult:
    """
    Consume los productos previamente cargados.

    NO hace HTTP.
    NO consulta ASO.
    NO conoce workflows.
    """

    raw_products = (
        conversation.captured_data.get(
            config.source_key
        )
    )

    if not raw_products:

        logger.warning(
            "PRODUCT SELECTOR SOURCE MISSING "
            "conversation_id=%s "
            "source_key=%s",
            conversation.conversation_id,
            config.source_key,
        )

        return ProductSelectorResult(
            success=False,
            products=[],
            reason="SOURCE_DATA_MISSING",
        )

    try:

        if isinstance(
            raw_products,
            str,
        ):
            payload = json.loads(
                raw_products
            )

        elif isinstance(
            raw_products,
            dict,
        ):
            payload = raw_products

        else:
            return ProductSelectorResult(
                success=False,
                products=[],
                reason=(
                    "SOURCE_DATA_INVALID_TYPE"
                ),
            )

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):

        return ProductSelectorResult(
            success=False,
            products=[],
            reason=(
                "SOURCE_DATA_INVALID_JSON"
            ),
        )

    products = normalize_financial_products(
        payload
    )

    if not products:

        return ProductSelectorResult(
            success=False,
            products=[],
            reason="NO_PRODUCTS",
        )

    conversation.captured_data[
        config.products_map_key
    ] = json.dumps(
        products,
        ensure_ascii=False,
    )

    conversation.captured_data[
        config.prompt_key
    ] = build_product_selection_prompt(
        products,
        config.prompt,
    )

    conversation.captured_data[
        config.option_labels_key
    ] = json.dumps(
        build_product_option_labels(
            products
        ),
        ensure_ascii=False,
    )

    return ProductSelectorResult(
        success=True,
        products=products,
    )