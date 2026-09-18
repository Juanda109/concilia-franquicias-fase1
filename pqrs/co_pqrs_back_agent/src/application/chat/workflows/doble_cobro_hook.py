"""Prefetch y gates del workflow Doble Cobro.

El hook se registra por WORKFLOW y despacha internamente por el NOMBRE DE LA
ACCION declarada en el YAML, no por el id del paso: renumerar el arbol no puede
volver a desincronizar la logica de Python.

Reparto de responsabilidades del flujo:

* Este hook (async) hace la E/S contra :8006 y reescribe ``current_step``.
* Las acciones del registro (sync, ``application/chat/actions/doble_cobro.py``)
  solo pintan lo que el hook ya dejo en ``captured_data``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from application.chat.actions.doble_cobro import _TRANSACTIONS_PER_PAGE
from application.chat.actions.shared.product_selector import resolve_selected_product
from application.chat.workflow_hooks import register_prefetch_hook
from domain.conversation.models import Conversation
from domain.workflow.doble_cobro.messages import load_doble_cobro_messages
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.doble_cobro_client import DobleCobroClient
from infrastructure.persistence.trx_case_store import (
    NOTIFICATION_DOBLE_COBRO,
    TrxCaseStore,
)

logger = get_logger(__name__)

# Textos de cara al cliente: viven en doble_cobro/messages.yml.
_MSG = load_doble_cobro_messages()

_WORKFLOW = "doble_cobro"
_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[3]
    / "domain"
    / "workflow"
    / "doble_cobro"
    / "doble_cobro.yml"
)

# Numero maximo de gates encadenados que se resuelven en un mismo turno. Los
# gates se reescriben unos a otros (registro -> estado), y este tope evita un
# bucle si un YAML mal formado los encadena en circulo.
_MAX_GATE_HOPS = 5

_WORKFLOW = "doble_cobro"

_MAX_GATE_HOPS = 5

_MILESTONE_REPORTED = "reported"
_OUTCOME_REPORTED = "reported"

_ORIGIN_CARD = "card"
_ORIGIN_ACCOUNT = "account"

# Máximo de transacciones que se muestran por página.

# Tope defensivo.
_DC_MAX_TRANSACTIONS = 100

# Un cobro duplicado necesita al menos dos cargos iguales: uno solo no
# prueba nada.
_MIN_DUPLICATES = 2

# Claves en captured_data.
_PRODUCTS_KEY = "dc_products_result"
_PRODUCTS_MAP_KEY = "doble_cobro_products_map"

_MOVEMENTS_KEY = "dc_movements"
_GROUPS_WARNING_KEY = "dc_groups_warning"
# Aviso de los cargos marcados que NO se reportan por no formar pareja.
_DISCARDED_WARNING_KEY = "dc_discarded_warning"

_TRANSACTIONS_KEY = "dc_transactions"
_TRANSACTIONS_SELECTED_KEY = "dc_transactions_selected"
_TRANSACTIONS_PAGE_KEY = "dc_transactions_page"
_GROUPS_QUERY_SIGNATURE_KEY = "dc_groups_query_signature"

_CASE_ITEMS_KEY = "dc_case_items"

# Claves en flow_answers.
_ANSWER_FAMILY = "doble_cobro_familia"
_ANSWER_PRODUCT = "doble_cobro_producto"
_ANSWER_DATE = "doble_cobro_fecha"
_ANSWER_AMOUNT = "doble_cobro_monto"
_ANSWER_TRANSACTION = "doble_cobro_trx_seleccion"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _load_json(conversation: Conversation, key: str, default: Any) -> Any:
    raw = conversation.captured_data.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "DOBLE_COBRO captured_data ilegible conversation_id=%s key=%s",
            conversation.conversation_id,
            key,
        )
        return default


def _store_json(conversation: Conversation, key: str, value: Any) -> None:
    conversation.captured_data[key] = json.dumps(value, ensure_ascii=False)


def _parse_amount(value: Any) -> float:
    """Monto que escribio el cliente, tolerante al formato colombiano.

    El YAML pide "solo numeros", pero el cliente escribe "$50.000" igual:
    un punto o coma seguido de grupos de exactamente 3 digitos es separador
    de miles ("50.000" -> 50000), no decimal. Con el filtro ingenuo anterior
    "50.000" se convertia en 50.0 y la busqueda de grupos por monto fallaba
    en silencio hacia el formulario.
    """

    text = re.sub(r"[^0-9.,]", "", str(value or ""))
    if not text:
        return 0.0

    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        text = re.sub(r"[.,]", "", text)
    else:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def _selected_product(conversation: Conversation) -> dict[str, Any]:
    """Producto que el cliente eligio en 3.4.0.1, ya normalizado."""

    products = _load_json(conversation, _PRODUCTS_MAP_KEY, [])
    selected = conversation.flow_answers.get(_ANSWER_PRODUCT)
    return resolve_selected_product(products, selected) or {}


def _groups_query_signature(
    conversation: Conversation,
) -> str:
    """Identifica la búsqueda actual de Doble Cobro."""

    product = _selected_product(conversation)

    product_id = str(
        product.get("card_id")
        or product.get("contract_id")
        or ""
    ).strip()

    transaction_date = str(
        conversation.flow_answers.get(_ANSWER_DATE) or ""
    ).strip()

    amount = _parse_amount(
        conversation.flow_answers.get(_ANSWER_AMOUNT)
    )

    return f"{product_id}|{transaction_date}|{amount:.2f}"

# ---------------------------------------------------------------------------
# Hook principal
# ---------------------------------------------------------------------------


@register_prefetch_hook(_WORKFLOW)
@log_execution
async def prefetch_doble_cobro(conversation: Conversation, **_: object) -> None:
    """Resuelve la accion del paso actual y encadena los gates que resulten."""

    if (conversation.workflow or "") != _WORKFLOW:
        return

    client = DobleCobroClient()

    for _ in range(_MAX_GATE_HOPS):
        step = conversation.current_step
        action = _STEP_ACTIONS.get(step)

        if action is None:
            logger.debug(
                "DOBLE_COBRO sin acción técnica step=%s conversation_id=%s",
                step,
                conversation.conversation_id,
            )
            return

        logger.info(
            "DOBLE_COBRO PREFETCH conversation_id=%s step=%s action=%s",
            conversation.conversation_id,
            step,
            action,
        )

        handler = _ACTION_HANDLERS[action]
        await handler(conversation, client)

        # Si el gate no movio el paso, no hay nada mas que encadenar.
        if conversation.current_step == step:
            return

    logger.error(
        "DOBLE_COBRO gates encadenados sin converger conversation_id=%s step=%s",
        conversation.conversation_id,
        conversation.current_step,
    )


# ---------------------------------------------------------------------------
# 3.4.0.1 - Productos activos
# ---------------------------------------------------------------------------


async def _prefetch_products(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Carga los productos de la familia elegida; sin productos, va a PQR."""

    customer_id = str(conversation.user_id or "").strip()
    family = str(conversation.flow_answers.get(_ANSWER_FAMILY) or "").strip()

    response = (
        await client.consultar_productos(customer_id=customer_id, family=family)
        if customer_id
        else None
    )

    products = ((response or {}).get("data") or {}).get("products") or []

    logger.info(
        "DOBLE_COBRO PRODUCTS conversation_id=%s family=%s products=%s",
        conversation.conversation_id,
        family,
        len(products),
    )

    if not products:
        logger.error(
            "DOBLE_COBRO PRODUCTS sin resultados conversation_id=%s family=%s",
            conversation.conversation_id,
            family,
        )
        conversation.current_step = "3.4.0.1.pqr"
        return

    _store_json(conversation, _PRODUCTS_KEY, response)


# ---------------------------------------------------------------------------
# 3.4.0.3 - Vigencia de la fecha
# ---------------------------------------------------------------------------


async def _validate_validity(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Días hábiles de conciliación, plazo de 6 meses y vigencia de franquicia."""

    product = _selected_product(conversation)
    transaction_date = str(conversation.flow_answers.get(_ANSWER_DATE) or "").strip()

    response = await client.validar_vigencia(
        transaction_date=transaction_date,
        product_type=str(product.get("product_type") or "ACCOUNT"),
        card_brand=str(product.get("card_brand") or ""),
    )

    data = (response or {}).get("data") or {}
    outcome = str(data.get("outcome") or "")

    logger.info(
        "DOBLE_COBRO VALIDITY conversation_id=%s date=%s outcome=%s",
        conversation.conversation_id,
        transaction_date,
        outcome,
    )

    if outcome == "settlement_pending":
        # El plazo depende del producto, asi que el texto se inyecta aqui.
        days = data.get("settlement_days")
        conversation.captured_data["dynamic_prompt_3.4.0.3.pendiente"] = (
            _MSG.vigencia.en_conciliacion.format(dias_habiles=days)
        )
        conversation.current_step = "3.4.0.3.pendiente"
        return

    if outcome in {"report_window_expired", "franchise_expired"}:
        conversation.current_step = "3.4.0.3.pqr"
        return

    if outcome != "ok":
        # Fecha ilegible o servicio caido: se revisa a fondo en vez de seguir
        # con un dato que no se pudo validar.
        logger.error(
            "DOBLE_COBRO VALIDITY sin resultado conversation_id=%s outcome=%s",
            conversation.conversation_id,
            outcome or "sin_respuesta",
        )
        conversation.current_step = "3.4.0.3.pqr"
        return

    conversation.current_step = "3.4.0.4"


# ---------------------------------------------------------------------------
# Registro del caso en OpenSearch
# ---------------------------------------------------------------------------
#
# El caso vive en el MISMO índice durable que transacción no reconocida y con la
# misma forma (`trx_case_state_snapshot.tantia_items`), para que el job de
# exportación a Tantia lo lea sin distinguir de qué flujo viene. Lo único que
# los separa es `tipo_de_notificacion`, que además prefija el id del documento
# para que los dos flujos no se pisen la ficha del mismo cliente.


def _case_store() -> TrxCaseStore:
    return TrxCaseStore()


async def _load_reported_items(conversation: Conversation) -> list[dict[str, Any]]:
    """Transacciones que este cliente ya reportó por doble cobro."""

    try:
        record = await _case_store().get_case(
            str(conversation.user_id or "").strip(),
            tipo_de_notificacion=NOTIFICATION_DOBLE_COBRO,
        )
    except Exception:
        # Fail-open: sin lectura no se bloquea el flujo, solo se pierde la
        # detección de recurrencia.
        logger.exception(
            "DOBLE_COBRO no se pudo leer el caso conversation_id=%s",
            conversation.conversation_id,
        )
        return []

    snapshot = (record or {}).get("trx_case_state_snapshot") or {}
    items = snapshot.get("tantia_items")
    return items if isinstance(items, list) else []


def _matches_reported(
    item: dict[str, Any],
    *,
    product_id: str,
    transaction_date: str,
    amount: float,
) -> bool:
    """¿Este ítem guardado es la misma transacción que el cliente reporta ahora?"""

    mismo_producto = product_id and product_id in {
        str(item.get("numero_tarjeta") or ""),
        str(item.get("contrato") or ""),
    }
    if not mismo_producto:
        return False

    if str(item.get("fecha_trx") or "") != transaction_date:
        return False

    try:
        return abs(float(item.get("movimiento_valor") or 0) - amount) < 0.01
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# 3.4.0.5 - Recurrencia
# ---------------------------------------------------------------------------


async def _validate_recurrence(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Busca un reporte previo, pero no bloquea un nuevo reporte."""

    del client

    product = _selected_product(conversation)

    product_id = str(
        product.get("card_id")
        or product.get("contract_id")
        or ""
    ).strip()

    transaction_date = str(
        conversation.flow_answers.get(_ANSWER_DATE) or ""
    ).strip()

    amount = _parse_amount(
        conversation.flow_answers.get(_ANSWER_AMOUNT)
    )

    previos = [
        item
        for item in await _load_reported_items(conversation)
        if _matches_reported(
            item,
            product_id=product_id,
            transaction_date=transaction_date,
            amount=amount,
        )
    ]

    logger.info(
        "DOBLE_COBRO RECURRENCE conversation_id=%s "
        "product_id=%s transaction_date=%s amount=%s "
        "previous_reports=%s action=continue",
        conversation.conversation_id,
        product_id,
        transaction_date,
        amount,
        len(previos),
    )

    conversation.current_step = "3.4.0.6"


# ---------------------------------------------------------------------------
# 3.4.0.6 - Grupos de cobros duplicados
# ---------------------------------------------------------------------------
def _build_transactions(
    conversation: Conversation,
    movements: list[dict[str, Any]],
    *,
    product: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convierte en seleccionables TODOS los movimientos del rango.

    No se recorta nada: el cliente ve cada movimiento cuyo importe cae dentro
    del rango del monto que indicó, y marca cuáles forman el cobro duplicado.
    Antes solo se ofrecían los cargos sobrantes de los grupos que el servicio
    detectaba, así que el más antiguo de cada pareja quedaba oculto y el
    cliente no podía escoger la pareja: se la dábamos hecha.
    """

    last_four = str(product.get("last_four") or "").strip()
    fecha = str(conversation.flow_answers.get(_ANSWER_DATE) or "")

    transactions: list[dict[str, Any]] = []

    for movement in movements[:_DC_MAX_TRANSACTIONS]:
        transactions.append(
            {
                "selection_id": f"transaccion_{len(transactions) + 1}",
                "movement_id": str(movement.get("id") or "").strip(),
                "merchant": str(movement.get("merchant") or "").strip(),
                "amount": movement.get("amount"),
                "date": fecha,
                "time": str(movement.get("time") or "").strip(),
                "last_four": last_four,
                # Operación cruda del ASO: el registro del caso la guarda tal
                # cual para que el CSV de Tantia pueda leer sus campos.
                "raw": movement.get("raw") or {},
            }
        )

    if len(movements) > _DC_MAX_TRANSACTIONS:
        logger.warning(
            "DOBLE_COBRO transacciones truncadas conversation_id=%s total=%s max=%s",
            conversation.conversation_id,
            len(movements),
            _DC_MAX_TRANSACTIONS,
        )

    return transactions


def normalize_merchant(value: Any) -> str:
    """Comercio comparable: sin tildes, en mayusculas y sin puntuacion.

    Replica la normalizacion del servicio porque el ASO devuelve el mismo
    comercio con acentos y espaciado inconsistentes entre operaciones, y
    compararlo crudo partiria en dos una pareja legitima.
    """

    texto = str(value or "").strip().upper()
    if not texto:
        return ""

    sin_tildes = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^A-Z0-9]+", " ", sin_tildes).strip()


def _format_amount(value: Any) -> str:
    """Importe en formato colombiano para los mensajes al cliente."""

    try:
        return "$" + f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _duplicate_key(transaction: dict[str, Any]) -> tuple[str, float, str]:
    """Lo que dos cargos deben compartir para ser el mismo cobro repetido."""

    return (
        normalize_merchant(transaction.get("merchant")),
        round(float(transaction.get("amount") or 0), 2),
        str(transaction.get("date") or ""),
    )


def _split_valid_duplicates(
    selected: list[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Separa la selección en duplicados reales y cargos sueltos.

    Agrupa por comercio + monto + fecha. Un grupo con dos o más cargos es un
    cobro duplicado; uno con un solo cargo no lo es y se descarta, porque un
    cargo aislado no prueba nada.

    Devuelve ``(grupos_validos, descartados)``.
    """

    por_clave: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for transaction in selected:
        por_clave.setdefault(_duplicate_key(transaction), []).append(transaction)

    validos = [g for g in por_clave.values() if len(g) >= _MIN_DUPLICATES]
    descartados = [g[0] for g in por_clave.values() if len(g) < _MIN_DUPLICATES]
    return validos, descartados


def _total_pages(total_transactions: int) -> int:
    """Número de páginas del selector (mínimo 1, aunque no haya nada)."""

    return max(
        1,
        (total_transactions + _TRANSACTIONS_PER_PAGE - 1) // _TRANSACTIONS_PER_PAGE,
    )


def _current_page(conversation: Conversation, total_pages: int) -> int:
    """Página actual, acotada al rango válido."""

    try:
        page = int(conversation.captured_data.get(_TRANSACTIONS_PAGE_KEY) or 0)
    except (TypeError, ValueError):
        page = 0

    return max(0, min(page, total_pages - 1))


def _toggle_transaction_selection(
    conversation: Conversation,
    transactions: list[dict[str, Any]],
) -> None:
    """Actualiza selección individual y paginación."""

    selected = set(
        _load_json(
            conversation,
            _TRANSACTIONS_SELECTED_KEY,
            [],
        )
    )

    answer = str(
        conversation.flow_answers.get(
            _ANSWER_TRANSACTION
        )
        or ""
    ).strip()

    # -----------------------------------------
    # Selección / deselección
    # -----------------------------------------
    if answer.startswith("transaccion_"):
        valid_ids = {
            str(transaction.get("selection_id") or "")
            for transaction in transactions
        }

        if answer in valid_ids:
            if answer in selected:
                selected.remove(answer)
            else:
                selected.add(answer)

    # -----------------------------------------
    # Paginación (adelante y atrás)
    # -----------------------------------------
    elif answer in ("mas_movimientos", "pagina_anterior"):
        total_pages = _total_pages(len(transactions))
        page = _current_page(conversation, total_pages)

        page = page + 1 if answer == "mas_movimientos" else page - 1
        page = max(0, min(page, total_pages - 1))

        conversation.captured_data[_TRANSACTIONS_PAGE_KEY] = str(page)

    _store_json(
        conversation,
        _TRANSACTIONS_SELECTED_KEY,
        sorted(selected),
    )

    # El click ya fue procesado.
    conversation.flow_answers.pop(
        _ANSWER_TRANSACTION,
        None,
    )


async def _prefetch_groups(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Carga grupos, aplana transacciones y prepara paginación."""

    signature = _groups_query_signature(conversation)

    stored_signature = str(
        conversation.captured_data.get(
            _GROUPS_QUERY_SIGNATURE_KEY
        )
        or ""
    )

    movements = _load_json(
        conversation,
        _MOVEMENTS_KEY,
        None,
    )

    # Nueva búsqueda: producto + fecha + monto cambiaron.
    if movements is None or stored_signature != signature:
        product = _selected_product(conversation)

        is_card = (
            str(
                product.get("product_type") or ""
            ).upper()
            == "CARD"
        )

        response = await client.buscar_grupos(
            customer_id=str(
                conversation.user_id or ""
            ).strip(),
            transaction_date=str(
                conversation.flow_answers.get(
                    _ANSWER_DATE
                )
                or ""
            ),
            amount=_parse_amount(
                conversation.flow_answers.get(
                    _ANSWER_AMOUNT
                )
            ),
            card_id=(
                str(product.get("card_id") or "")
                if is_card
                else ""
            ),
            account_id=(
                ""
                if is_card
                else str(
                    product.get("contract_id") or ""
                )
            ),
        )

        # `transactions` trae TODOS los movimientos del rango, sin recortar.
        movements = (
            ((response or {}).get("data") or {}).get("transactions")
            or []
        )

        _store_json(
            conversation,
            _MOVEMENTS_KEY,
            movements,
        )

        conversation.captured_data[
            _GROUPS_QUERY_SIGNATURE_KEY
        ] = signature

        conversation.captured_data[
            _TRANSACTIONS_PAGE_KEY
        ] = "0"

        _store_json(
            conversation,
            _TRANSACTIONS_SELECTED_KEY,
            [],
        )

        _store_json(
            conversation,
            _TRANSACTIONS_KEY,
            [],
        )

        logger.info(
            "DOBLE_COBRO MOVEMENTS conversation_id=%s en_rango=%s",
            conversation.conversation_id,
            len(movements),
        )

    movements = _load_json(conversation, _MOVEMENTS_KEY, [])

    if not movements:
        conversation.current_step = "3.4.0.6.pqr"
        return

    transactions = _load_json(
        conversation,
        _TRANSACTIONS_KEY,
        None,
    )

    if not transactions:
        product = _selected_product(conversation)

        transactions = _build_transactions(
            conversation,
            movements,
            product=product,
        )

        _store_json(
            conversation,
            _TRANSACTIONS_KEY,
            transactions,
        )

        logger.info(
            "DOBLE_COBRO TRANSACTIONS "
            "conversation_id=%s total=%s",
            conversation.conversation_id,
            len(transactions),
        )

    if not transactions:
        conversation.current_step = "3.4.0.6.pqr"
        return

    _toggle_transaction_selection(
        conversation,
        transactions,
    )

# ---------------------------------------------------------------------------
# 3.4.0.7 - Registro del caso
# ---------------------------------------------------------------------------


def _build_tantia_item(
    conversation: Conversation,
    *,
    product: dict[str, Any],
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Una transacción del caso, con la misma forma que en TXNR.

    Los campos que en transacción no reconocida vienen de PostgreSQL
    (``customer_name``, ``personal_id``, ``customer_mail``, ``customer_id``) van
    vacíos: doble cobro resuelve sus productos contra el ASO, que no trae los
    datos del titular. Quedan declarados para que la estructura sea idéntica y
    solo haya que rellenarlos cuando se integre back_data.
    """

    is_card = str(product.get("product_type") or "").upper() == "CARD"

    return {
        "fecha_recepcion": datetime.now().strftime("%Y-%m-%d"),
        "customer_id": "",
        "customer_name": "",
        "customer_mail": "",
        "personal_id": "",
        "evento": _WORKFLOW,
        "contrato": str(product.get("contract_id") or ""),
        "numero_tarjeta": str(product.get("card_id") or ""),
        "tipo_producto": str(product.get("commercial_product_desc") or ""),
        "origin_flag": _ORIGIN_CARD if is_card else _ORIGIN_ACCOUNT,
        "card_brand": str(product.get("card_brand") or ""),
        "last_four": str(product.get("last_four") or ""),
        "fecha_trx": str(conversation.flow_answers.get(_ANSWER_DATE) or ""),
        "movimiento_descripcion": str(transaction.get("merchant") or ""),
        "movimiento_valor": transaction.get("amount"),
        "tx_id": str(transaction.get("movement_id") or ""),
        "clasificacion": _WORKFLOW,
        "detalle": transaction.get("raw") or {},
    }


async def _register_case(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Registra únicamente las transacciones seleccionadas por el cliente."""

    del client  # el registro es directo contra OpenSearch

    transactions = _load_json(
        conversation,
        _TRANSACTIONS_KEY,
        [],
    )

    selected_ids = set(
        _load_json(
            conversation,
            _TRANSACTIONS_SELECTED_KEY,
            [],
        )
    )

    if not selected_ids:
        conversation.captured_data[_GROUPS_WARNING_KEY] = _MSG.validacion.sin_seleccion
        conversation.current_step = "3.4.0.6"
        return

    selected_transactions = [
        transaction
        for transaction in transactions
        if str(transaction.get("selection_id") or "") in selected_ids
    ]

    # ---------------------------------------------------------------
    # Validación: solo se reporta lo que de verdad es un cobro duplicado.
    #
    # Se agrupa la selección por comercio + monto + fecha. Un grupo con dos o
    # más cargos sí lo es; un cargo suelto no, y se descarta avisando al
    # cliente. El flujo continúa con lo que sí procede en vez de rechazarlo
    # todo por una casilla mal marcada.
    # ---------------------------------------------------------------
    grupos_validos, descartados = _split_valid_duplicates(selected_transactions)

    if descartados:
        detalle = ", ".join(
            _MSG.validacion.descartada_item.format(
                comercio=(
                    item.get("merchant")
                    or _MSG.selector_transacciones.sin_comercio
                ),
                monto=_format_amount(item.get("amount")),
            )
            for item in descartados
        )
        conversation.captured_data[_DISCARDED_WARNING_KEY] = (
            _MSG.validacion.descartadas.format(detalle=detalle)
        )

    logger.info(
        "DOBLE_COBRO SELECCION conversation_id=%s marcadas=%s grupos_validos=%s descartadas=%s",
        conversation.conversation_id,
        len(selected_transactions),
        len(grupos_validos),
        len(descartados),
    )

    if not grupos_validos:
        conversation.captured_data[_GROUPS_WARNING_KEY] = _MSG.validacion.ninguna_pareja
        conversation.current_step = "3.4.0.6"
        return

    product = _selected_product(conversation)

    # UNA transacción por grupo, no una por cargo sobrante.
    #
    # Negocio revisa el caso mirando los movimientos del cliente, así que con
    # un cargo del grupo le basta para ubicarlo: si el mismo cobro aparece tres
    # veces, reportarlo tres veces solo repite la misma información. Se envía
    # el segundo cargo (el primer repetido), porque el más antiguo es el
    # legítimo y no es el que se reclama.
    new_items: list[dict[str, Any]] = []

    for grupo in grupos_validos:
        grupo_ordenado = sorted(grupo, key=lambda x: str(x.get("time") or ""))

        new_items.append(
            _build_tantia_item(
                conversation,
                product=product,
                transaction=grupo_ordenado[1],
            )
        )

    if not new_items:
        logger.error(
            "DOBLE_COBRO sin grupos que reportar conversation_id=%s",
            conversation.conversation_id,
        )
        conversation.current_step = "3.4.0.8.no_procede"
        return

    # ---------------------------------------------------------------
    # Reportes anteriores.
    # ---------------------------------------------------------------
    items: list[dict[str, Any]] = list(
        await _load_reported_items(conversation)
    )

    # ---------------------------------------------------------------
    # Filtro de reemplazo:
    #
    # producto + fecha + monto
    #
    # Se eliminan únicamente los reportes anteriores equivalentes
    # a los cobros que se están volviendo a reportar.
    # ---------------------------------------------------------------
    product_id = str(
        product.get("card_id")
        or product.get("contract_id")
        or ""
    ).strip()

    transaction_date = str(
        conversation.flow_answers.get(
            _ANSWER_DATE
        )
        or ""
    ).strip()

    selected_amounts: set[float] = {
        float(transaction.get("movimiento_valor") or 0)
        for transaction in new_items
        if transaction.get("movimiento_valor") is not None
    }

    filtered_items: list[dict[str, Any]] = []

    for item in items:
        should_replace = False

        for amount in selected_amounts:
            if _matches_reported(
                item,
                product_id=product_id,
                transaction_date=transaction_date,
                amount=amount,
            ):
                should_replace = True
                break

        if not should_replace:
            filtered_items.append(item)

    items = filtered_items
    items.extend(new_items)

    nuevos = len(new_items)

    try:
        await _case_store().record_milestone(
            client_id=str(
                conversation.user_id or ""
            ).strip(),
            conversation_id=conversation.conversation_id,
            milestone=_MILESTONE_REPORTED,
            snapshot={
                "tantia": items[-1],
                "tantia_items": items,
            },
            outcome=_OUTCOME_REPORTED,
            tipo_de_notificacion=NOTIFICATION_DOBLE_COBRO,
        )
    except Exception:
        logger.exception(
            "DOBLE_COBRO no se pudo registrar el caso "
            "conversation_id=%s",
            conversation.conversation_id,
        )

        conversation.current_step = "3.4.0.8.no_procede"
        return

    logger.info(
        "DOBLE_COBRO CASE REGISTERED "
        "conversation_id=%s seleccionadas=%s "
        "transacciones=%s total=%s",
        conversation.conversation_id,
        len(selected_ids),
        nuevos,
        len(items),
    )

    conversation.current_step = "3.4.0.8"


# ---------------------------------------------------------------------------
# 3.4.0.8 - Estado del caso
# ---------------------------------------------------------------------------


async def _check_case_status(
    conversation: Conversation,
    client: DobleCobroClient,
) -> None:
    """Confirma que el caso quedó guardado antes de prometerle el abono.

    No interpreta ningún estado de gestión: el bot solo deja la información
    reposada y negocio la trabaja después. Lo único que se verifica aquí es que
    la escritura en OpenSearch sea legible; si no lo es, se cae al mensaje que
    no promete nada.
    """

    del client

    items = await _load_reported_items(conversation)

    logger.info(
        "DOBLE_COBRO CASE PERSISTED conversation_id=%s transacciones=%s",
        conversation.conversation_id,
        len(items),
    )

    conversation.captured_data[_CASE_ITEMS_KEY] = str(len(items))
    conversation.current_step = (
        "3.4.0.8.pendiente" if items else "3.4.0.8.no_procede"
    )

    # El mensaje de cierre se arma SIEMPRE desde el catálogo, no desde el
    # `question` del YAML: así hay una sola fuente para ese texto.
    #
    # Si además algún cargo marcado se descartó por no formar pareja, se le
    # dice aquí: el reporte de lo que sí procede ya está hecho, y callarlo le
    # haría creer que reportó algo que no reportó.
    if conversation.current_step == "3.4.0.8.pendiente":
        mensaje = _MSG.confirmacion.registrado
        descartadas = conversation.captured_data.pop(_DISCARDED_WARNING_KEY, None)
        if descartadas:
            mensaje = f"{mensaje}\n\n{descartadas}"
        conversation.captured_data["dynamic_prompt_3.4.0.8.pendiente"] = mensaje
    else:
        conversation.captured_data.pop(_DISCARDED_WARNING_KEY, None)


# ---------------------------------------------------------------------------
# Tablas de despacho
# ---------------------------------------------------------------------------

_ACTION_HANDLERS = {
    "mostrar_productos_activos_dc": _prefetch_products,
    "validar_vigencia_doble_cobro": _validate_validity,
    "validar_recurrencia_doble_cobro": _validate_recurrence,
    "mostrar_grupos_doble_cobro": _prefetch_groups,
    "registrar_caso_doble_cobro": _register_case,
    "consultar_estado_doble_cobro": _check_case_status,
}


def _load_step_actions() -> dict[str, str]:
    """Mapa paso -> accion, leido del propio YAML del flujo.

    Se deriva del YAML en vez de mantenerse a mano: es la unica forma de que
    renumerar el arbol no vuelva a dejar el hook apuntando a pasos que ya no
    existen. Solo se conservan las acciones que este hook sabe atender.
    """

    try:
        definition = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        logger.exception("DOBLE_COBRO no se pudo leer el YAML del flujo")
        return {}

    return {
        step_id: step["action"]
        for step_id, step in (definition.get("steps") or {}).items()
        if isinstance(step, dict) and step.get("action") in _ACTION_HANDLERS
    }


_STEP_ACTIONS = _load_step_actions()
