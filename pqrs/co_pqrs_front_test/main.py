from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st
import urllib3
from requests import Response
from requests.exceptions import HTTPError, RequestException

from app_benchmark import render_benchmark_page
from app_metrics import (
    DEFAULT_METRICS_SOURCE,
    _resolve_opensearch_settings,
    build_metrics_snapshot,
    format_duration_ms,
    format_timestamp,
)

APP_DIR = Path(__file__).resolve().parent
EMBARGOS_SAMPLE_PATH = APP_DIR / "Muestra_tabla_embargos.csv"
CONVERSATION_DATE_FORMAT = "%Y%m%d"
DEFAULT_API_BASE_URL = os.getenv("PQRS_AGENT_API_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT_SECONDS = 45


def normalize_base_url(value: str) -> str:
    """Return a normalized backend base URL without trailing slash."""

    return value.strip().rstrip("/")


def clean_string(value: Any) -> str:
    """Return a stripped string representation for UI and CSV values."""

    return str(value or "").strip()


def format_cop_currency(amount: int) -> str:
    """Format a whole-peso amount as "$x.xxx,xx" (COP thousands/decimal marks)."""

    return f"$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_conversation_id(customer_id: str, conversation_date: date | None = None) -> str:
    """Build a compatibility `conversation_id` when the backend still requires it on `/start`."""

    normalized_customer_id = clean_string(customer_id)
    if not normalized_customer_id:
        return ""

    normalized_date = conversation_date or datetime.now().date()
    return f"{normalized_customer_id}_{normalized_date.strftime(CONVERSATION_DATE_FORMAT)}"


def parse_conversation_id(value: str) -> tuple[str | None, date | None]:
    """Parse a conversation identifier in the `customer_id_yyyymmdd` format."""

    normalized_value = clean_string(value)
    customer_id, separator, raw_date = normalized_value.rpartition("_")
    if not separator or not customer_id:
        return None, None

    try:
        parsed_date = datetime.strptime(raw_date, CONVERSATION_DATE_FORMAT).date()
    except ValueError:
        return None, None

    return customer_id, parsed_date


def unique_preserving_order(values: list[str]) -> list[str]:
    """Return unique strings while preserving the original order."""

    return list(dict.fromkeys(value for value in values if value))


def queue_draft_customer_id_update(customer_id: str | None) -> None:
    """Defer `draft_customer_id` updates until the next rerun, before widgets exist."""

    normalized_customer_id = clean_string(customer_id)
    st.session_state["pending_draft_customer_id"] = normalized_customer_id or None


def get_effective_draft_customer_id() -> str:
    """Return the manual customer override when present, otherwise the selected CSV id."""

    manual_customer_id = clean_string(st.session_state.get("draft_customer_id_manual"))
    if manual_customer_id:
        return manual_customer_id

    return clean_string(st.session_state.get("draft_customer_id"))


def clear_manual_draft_customer_id() -> None:
    """Clear the manual customer override when the user goes back to the CSV list."""

    st.session_state["draft_customer_id_manual"] = ""


def build_file_cache_key(csv_path: str) -> str:
    """Return a lightweight cache key that changes when the CSV file changes."""

    source_path = Path(csv_path)
    if not source_path.exists():
        return "missing"

    stat = source_path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


@st.cache_data(show_spinner=False)
def load_embargo_customer_options(csv_path: str, _cache_key: str) -> list[dict[str, Any]]:
    """Load customers with multiple products from the embargo sample CSV."""

    source_path = Path(csv_path)
    if not source_path.exists():
        return []

    grouped_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    with source_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        for row in reader:
            customer_id = clean_string(row.get("customer_id"))
            if not customer_id:
                continue

            grouped_rows[customer_id].append(
                {
                    "contract_id": clean_string(row.get("contract_id")),
                    "product_id": clean_string(row.get("contract_product_id")),
                }
            )

    options: list[dict[str, Any]] = []
    for customer_id, rows in grouped_rows.items():
        product_ids = sorted({row["product_id"] for row in rows if row["product_id"]})
        if len(product_ids) < 2:
            continue

        product_options: list[dict[str, Any]] = []
        for product_id in product_ids:
            contract_ids = unique_preserving_order(
                [
                    row["contract_id"]
                    for row in rows
                    if row["product_id"] == product_id and row["contract_id"]
                ]
            )
            contract_preview = ", ".join(contract_ids[:3]) if contract_ids else "Sin contratos"
            if len(contract_ids) > 3:
                contract_preview = f"{contract_preview}..."

            product_options.append(
                {
                    "product_id": product_id,
                    "contract_ids": contract_ids,
                    "label": f"Producto {product_id} | contratos: {contract_preview}",
                }
            )

        options.append(
            {
                "customer_id": customer_id,
                "row_count": len(rows),
                "product_count": len(product_ids),
                "product_ids": product_ids,
                "product_options": product_options,
                "label": (
                    f"{customer_id} | productos {', '.join(product_ids)} | "
                    f"{len(rows)} registro(s)"
                ),
            }
        )

    options.sort(
        key=lambda option: (
            -int(option["product_count"]),
            -int(option["row_count"]),
            str(option["customer_id"]),
        )
    )
    return options


def find_customer_option(
    customer_options: list[dict[str, Any]],
    customer_id: str,
) -> dict[str, Any] | None:
    """Return the matching customer option from the CSV-derived sample list."""

    normalized_customer_id = clean_string(customer_id)
    return next(
        (
            option
            for option in customer_options
            if str(option["customer_id"]) == normalized_customer_id
        ),
        None,
    )


def initialize_session_state() -> None:
    """Populate Streamlit session state with the keys used by the app."""

    customer_options = load_embargo_customer_options(
        str(EMBARGOS_SAMPLE_PATH),
        build_file_cache_key(str(EMBARGOS_SAMPLE_PATH)),
    )
    default_customer_id = (
        str(customer_options[0]["customer_id"])
        if customer_options
        else ""
    )

    st.session_state.setdefault("api_base_url", normalize_base_url(DEFAULT_API_BASE_URL))
    st.session_state.setdefault("current_view", "chat")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("health_status", None)
    st.session_state.setdefault("health_message", "")
    st.session_state.setdefault("metrics_source", DEFAULT_METRICS_SOURCE)
    st.session_state.setdefault("chat_notice", None)
    st.session_state.setdefault("selected_customer_id", default_customer_id)
    st.session_state.setdefault("conversation_id", "")
    st.session_state.setdefault("conversation_status", None)
    st.session_state.setdefault("draft_customer_id", default_customer_id)
    st.session_state.setdefault("draft_customer_id_manual", "")
    st.session_state.setdefault("draft_product_id", "")
    st.session_state.setdefault("pending_draft_customer_id", None)
    st.session_state.setdefault("pending_polling_conversation_id", "")

    pending_draft_customer_id = clean_string(st.session_state.get("pending_draft_customer_id"))
    if pending_draft_customer_id:
        st.session_state["draft_customer_id"] = pending_draft_customer_id
        st.session_state["pending_draft_customer_id"] = None

    current_conversation_id = clean_string(st.session_state.get("conversation_id"))
    current_customer_id, _ = parse_conversation_id(current_conversation_id)
    if current_customer_id:
        st.session_state["selected_customer_id"] = current_customer_id
        st.session_state["draft_customer_id"] = current_customer_id

    active_customer = find_customer_option(customer_options, st.session_state["selected_customer_id"])
    if (
        active_customer is None
        and not clean_string(st.session_state["selected_customer_id"])
        and customer_options
    ):
        active_customer = customer_options[0]
        st.session_state["selected_customer_id"] = str(active_customer["customer_id"])
        st.session_state["draft_customer_id"] = str(active_customer["customer_id"])

    draft_customer = find_customer_option(
        customer_options,
        st.session_state["draft_customer_id"],
    )
    if (
        draft_customer is None
        and not clean_string(st.session_state["draft_customer_id"])
        and customer_options
    ):
        draft_customer = customer_options[0]
        st.session_state["draft_customer_id"] = str(draft_customer["customer_id"])

    available_products = draft_customer["product_ids"] if draft_customer else []
    if available_products and st.session_state["draft_product_id"] not in available_products:
        st.session_state["draft_product_id"] = str(available_products[0])
    elif not available_products:
        st.session_state["draft_product_id"] = ""


def reset_chat(
    *,
    customer_id: str | None = None,
) -> None:
    """Start a clean local chat session and wait for the backend conversation id."""

    normalized_customer_id = clean_string(
        customer_id or st.session_state.get("selected_customer_id")
    )

    st.session_state["selected_customer_id"] = normalized_customer_id
    queue_draft_customer_id_update(normalized_customer_id)
    st.session_state["conversation_id"] = ""
    st.session_state["conversation_status"] = None
    st.session_state["pending_polling_conversation_id"] = ""
    st.session_state["messages"] = []


def clear_local_conversation() -> None:
    """Clear the local conversation history shown in the frontend."""

    st.session_state["messages"] = []
    st.session_state["conversation_status"] = None
    st.session_state["pending_polling_conversation_id"] = ""


def has_active_conversation() -> bool:
    """Return whether the frontend already has an open backend conversation."""

    active_conversation_id = clean_string(st.session_state.get("conversation_id"))
    if not active_conversation_id:
        return False

    return clean_string(st.session_state.get("conversation_status")) not in {
        "Closed",
        "Inactive",
    }


def has_pending_polling_message() -> bool:
    """Return whether the latest backend turn is still processing."""

    return bool(clean_string(st.session_state.get("pending_polling_conversation_id")))


def clear_pending_polling_state() -> None:
    """Clear the local pending-processing marker and its placeholder message."""

    st.session_state["pending_polling_conversation_id"] = ""
    st.session_state["messages"] = [
        message
        for message in st.session_state["messages"]
        if message.get("kind") != "pending"
    ]


def mark_conversation_as_processing(conversation_id: str) -> None:
    """Mark the active conversation as still processing the latest chat turn."""

    normalized_conversation_id = clean_string(conversation_id) or clean_string(
        st.session_state.get("conversation_id")
    )
    st.session_state["pending_polling_conversation_id"] = normalized_conversation_id
    st.session_state["messages"] = [
        message
        for message in st.session_state["messages"]
        if message.get("kind") != "pending"
    ]
    add_chat_message(
        "assistant",
        "Procesando tu solicitud. Usa el boton de polling para consultar el mensaje pendiente.",
        kind="pending",
    )


def close_active_conversation() -> None:
    """Send `POST /end` using the active `conversation_id` and update local state."""

    active_conversation_id = clean_string(st.session_state.get("conversation_id"))
    if not active_conversation_id:
        st.session_state["chat_notice"] = {
            "level": "error",
            "message": "No hay un `conversation_id` activo para cerrar.",
        }
        return

    with st.spinner("Cerrando conversacion en el backend..."):
        result = end_conversation(
            base_url=st.session_state["api_base_url"],
            conversation_id=active_conversation_id,
            customer_id=st.session_state["selected_customer_id"],
        )

    if result["ok"]:
        clear_pending_polling_state()
        st.session_state["conversation_status"] = (
            result.get("conversation_status") or "Closed"
        )
        message_payload = result.get("message_payload") or {
            "content": result["message"],
            "options": [],
            "timestamp": None,
        }
        add_chat_message(
            "assistant",
            message_payload["content"],
            options=message_payload.get("options"),
            timestamp=message_payload.get("timestamp"),
            input_type=message_payload.get("input_type"),
            message_id=message_payload.get("message_id"),
        )
        st.session_state["chat_notice"] = {
            "level": "success",
            "message": (
                f"El backend cerro `{active_conversation_id}` via `/end` "
                f"con estado `{st.session_state['conversation_status']}`."
            ),
        }
        return

    st.session_state["chat_notice"] = {
        "level": "error",
        "message": result["message"],
    }


def build_opensearch_conversation_query(conversation_id: str) -> dict[str, Any]:
    """Build a query that matches the persisted conversation identifier."""

    normalized_conversation_id = clean_string(conversation_id)
    return {
        "query": {
            "bool": {
                "should": [
                    {"term": {"conversation_id.keyword": normalized_conversation_id}},
                    {"term": {"conversation_id": normalized_conversation_id}},
                    {"match_phrase": {"conversation_id": normalized_conversation_id}},
                ],
                "minimum_should_match": 1,
            }
        }
    }


def _opensearch_timeout(settings: dict[str, Any]) -> tuple[float, float]:
    """Return a more forgiving `(connect, read)` timeout for OpenSearch maintenance calls."""

    base_timeout = float(settings.get("timeout", 10.0) or 10.0)
    return (min(base_timeout, 10.0), max(base_timeout, 45.0))


def execute_opensearch_request(
    settings: dict[str, Any],
    method: str,
    path: str,
    *,
    json_payload: dict[str, Any] | None = None,
    data_payload: str | None = None,
    params: dict[str, str] | None = None,
    expected_statuses: set[int],
    headers: dict[str, str] | None = None,
) -> Response:
    """Execute a direct request against OpenSearch with consistent auth and timeouts."""

    if not settings["verify_ssl"]:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    endpoint = str(settings["endpoint"]).rstrip("/")
    url = f"{endpoint}{path}"
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)

    try:
        response = requests.request(
            method,
            url,
            auth=(settings["user"], settings["password"]),
            verify=settings["verify_ssl"],
            timeout=_opensearch_timeout(settings),
            json=json_payload,
            data=data_payload,
            params=params,
            headers=merged_headers,
        )
    except RequestException as exc:
        raise ValueError(
            "No pude comunicarme con OpenSearch. "
            f"Detalle: {exc}"
        ) from exc

    if response.status_code not in expected_statuses:
        raise ValueError(
            f"OpenSearch devolvio HTTP {response.status_code} en `{path}`. "
            f"Detalle: {extract_error_message(response)}"
        )

    return response


def load_opensearch_document_ids(
    settings: dict[str, Any],
    index_name: str,
    conversation_id: str,
    *,
    page_size: int = 200,
) -> tuple[list[str], bool]:
    """Load OpenSearch document ids that belong to the given conversation."""

    query = build_opensearch_conversation_query(conversation_id)["query"]
    document_ids: list[str] = []
    search_after: list[Any] | None = None

    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "_source": False,
            "query": query,
            "sort": [{"_id": {"order": "asc"}}],
        }
        if search_after is not None:
            body["search_after"] = search_after

        response = execute_opensearch_request(
            settings,
            "POST",
            f"/{index_name}/_search",
            json_payload=body,
            expected_statuses={200, 404},
        )
        if response.status_code == 404:
            return [], False

        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        if not hits:
            break

        document_ids.extend(
            str(hit["_id"])
            for hit in hits
            if hit.get("_id") is not None
        )

        search_after = hits[-1].get("sort")
        if len(hits) < page_size or not search_after:
            break

    return document_ids, True


def delete_opensearch_document_by_id(
    settings: dict[str, Any],
    index_name: str,
    document_id: str,
) -> tuple[bool, bool]:
    """Delete a single OpenSearch document by id.

    Returns `(deleted, index_exists)`.
    """

    response = execute_opensearch_request(
        settings,
        "DELETE",
        f"/{index_name}/_doc/{quote(document_id, safe='')}",
        params={"refresh": "false"},
        expected_statuses={200, 404},
    )

    if response.status_code == 404:
        return False, False

    payload = response.json()
    result = clean_string(payload.get("result"))
    if result == "not_found":
        return False, True

    return True, True


def bulk_delete_opensearch_documents(
    settings: dict[str, Any],
    index_name: str,
    document_ids: list[str],
    *,
    chunk_size: int = 200,
) -> tuple[int, list[str]]:
    """Delete multiple OpenSearch documents in bulk and return `(deleted_count, failures)`."""

    if not document_ids:
        return 0, []

    deleted_count = 0
    failures: list[str] = []

    for start in range(0, len(document_ids), chunk_size):
        chunk = document_ids[start : start + chunk_size]
        operations = "".join(
            json.dumps(
                {
                    "delete": {
                        "_index": index_name,
                        "_id": document_id,
                    }
                }
            )
            + "\n"
            for document_id in chunk
        )
        response = execute_opensearch_request(
            settings,
            "POST",
            "/_bulk",
            data_payload=operations,
            params={"refresh": "false"},
            expected_statuses={200},
            headers={"Content-Type": "application/x-ndjson"},
        )

        payload = response.json()
        for item in payload.get("items", []):
            result = item.get("delete", {})
            status = int(result.get("status", 0) or 0)
            if status in {200, 202}:
                deleted_count += 1
                continue
            if status == 404:
                continue

            failures.append(str(result.get("error") or result))

    return deleted_count, failures


def refresh_opensearch_index(settings: dict[str, Any], index_name: str) -> bool:
    """Refresh an OpenSearch index and report whether it exists."""

    response = execute_opensearch_request(
        settings,
        "POST",
        f"/{index_name}/_refresh",
        expected_statuses={200, 404},
    )
    return response.status_code != 404


def build_headers() -> dict[str, str]:
    """Return default JSON headers for the backend requests."""

    return {"Content-Type": "application/json"}


def resolve_user_id(
    *,
    customer_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    """Resolve the `user_id` expected by `/start`."""

    normalized_customer_id = clean_string(customer_id)
    if normalized_customer_id:
        return normalized_customer_id

    parsed_customer_id, _ = parse_conversation_id(clean_string(conversation_id))
    return clean_string(parsed_customer_id)


def build_backend_payload(
    endpoint_path: str,
    conversation_id: str,
    content: str | None,
    *,
    customer_id: str | None = None,
    prefer_conversation_id_for_start: bool = False,
) -> dict[str, str]:
    """Build the JSON body required by each backend endpoint."""

    if endpoint_path == "/start":
        if prefer_conversation_id_for_start:
            normalized_conversation_id = clean_string(conversation_id)
            if not normalized_conversation_id:
                raise ValueError(
                    "No pude resolver el `conversation_id` requerido por este backend en `/start`."
                )
            return {
                "conversation_id": normalized_conversation_id,
            }

        user_id = resolve_user_id(
            customer_id=customer_id,
            conversation_id=conversation_id,
        )
        if not user_id:
            raise ValueError("No pude resolver el `user_id` requerido por `/start`.")
        return {
            "user_id": user_id,
        }

    normalized_conversation_id = clean_string(conversation_id)
    if not normalized_conversation_id:
        raise ValueError("No hay un `conversation_id` activo para consultar al backend.")

    if endpoint_path == "/end":
        return {
            "conversation_id": normalized_conversation_id,
        }

    if endpoint_path == "/chat":
        normalized_content = clean_string(content)
        if not normalized_content:
            raise ValueError("No puedo enviar un mensaje vacio al backend.")
        return {
            "conversation_id": normalized_conversation_id,
            "content": normalized_content,
        }

    raise ValueError(f"El endpoint `{endpoint_path}` no esta soportado por el front.")


def normalize_backend_message(message: Any) -> dict[str, Any] | None:
    """Normalize backend assistant payloads from both legacy and structured formats."""

    if isinstance(message, str):
        normalized_content = message.strip()
        if not normalized_content:
            return None
        return {
            "content": normalized_content,
            "options": [],
            "sender": "bot",
            "timestamp": None,
            "input_type": None,
        }

    if not isinstance(message, dict):
        return None

    raw_content = message.get("content")
    normalized_content = ""
    normalized_options: list[dict[str, str]] = []

    if isinstance(raw_content, dict):
        normalized_content = clean_string(raw_content.get("label"))
        raw_options = raw_content.get("options")
        if isinstance(raw_options, list):
            for option in raw_options:
                if not isinstance(option, dict):
                    continue
                option_key = clean_string(option.get("key"))
                option_label = clean_string(option.get("label"))
                if option_key and option_label:
                    normalized_options.append(
                        {
                            "key": option_key,
                            "label": option_label,
                        }
                    )
    else:
        normalized_content = clean_string(message.get("label"))

    if not normalized_content:
        return None

    return {
        "content": normalized_content,
        "options": normalized_options,
        "sender": clean_string(message.get("sender")) or "bot",
        "timestamp": clean_string(message.get("timestamp")) or None,
        "input_type": clean_string(message.get("input_type")) or None,
        "message_id": clean_string(message.get("message_id")) or None,
    }


def extract_error_message(response: Response) -> str:
    """Build a readable error message from a failing HTTP response."""

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            formatted_items: list[str] = []
            for item in detail:
                if not isinstance(item, dict):
                    formatted_items.append(str(item))
                    continue

                location = ".".join(str(part) for part in item.get("loc") or [])
                message = clean_string(item.get("msg"))
                if location and message:
                    formatted_items.append(f"{location}: {message}")
                elif message:
                    formatted_items.append(message)

            if formatted_items:
                return " | ".join(formatted_items)
        if detail is not None:
            return str(detail)

    body = response.text.strip()
    if body:
        return body

    return f"El backend respondio con HTTP {response.status_code}."


def format_request_exception(exc: RequestException) -> str:
    """Format requests exceptions in Spanish for the UI."""

    return (
        "No pude comunicarme con el backend. "
        f"Verifica que `agentepqr` este arriba y accesible. Detalle: {exc}"
    )


def delete_conversation_from_opensearch(conversation_id: str) -> dict[str, Any]:
    """Delete a conversation directly from OpenSearch conversation and message indices."""

    normalized_conversation_id = clean_string(conversation_id)
    if not normalized_conversation_id:
        raise ValueError("No hay un `conversation_id` activo para borrar.")

    settings = _resolve_opensearch_settings()
    endpoint = str(settings["endpoint"]).rstrip("/")
    missing_indices: list[str] = []
    warnings: list[str] = []

    conversation_deleted, conversation_index_exists = delete_opensearch_document_by_id(
        settings,
        settings["conversations_index"],
        normalized_conversation_id,
    )
    if not conversation_index_exists:
        missing_indices.append(settings["conversations_index"])

    message_ids, messages_index_exists = load_opensearch_document_ids(
        settings,
        settings["messages_index"],
        normalized_conversation_id,
    )
    if not messages_index_exists:
        missing_indices.append(settings["messages_index"])
        deleted_messages = 0
    else:
        try:
            deleted_messages, bulk_failures = bulk_delete_opensearch_documents(
                settings,
                settings["messages_index"],
                message_ids,
            )
        except ValueError as exc:
            deleted_messages = 0
            bulk_failures = []
            warnings.append(
                "No pude borrar todos los mensajes asociados. "
                f"Detalle: {exc}"
            )
        else:
            if bulk_failures:
                warnings.append(
                    "OpenSearch reporto fallos al borrar algunos mensajes: "
                    + " | ".join(bulk_failures[:3])
                )

    for index_name in (
        settings["conversations_index"],
        settings["messages_index"],
    ):
        if index_name in missing_indices:
            continue
        try:
            refresh_opensearch_index(settings, index_name)
        except ValueError as exc:
            warnings.append(
                f"No pude refrescar el indice `{index_name}` despues del borrado: {exc}"
            )

    deleted_by_index = {
        settings["conversations_index"]: 1 if conversation_deleted else 0,
        settings["messages_index"]: deleted_messages,
    }

    return {
        "conversation_id": normalized_conversation_id,
        "endpoint": endpoint,
        "deleted_by_index": deleted_by_index,
        "deleted_total": sum(deleted_by_index.values()),
        "missing_indices": missing_indices,
        "warnings": warnings,
    }


def check_health(base_url: str) -> tuple[str, str]:
    """Ping /health and return the UI status plus a human-readable message."""

    try:
        response = requests.get(
            f"{base_url}/health",
            timeout=8,
            headers=build_headers(),
        )
        response.raise_for_status()
        payload = response.json()
    except HTTPError as exc:
        if exc.response is None:
            return "error", f"El backend respondio con error: {exc}"
        return "error", extract_error_message(exc.response)
    except RequestException as exc:
        return "error", format_request_exception(exc)
    except ValueError:
        return "error", "El endpoint /health no devolvio JSON valido."

    status = payload.get("status")
    if status == "ok":
        return "success", "Conexion lista. El backend respondio `status: ok`."

    return "warning", f"/health respondio, pero con un payload inesperado: {payload}"


def send_message_request(
    base_url: str,
    endpoint_path: str,
    conversation_id: str,
    content: str | None,
    *,
    customer_id: str | None = None,
    prefer_conversation_id_for_start: bool = False,
) -> dict[str, Any]:
    """Send a user message to one backend endpoint and normalize the response."""

    try:
        payload = build_backend_payload(
            endpoint_path,
            conversation_id,
            content,
            customer_id=customer_id,
            prefer_conversation_id_for_start=prefer_conversation_id_for_start,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "status_code": None,
            "message": str(exc),
        }

    try:
        response = requests.post(
            f"{base_url}{endpoint_path}",
            json=payload,
            headers=build_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except HTTPError as exc:
        if exc.response is None:
            return {
                "ok": False,
                "status_code": None,
                "message": f"El backend respondio con error: {exc}",
            }
        return {
            "ok": False,
            "status_code": exc.response.status_code,
            "message": extract_error_message(exc.response),
        }
    except RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "message": format_request_exception(exc),
        }

    if response.status_code == 204:
        return {
            "ok": True,
            "pending": True,
            "status_code": response.status_code,
            "conversation_id": clean_string(conversation_id),
            "endpoint_path": endpoint_path,
            "message": "El backend sigue procesando este mensaje.",
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "ok": False,
            "status_code": response.status_code,
            "message": "El backend respondio, pero no envio JSON valido.",
        }

    normalized_message = normalize_backend_message(data.get("message"))
    returned_conversation_id = str(data.get("conversation_id", conversation_id))

    if normalized_message is None:
        return {
            "ok": False,
            "status_code": response.status_code,
            "message": (
                f"El payload de `{endpoint_path}` no tiene un campo `message` valido: {data}"
            ),
        }

    return {
        "ok": True,
        "status_code": response.status_code,
        "conversation_status": clean_string(data.get("status")) or None,
        "pending": False,
        "message": normalized_message["content"],
        "message_payload": normalized_message,
        "conversation_id": returned_conversation_id,
        "endpoint_path": endpoint_path,
    }


def should_retry_with_chat(result: dict[str, Any]) -> bool:
    """Return whether a failed `/start` call should transparently retry via `/chat`."""

    message = clean_string(result.get("message")).lower()
    return result.get("status_code") == 409 or "post /chat" in message


def should_retry_with_start(result: dict[str, Any]) -> bool:
    """Return whether a failed `/chat` call should transparently retry via `/start`."""

    message = clean_string(result.get("message")).lower()
    return result.get("status_code") == 404 or "post /start" in message


def should_retry_start_with_conversation_id(result: dict[str, Any]) -> bool:
    """Return whether `/start` rejected `user_id` and is still expecting `conversation_id`."""

    if result.get("status_code") not in {406, 422}:
        return False

    message = clean_string(result.get("message")).lower()
    return (
        "body.conversation_id" in message
        and "field required" in message
        and "body.user_id" in message
        and "extra inputs are not permitted" in message
    )


def send_conversation_message(
    base_url: str,
    conversation_id: str,
    customer_id: str,
    content: str | None,
    *,
    use_start: bool,
) -> dict[str, Any]:
    """Route the first turn through `/start` and subsequent turns through `/chat`."""

    primary_endpoint = "/start" if use_start else "/chat"
    primary_result = send_message_request(
        base_url,
        primary_endpoint,
        conversation_id,
        content,
        customer_id=customer_id,
    )
    if primary_result["ok"]:
        return primary_result

    if use_start and should_retry_start_with_conversation_id(primary_result):
        fallback_conversation_id = clean_string(conversation_id) or build_conversation_id(
            customer_id
        )
        fallback_result = send_message_request(
            base_url,
            "/start",
            fallback_conversation_id,
            content,
            customer_id=customer_id,
            prefer_conversation_id_for_start=True,
        )
        if fallback_result["ok"]:
            fallback_result["fallback_from"] = "/start:user_id"
            fallback_result["compat_mode"] = "start_requires_conversation_id"
        return fallback_result

    if use_start and should_retry_with_chat(primary_result):
        fallback_result = send_message_request(
            base_url,
            "/chat",
            conversation_id,
            content,
            customer_id=customer_id,
        )
        if fallback_result["ok"]:
            fallback_result["fallback_from"] = "/start"
        return fallback_result

    if (not use_start) and should_retry_with_start(primary_result):
        fallback_result = send_message_request(
            base_url,
            "/start",
            conversation_id,
            content,
            customer_id=customer_id,
        )
        if fallback_result["ok"]:
            fallback_result["fallback_from"] = "/chat"
        return fallback_result

    return primary_result


def end_conversation(
    base_url: str,
    conversation_id: str,
    *,
    customer_id: str,
) -> dict[str, Any]:
    """Finalize the active conversation via `POST /end`."""

    return send_message_request(
        base_url,
        "/end",
        conversation_id,
        None,
        customer_id=customer_id,
    )


def poll_conversation_message(base_url: str, conversation_id: str) -> dict[str, Any]:
    """Check whether an async chat turn finished and fetch the bot message if available."""

    normalized_conversation_id = clean_string(conversation_id)
    if not normalized_conversation_id:
        return {
            "ok": False,
            "status_code": None,
            "message": "No hay un `conversation_id` activo para consultar por polling.",
        }

    try:
        response = requests.post(
            f"{base_url}/polling",
            json={"conversation_id": normalized_conversation_id},
            headers=build_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "message": format_request_exception(exc),
        }

    if response.status_code == 204:
        return {
            "ok": True,
            "pending": True,
            "status_code": 204,
            "conversation_id": normalized_conversation_id,
            "message": "El backend sigue procesando este mensaje.",
        }

    if response.status_code == 303:
        return fetch_polling_message(base_url, normalized_conversation_id)

    try:
        response.raise_for_status()
    except HTTPError as exc:
        if exc.response is None:
            return {
                "ok": False,
                "status_code": None,
                "message": f"El backend respondio con error: {exc}",
            }
        return {
            "ok": False,
            "status_code": exc.response.status_code,
            "message": extract_error_message(exc.response),
        }

    return fetch_polling_message(base_url, normalized_conversation_id)


def fetch_polling_message(base_url: str, conversation_id: str) -> dict[str, Any]:
    """Fetch the latest bot message for a conversation using the polling endpoint."""

    normalized_conversation_id = clean_string(conversation_id)
    try:
        response = requests.get(
            f"{base_url}/polling/{quote(normalized_conversation_id, safe='')}",
            headers=build_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except HTTPError as exc:
        if exc.response is None:
            return {
                "ok": False,
                "status_code": None,
                "message": f"El backend respondio con error: {exc}",
            }
        return {
            "ok": False,
            "status_code": exc.response.status_code,
            "message": extract_error_message(exc.response),
        }
    except RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "message": format_request_exception(exc),
        }

    if response.status_code == 204:
        return {
            "ok": True,
            "pending": True,
            "status_code": 204,
            "conversation_id": normalized_conversation_id,
            "message": "El backend sigue procesando este mensaje.",
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "ok": False,
            "status_code": response.status_code,
            "message": "El endpoint de polling respondio, pero no envio JSON valido.",
        }

    normalized_message = normalize_backend_message(data.get("message"))
    returned_conversation_id = str(data.get("conversation_id", normalized_conversation_id))

    if normalized_message is None:
        return {
            "ok": False,
            "status_code": response.status_code,
            "message": (
                f"El payload de `/polling/{normalized_conversation_id}` no tiene un campo "
                f"`message` valido: {data}"
            ),
        }

    return {
        "ok": True,
        "pending": False,
        "status_code": response.status_code,
        "conversation_status": clean_string(data.get("status")) or None,
        "message": normalized_message["content"],
        "message_payload": normalized_message,
        "conversation_id": returned_conversation_id,
        "endpoint_path": f"/polling/{normalized_conversation_id}",
    }


def render_theme() -> None:
    """Inject a light custom theme that gives the app a more polished feel."""

    st.markdown(
        """
        <style>
        :root {
            --paper: #f7f1e6;
            --mist: #e8eef5;
            --ink: #17324d;
            --muted: #557086;
            --accent: #dd6b2f;
            --accent-strong: #9f3f17;
            --line: rgba(23, 50, 77, 0.14);
            --card: rgba(255, 252, 247, 0.82);
            --shadow: 0 18px 45px rgba(27, 41, 56, 0.12);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(221, 107, 47, 0.14), transparent 28%),
                radial-gradient(circle at top right, rgba(77, 136, 189, 0.16), transparent 24%),
                linear-gradient(160deg, #fbf6ee 0%, #f4f7fb 50%, #eef3ea 100%);
            color: var(--ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, rgba(252, 247, 239, 0.95) 0%, rgba(238, 244, 250, 0.96) 100%);
            border-right: 1px solid var(--line);
        }

        .block-container {
            max-width: 980px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        .hero-card {
            background: linear-gradient(145deg, rgba(255, 252, 246, 0.92), rgba(234, 242, 249, 0.88));
            border: 1px solid rgba(23, 50, 77, 0.08);
            border-radius: 24px;
            box-shadow: var(--shadow);
            padding: 1.5rem 1.6rem;
            margin-bottom: 1.25rem;
            position: relative;
            overflow: hidden;
        }

        .hero-card::after {
            content: "";
            position: absolute;
            inset: auto -40px -80px auto;
            width: 180px;
            height: 180px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(221, 107, 47, 0.22), transparent 70%);
        }

        .hero-eyebrow {
            display: inline-block;
            background: rgba(221, 107, 47, 0.12);
            color: var(--accent-strong);
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            padding: 0.35rem 0.7rem;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }

        .hero-title {
            font-family: "Trebuchet MS", "Segoe UI", sans-serif;
            font-size: clamp(2rem, 5vw, 3rem);
            line-height: 1;
            margin: 0 0 0.65rem 0;
            color: var(--ink);
        }

        .hero-copy {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.6;
            margin: 0;
            max-width: 50rem;
        }

        .info-chip-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 0.85rem;
            margin: 1rem 0 1.35rem;
        }

        .info-chip {
            background: var(--card);
            border: 1px solid rgba(23, 50, 77, 0.08);
            border-radius: 18px;
            padding: 0.9rem 1rem;
            box-shadow: 0 10px 28px rgba(27, 41, 56, 0.06);
        }

        .info-chip label {
            color: var(--muted);
            display: block;
            font-size: 0.8rem;
            margin-bottom: 0.3rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .info-chip code {
            color: var(--ink);
            font-size: 0.92rem;
            word-break: break-word;
        }

        .empty-state {
            background: rgba(255, 252, 247, 0.7);
            border: 1px dashed rgba(23, 50, 77, 0.18);
            border-radius: 22px;
            padding: 1.2rem 1.25rem;
            margin: 0.6rem 0 1rem;
            color: var(--muted);
        }

        .stChatMessage {
            border-radius: 22px;
            border: 1px solid rgba(23, 50, 77, 0.08);
            box-shadow: 0 8px 24px rgba(27, 41, 56, 0.06);
            background: rgba(255, 252, 247, 0.72);
            backdrop-filter: blur(10px);
        }

        .stChatMessage p {
            color: var(--ink);
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 999px;
            border: 1px solid rgba(23, 50, 77, 0.12);
            background: linear-gradient(180deg, rgba(255, 252, 247, 0.92), rgba(240, 244, 248, 0.95));
            color: var(--ink);
            font-weight: 600;
        }

        .stButton > button:hover {
            border-color: rgba(159, 63, 23, 0.3);
            color: var(--accent-strong);
        }

        .st-key-finish-conversation-button button {
            background: linear-gradient(180deg, #c73c2d, #9f2418);
            border-color: rgba(159, 36, 24, 0.45);
            color: #fff7f4;
        }

        .st-key-finish-conversation-button button:hover {
            border-color: rgba(123, 18, 9, 0.6);
            color: #fff7f4;
            box-shadow: 0 12px 24px rgba(159, 36, 24, 0.22);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render the page hero and current chat metadata."""

    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-eyebrow">PQRS Agent Front</div>
            <h1 class="hero-title">Chat de prueba para agentepqr</h1>
            <p class="hero-copy">
                Esta vista arranca la sesion con un boton dedicado para
                <code>POST /start</code> que envia solo el identificador. Cuando el backend devuelve
                <code>conversation_id</code>, el resto del intercambio sigue por
                <code>POST /chat</code> y el cierre por <code>POST /end</code>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="info-chip-row">
            <div class="info-chip">
                <label>Backend</label>
                <code>{st.session_state["api_base_url"]}</code>
            </div>
            <div class="info-chip">
                <label>ID cargado</label>
                <code>{st.session_state["selected_customer_id"] or "N/D"}</code>
            </div>
            <div class="info-chip">
                <label>ID en edicion</label>
                <code>{get_effective_draft_customer_id() or "N/D"}</code>
            </div>
            <div class="info-chip">
                <label>Conversation activa</label>
                <code>{st.session_state["conversation_id"]}</code>
            </div>
            <div class="info-chip">
                <label>Estado backend</label>
                <code>{st.session_state["conversation_status"] or "N/D"}</code>
            </div>
            <div class="info-chip">
                <label>Mensajes locales</label>
                <code>{len(st.session_state["messages"])}</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_view_navigation() -> None:
    """Render the app-level navigation between chat and metrics."""

    with st.sidebar:
        st.subheader("Vista")
        chat_type = "primary" if st.session_state["current_view"] == "chat" else "secondary"
        metrics_type = (
            "primary" if st.session_state["current_view"] == "metrics" else "secondary"
        )

        if st.button("Chat", key="nav-chat", type=chat_type, use_container_width=True):
            st.session_state["current_view"] = "chat"

        if st.button(
            "Metricas",
            key="nav-metrics",
            type=metrics_type,
            use_container_width=True,
        ):
            st.session_state["current_view"] = "metrics"

        benchmark_type = (
            "primary" if st.session_state["current_view"] == "benchmark" else "secondary"
        )
        if st.button(
            "Benchmark",
            key="nav-benchmark",
            type=benchmark_type,
            use_container_width=True,
        ):
            st.session_state["current_view"] = "benchmark"

        st.divider()


def render_chat_sidebar() -> None:
    """Render backend configuration, health checks, and conversation controls."""

    customer_options = load_embargo_customer_options(
        str(EMBARGOS_SAMPLE_PATH),
        build_file_cache_key(str(EMBARGOS_SAMPLE_PATH)),
    )
    customer_ids = [str(option["customer_id"]) for option in customer_options]
    customer_labels = {
        str(option["customer_id"]): str(option["label"])
        for option in customer_options
    }

    draft_customer_id = clean_string(st.session_state["draft_customer_id"])
    if draft_customer_id and draft_customer_id not in customer_ids:
        customer_ids = [draft_customer_id, *customer_ids]
        customer_labels[draft_customer_id] = (
            f"{draft_customer_id} | customer_id actual"
        )
    elif customer_ids and not draft_customer_id:
        st.session_state["draft_customer_id"] = customer_ids[0]

    effective_draft_customer_id = get_effective_draft_customer_id()

    with st.sidebar:
        st.subheader("Conexion")

        new_api_base_url = normalize_base_url(
            st.text_input(
                "Base URL",
                value=st.session_state["api_base_url"],
                placeholder="http://127.0.0.1:8000",
                help=(
                    "URL base del backend FastAPI. No incluyas `/start`, `/chat`, "
                    "`/end` ni `/health`."
                ),
            )
        )

        if new_api_base_url != st.session_state["api_base_url"]:
            st.session_state["api_base_url"] = new_api_base_url
            st.session_state["health_status"] = None
            st.session_state["health_message"] = ""

        if st.button("Probar /health", use_container_width=True):
            status, message = check_health(st.session_state["api_base_url"])
            st.session_state["health_status"] = status
            st.session_state["health_message"] = message

        health_status = st.session_state["health_status"]
        health_message = st.session_state["health_message"]

        if health_status == "success":
            st.success(health_message)
        elif health_status == "warning":
            st.warning(health_message)
        elif health_status == "error":
            st.error(health_message)
        else:
            st.caption("Usa `/health` para confirmar conectividad antes de empezar.")

        st.divider()
        st.subheader("Conversacion")

        notice = st.session_state.get("chat_notice")
        if isinstance(notice, dict):
            level = clean_string(notice.get("level")) or "success"
            message = clean_string(notice.get("message"))
            if message:
                if level == "error":
                    st.error(message)
                elif level == "warning":
                    st.warning(message)
                else:
                    st.success(message)
            st.session_state["chat_notice"] = None

        if customer_options:
            st.selectbox(
                "Caso de prueba",
                options=customer_ids,
                key="draft_customer_id",
                format_func=lambda customer_id: customer_labels[customer_id],
                on_change=clear_manual_draft_customer_id,
                help=(
                    "Clientes tomados del CSV de embargos que tienen varios productos "
                    "para probar consultas mas completas."
                ),
            )
            st.caption(f"IDs detectados en el CSV: {len(customer_options)}")
        else:
            st.caption("No encontre casos multi-producto en el CSV. Usa un ID manual.")

        st.text_input(
            "Customer ID manual",
            key="draft_customer_id_manual",
            placeholder="Escribe un customer_id si no quieres usar la lista",
            help=(
                "Si escribes un valor aqui, ese ID tendra prioridad sobre la lista actual. "
                "Deja el campo vacio o cambia la lista para volver al CSV."
            ),
        )

        effective_draft_customer_id = get_effective_draft_customer_id()

        selected_customer = find_customer_option(
            customer_options,
            effective_draft_customer_id,
        )
        available_products = selected_customer["product_ids"] if selected_customer else []
        if available_products and st.session_state["draft_product_id"] not in available_products:
            st.session_state["draft_product_id"] = str(available_products[0])
        elif not available_products:
            st.session_state["draft_product_id"] = ""

        if available_products:
            st.selectbox(
                "Producto de referencia",
                options=available_products,
                key="draft_product_id",
                help=(
                    "Esta seleccion es solo una guia visual para la consulta. "
                    "No viaja al backend: solo te ayuda a contextualizar contratos y "
                    "productos del customer_id elegido."
                ),
            )
            selected_product = next(
                (
                    option
                    for option in selected_customer["product_options"]
                    if option["product_id"] == st.session_state["draft_product_id"]
                ),
                None,
            )
            if selected_product:
                contract_preview = ", ".join(selected_product["contract_ids"][:4])
                if len(selected_product["contract_ids"]) > 4:
                    contract_preview = f"{contract_preview}..."
                st.caption(
                    f"Contratos del producto {selected_product['product_id']}: "
                    f"`{contract_preview or 'Sin contratos visibles'}`"
                )

        st.caption("ID que se enviara a `/start`")
        st.code(effective_draft_customer_id or "Selecciona o escribe un customer_id")
        st.caption(
            "Compatibilidad: primero se intenta `/start` con `user_id`; si el backend "
            "responde como el contrato antiguo, se reintenta con `conversation_id`. "
            "En ambos casos sin `content`."
        )

        active_conversation_id = clean_string(st.session_state["conversation_id"])
        st.caption("Conversation ID activo")
        st.code(active_conversation_id or "Aun no lo devuelve el backend")

        apply_existing = st.button("Cargar ID", use_container_width=True)
        start_new = st.button("Nueva conversacion", use_container_width=True)

        if apply_existing:
            if not effective_draft_customer_id:
                st.error("Debes elegir un `customer_id` antes de consultar.")
            else:
                reset_chat(
                    customer_id=effective_draft_customer_id,
                )
                st.session_state["chat_notice"] = {
                    "level": "success",
                    "message": (
                        "ID cargado. Ahora usa el boton `Iniciar conversacion (/start)` "
                        "para obtener el `conversation_id` del backend."
                    ),
                }
                st.rerun()

        if start_new:
            if not effective_draft_customer_id:
                st.error("Debes elegir un `customer_id` antes de crear una conversacion.")
            else:
                reset_chat(customer_id=effective_draft_customer_id)
                st.session_state["chat_notice"] = {
                    "level": "success",
                    "message": (
                        "Se limpio el contexto local. El proximo mensaje abrira una "
                        "nueva conversacion en el backend para este ID."
                    ),
                }
                st.rerun()

        st.caption(
            "La lista carga el ID inicial. Luego el boton de inicio llama a `/start` "
            "y el front conserva el `conversation_id` exacto que devuelve el backend "
            "para reutilizarlo en `/chat` y `/end`. Si `/start` sigue pidiendo "
            "`conversation_id`, el front lo resuelve automaticamente en modo compatibilidad."
        )


def render_metrics_sidebar() -> None:
    """Render the controls specific to the metrics view."""

    with st.sidebar:
        st.subheader("Fuente de metricas")
        st.session_state["metrics_source"] = st.text_input(
            "Endpoint de OpenSearch",
            value=st.session_state["metrics_source"],
            help=(
                "URL base de OpenSearch, por ejemplo `https://localhost:9200`."
            ),
        ).strip()
        st.caption(
            "Esta vista solo usa OpenSearch. "
            "Por defecto toma el endpoint configurado en el backend o `https://localhost:9200`."
        )

        st.divider()
        st.subheader("Lectura")
        st.button(
            "Refrescar metricas",
            key="refresh-metrics",
            use_container_width=True,
        )


CHECKED_MARK = "☑"
UNCHECKED_MARK = "☐"

REPORT_EMPTY_LABEL = "Reportar seleccionados"


def split_multi_select_option(option: dict) -> tuple[str, str, bool | None]:
    """Return (key, label, checked) for one option of a multi_select step.

    ``checked`` is ``None`` for the fixed action buttons ("Ver mas
    movimientos", "Reportar...", "No encuentro..."), which the backend sends
    without a checkbox mark.
    """

    option_key = clean_string(option.get("key"))
    option_label = clean_string(option.get("label"))

    if option_label.startswith((CHECKED_MARK, UNCHECKED_MARK)):
        return (
            option_key,
            option_label[1:].strip(),
            option_label.startswith(CHECKED_MARK),
        )

    return option_key, option_label, None


def render_multi_select_options(
    message_options: list[dict],
    index: int,
) -> dict[str, str] | None:
    """Render a multi_select step as checkboxes plus its fixed action buttons.

    The backend owns the selection: every checkbox toggle is sent as the
    option key of that row, and the reply comes back with the marks updated.
    So the checkbox is painted from the backend mark, and a click is detected
    as "the widget no longer agrees with what the backend said".
    """

    st.caption(
        "Selecciona uno o varios cobros duplicados. "
        "La seleccion se conserva al cambiar de pagina."
    )

    queued: dict[str, str] | None = None
    actions: list[tuple[int, str, str]] = []

    for option_position, option in enumerate(message_options):
        option_key, option_label, checked = split_multi_select_option(option)
        if not option_key or not option_label:
            continue

        if checked is None:
            actions.append((option_position, option_key, option_label))
            continue

        widget_checked = st.checkbox(
            option_label,
            value=checked,
            key=f"assistant-multi-{index}-{option_position}-{option_key}",
        )

        # Solo el primer cambio se envia: el backend responde con un mensaje
        # nuevo y el resto de casillas se vuelve a pintar desde esa respuesta.
        if queued is None and widget_checked != checked:
            queued = {
                "content": option_key,
                "display_content": option_label,
            }

    if queued is not None:
        return queued

    for option_position, option_key, option_label in actions:
        is_report = option_key == "reportar_seleccionados"
        # La seleccion vive en el backend y sobrevive a la paginacion, asi que
        # el conteo NO se puede sacar de las casillas visibles: el backend lo
        # publica en la propia etiqueta ("Reportar 2 cobros") y deja la
        # generica cuando no hay nada marcado.
        nothing_selected = is_report and option_label == REPORT_EMPTY_LABEL
        if st.button(
            option_label,
            key=f"assistant-option-{index}-{option_position}-{option_key}",
            type="primary" if is_report else "secondary",
            use_container_width=True,
            disabled=nothing_selected,
        ):
            queued = {
                "content": option_key,
                "display_content": option_label,
            }

    return queued


def render_messages() -> dict[str, str] | None:
    """Render the current local message history and return an option click if any."""

    if not st.session_state["messages"]:
        st.markdown(
            """
            <div class="empty-state">
                Todavia no hay mensajes en esta sesion. Carga un ID, usa el boton
                <code>Iniciar conversacion (/start)</code> y, cuando el backend responda
                con <code>conversation_id</code>, seguimos desde el chat.
            </div>
            """,
            unsafe_allow_html=True,
        )

    queued_prompt: dict[str, str] | None = None
    actionable_index = len(st.session_state["messages"]) - 1

    for index, message in enumerate(st.session_state["messages"]):
        with st.chat_message(message["role"]):
            if message.get("kind") == "error":
                st.error(message["content"])
            elif message.get("kind") == "pending":
                st.info(message["content"])
            else:
                st.markdown(message["content"])
                message_options = message.get("options") or []
                message_input_type = clean_string(message.get("input_type"))
                is_actionable = index == actionable_index and message["role"] == "assistant"

                if queued_prompt is None and is_actionable and message_options:
                    if message_input_type == "multi_select":
                        queued_prompt = render_multi_select_options(
                            message_options,
                            index,
                        )
                    else:
                        st.caption("Opciones sugeridas")

                        for option_position, option in enumerate(message_options):
                            option_key = clean_string(option.get("key"))
                            option_label = clean_string(option.get("label"))
                            if not option_key or not option_label:
                                continue

                            if st.button(
                                option_label,
                                key=(
                                    f"assistant-option-{index}-"
                                    f"{option_position}-{option_key}"
                                ),
                                use_container_width=True,
                            ):
                                queued_prompt = {
                                    "content": option_key,
                                    "display_content": option_label,
                                }

                if (
                    queued_prompt is None
                    and is_actionable
                    and not message_options
                    and message.get("input_type") == "date"
                ):
                    picked_date = st.date_input(
                        "Selecciona la fecha",
                        key=f"assistant-date-{index}",
                        format="DD/MM/YYYY",
                    )
                    if st.button(
                        "Continuar",
                        key=f"assistant-date-confirm-{index}",
                        type="primary",
                        use_container_width=True,
                    ):
                        formatted_date = picked_date.strftime("%d/%m/%Y")
                        queued_prompt = {
                            "content": formatted_date,
                            "display_content": formatted_date,
                        }

                if (
                    queued_prompt is None
                    and is_actionable
                    and not message_options
                    and message.get("input_type") == "number"
                ):
                    monto = st.number_input(
                        "Monto",
                        key=f"assistant-number-{index}",
                        min_value=0,
                        step=1000,
                        format="%d",
                    )
                    if st.button(
                        "Continuar",
                        key=f"assistant-number-confirm-{index}",
                        type="primary",
                        use_container_width=True,
                    ):
                        raw_amount = int(monto)
                        queued_prompt = {
                            "content": str(raw_amount),
                            "display_content": format_cop_currency(raw_amount),
                        }

    return queued_prompt


def render_chat_page() -> None:
    """Render the chat experience."""

    render_chat_sidebar()
    render_header()

    action_col, info_col = st.columns([1.2, 4.8])
    with action_col:
        if st.button(
            "Ver metricas",
            key="open-metrics-from-chat",
            use_container_width=True,
        ):
            st.session_state["current_view"] = "metrics"
            st.rerun()

    with info_col:
        st.caption(
            "Desde la vista de metricas puedes revisar tokens, tiempos, estados y conversaciones recientes."
        )

    conversation_started = has_active_conversation()
    waiting_for_polling = has_pending_polling_message()
    if conversation_started:
        st.markdown("**Conversacion activa**")
        poll_col, close_col, meta_col = st.columns([2.1, 1.9, 3.0])
        with poll_col:
            if st.button(
                "Consultar respuesta",
                key="poll-pending-message-button",
                use_container_width=True,
            ):
                handle_polling_request()
                st.rerun()

        with close_col:
            if st.button(
                "Finalizar conversacion",
                key="finish-conversation-button",
                type="primary",
                use_container_width=True,
            ):
                close_active_conversation()
                st.rerun()

        with meta_col:
            if waiting_for_polling:
                st.caption(
                    "El backend esta procesando el ultimo turno. Usa el boton de polling "
                    "para traer el mensaje pendiente cuando ya este listo."
                )
            else:
                st.caption(
                    "Este boton rojo envia `POST /end` usando el `conversation_id` actual "
                    "y finaliza la conversacion en el backend."
                )

    queued_prompt = render_messages()
    if queued_prompt and conversation_started:
        handle_user_prompt(queued_prompt)
        st.rerun()
        return

    if not conversation_started:
        st.markdown("**Inicio**")
        st.caption(
            "Este boton hace la llamada inicial a `/start` sin `content`. Despues "
            "el chat seguira solo con el `conversation_id` devuelto por el backend."
        )

        if st.button(
            "Iniciar conversacion (/start)",
            key="start-conversation-button",
            type="primary",
            use_container_width=True,
        ):
            handle_start_conversation()
            st.rerun()

        st.info(
            "El cuadro de chat se habilita cuando el backend responda con un "
            "`conversation_id` activo."
        )
        return

    chat_input = st.chat_input(
        "Escribe tu mensaje para agentepqr",
        disabled=waiting_for_polling,
    )
    if chat_input:
        handle_user_prompt(
            {
                "content": chat_input,
                "display_content": chat_input,
            }
        )
        st.rerun()


def render_metrics_page() -> None:
    """Render the operational metrics view based on persisted agent data."""

    render_metrics_sidebar()
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-eyebrow">Metricas</div>
            <h1 class="hero-title">Panel operativo de agentepqr</h1>
            <p class="hero-copy">
                Esta vista lee OpenSearch para resumir volumen, uso de tokens,
                tiempos de respuesta y estado de las conversaciones.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_col, details_col = st.columns([1.2, 4.8])
    with action_col:
        if st.button("Volver al chat", key="back-to-chat", use_container_width=True):
            st.session_state["current_view"] = "chat"
            st.rerun()

    try:
        snapshot = build_metrics_snapshot(st.session_state["metrics_source"])
    except ValueError as exc:
        st.error(str(exc))
        return

    with details_col:
        st.caption(
            f"Fuente actual: `{snapshot['source']}` (`{snapshot['source_type']}`). "
            f"Ultima actividad detectada: `{format_timestamp(snapshot['latest_activity'])}`."
        )
        if snapshot["known_sources"]:
            st.caption(
                "Endpoints detectados: "
                + " | ".join(f"`{path}`" for path in snapshot["known_sources"])
            )

    if snapshot["missing_sources"]:
        missing = ", ".join(snapshot["missing_sources"])
        st.warning(
            f"Faltan indices en OpenSearch: {missing}. "
            "Las metricas visibles se calcularon con lo que si estaba disponible."
        )

    top_row = st.columns(4)
    top_row[0].metric("Conversaciones", f"{snapshot['conversation_count']:,}")
    top_row[1].metric("Activas", f"{snapshot['active_count']:,}")
    top_row[2].metric("Cerradas", f"{snapshot['closed_count']:,}")
    top_row[3].metric("Fallidas", f"{snapshot['error_count']:,}")

    second_row = st.columns(4)
    second_row[0].metric("Mensajes", f"{snapshot['message_count']:,}")
    second_row[1].metric("Tokens totales", f"{snapshot['total_tokens']:,}")
    second_row[2].metric(
        "Resp. prom. asistente",
        format_duration_ms(snapshot["avg_assistant_response_ms"]),
    )
    second_row[3].metric(
        "P95 resp. asistente",
        format_duration_ms(snapshot["p95_assistant_response_ms"]),
    )

    third_row = st.columns(4)
    third_row[0].metric(
        "Turns con modelo",
        f"{snapshot['turns_with_model_usage']:,}",
    )
    third_row[1].metric(
        "Input tokens",
        f"{snapshot['total_input_tokens']:,}",
    )
    third_row[2].metric(
        "Output tokens",
        f"{snapshot['total_output_tokens']:,}",
    )
    third_row[3].metric(
        "Latencia prom. turno",
        format_duration_ms(snapshot["avg_user_turn_ms"]),
    )

    st.caption(
        "La metrica `Fallidas` se calcula con conversaciones cuyo `status` persistido es `Error`. "
        "Si el backend no actualiza ese estado, el contador puede quedarse en cero aunque haya fallos transitorios."
    )

    st.subheader("Workflows")
    if snapshot["workflow_rows"]:
        st.dataframe(snapshot["workflow_rows"], use_container_width=True, hide_index=True)
    else:
        st.info("Todavia no hay conversaciones persistidas para resumir por workflow.")

    st.subheader("Conversaciones recientes")
    if snapshot["recent_rows"]:
        st.dataframe(snapshot["recent_rows"], use_container_width=True, hide_index=True)
    else:
        st.info("Aun no hay conversaciones persistidas en la fuente de datos seleccionada.")

    st.subheader("Conversaciones fallidas")
    if snapshot["error_rows"]:
        st.dataframe(snapshot["error_rows"], use_container_width=True, hide_index=True)
    else:
        st.info("No hay conversaciones con `status = Error` en los datos actuales.")


def _repaints_an_existing_message(result: dict[str, Any]) -> bool:
    """Whether the backend answered with a message the history already holds."""

    payload = result.get("message_payload") or {}
    message_id = clean_string(payload.get("message_id"))
    if not message_id:
        return False

    return any(
        message.get("message_id") == message_id
        for message in st.session_state["messages"]
    )


def add_chat_message(
    role: str,
    content: str,
    *,
    kind: str = "message",
    options: list[dict[str, str]] | None = None,
    timestamp: str | None = None,
    input_type: str | None = None,
    message_id: str | None = None,
) -> None:
    """Add a message to the local UI history, or update it if already there.

    The backend answers a step that repaints itself in place (the multi_select
    selector toggling a box or changing page) with the SAME ``message_id`` it
    already sent. That message is then REPLACED, so the selector stays a single
    card instead of piling up one copy of the listing per click.
    """

    message = {
        "role": role,
        "content": content,
        "kind": kind,
        "options": options or [],
        "timestamp": timestamp,
        "input_type": input_type,
        "message_id": message_id,
    }

    if message_id:
        for position, existing in enumerate(st.session_state["messages"]):
            if existing.get("message_id") == message_id:
                st.session_state["messages"][position] = message
                return

    st.session_state["messages"].append(message)


def resolve_prompt_request(prompt: str | dict[str, str]) -> tuple[str, str]:
    """Resolve the backend content plus the user-visible text for a prompt request."""

    if isinstance(prompt, str):
        normalized_prompt = prompt.strip()
        return normalized_prompt, normalized_prompt

    content = clean_string(prompt.get("content"))
    display_content = clean_string(prompt.get("display_content")) or content
    return content, display_content


def apply_successful_backend_result(result: dict[str, Any]) -> None:
    """Persist a successful backend response in the local UI state."""

    clear_pending_polling_state()
    st.session_state["conversation_id"] = result["conversation_id"]
    st.session_state["conversation_status"] = result.get("conversation_status")
    if result.get("compat_mode") == "start_requires_conversation_id":
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": (
                "El backend activo no esta usando el contrato publicado en `swagger.json` "
                "para `/start`. El front aplico un modo compatibilidad con "
                "`conversation_id` y la conversacion continuo bien."
            ),
        }

    returned_customer_id, _ = parse_conversation_id(result["conversation_id"])
    if returned_customer_id:
        st.session_state["selected_customer_id"] = returned_customer_id
        queue_draft_customer_id_update(returned_customer_id)

    message_payload = result.get("message_payload") or {
        "content": result["message"],
        "options": [],
        "timestamp": None,
    }
    add_chat_message(
        "assistant",
        message_payload["content"],
        options=message_payload.get("options"),
        timestamp=message_payload.get("timestamp"),
        input_type=message_payload.get("input_type"),
        message_id=message_payload.get("message_id"),
    )


def handle_start_conversation() -> None:
    """Explicitly open a backend conversation through `POST /start`."""

    active_customer_id = clean_string(st.session_state.get("selected_customer_id"))
    if not active_customer_id:
        st.session_state["chat_notice"] = {
            "level": "error",
            "message": "Debes cargar un `user_id` antes de iniciar la conversacion.",
        }
        return

    with st.spinner("Iniciando conversacion con agentepqr..."):
        result = send_conversation_message(
            base_url=st.session_state["api_base_url"],
            conversation_id=clean_string(st.session_state.get("conversation_id")),
            customer_id=active_customer_id,
            content=None,
            use_start=True,
        )

    if result["ok"]:
        apply_successful_backend_result(result)
        return

    add_chat_message("assistant", result["message"], kind="error")


def handle_polling_request() -> None:
    """Query the backend for a response that is still being processed."""

    active_conversation_id = clean_string(
        st.session_state.get("pending_polling_conversation_id")
        or st.session_state.get("conversation_id")
    )
    if not active_conversation_id:
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": "No hay un mensaje pendiente para consultar por polling.",
        }
        return

    with st.spinner("Consultando mensaje pendiente..."):
        result = poll_conversation_message(
            base_url=st.session_state["api_base_url"],
            conversation_id=active_conversation_id,
        )

    if result["ok"] and result.get("pending"):
        mark_conversation_as_processing(active_conversation_id)
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": "El backend sigue pensando la respuesta. Puedes volver a consultar en un momento.",
        }
        return

    if result["ok"]:
        apply_successful_backend_result(result)
        st.session_state["chat_notice"] = {
            "level": "success",
            "message": "Llegó la respuesta pendiente del backend.",
        }
        return

    add_chat_message("assistant", result["message"], kind="error")


def handle_user_prompt(prompt: str | dict[str, str]) -> None:
    """Send a prompt to the backend and update the rendered conversation."""

    content, display_content = resolve_prompt_request(prompt)
    if not content:
        return

    active_customer_id = clean_string(st.session_state.get("selected_customer_id"))
    if not active_customer_id:
        st.session_state["chat_notice"] = {
            "level": "error",
            "message": "Debes cargar un `user_id` antes de enviar mensajes al backend.",
        }
        return

    active_conversation_id = clean_string(st.session_state.get("conversation_id"))
    if not has_active_conversation():
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": (
                "Primero usa el boton `Iniciar conversacion (/start)` para obtener "
                "el `conversation_id` del backend."
            ),
        }
        return

    if has_pending_polling_message():
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": (
                "Hay una respuesta pendiente del backend. Usa `Consultar mensaje en espera` "
                "antes de enviar otro mensaje."
            ),
        }
        return

    add_chat_message("user", display_content)
    echoed_click_position = len(st.session_state["messages"]) - 1

    with st.spinner("Consultando agentepqr..."):
        result = send_message_request(
            base_url=st.session_state["api_base_url"],
            endpoint_path="/chat",
            conversation_id=active_conversation_id,
            customer_id=active_customer_id,
            content=content,
        )

    # Marcar una casilla no es un turno de conversacion. Si el backend responde
    # repintando la tarjeta que ya estaba (mismo message_id), el clic tampoco
    # tiene por que quedar como mensaje del cliente.
    if result["ok"] and _repaints_an_existing_message(result):
        st.session_state["messages"].pop(echoed_click_position)

    if result["ok"] and result.get("pending"):
        mark_conversation_as_processing(active_conversation_id)
        st.session_state["chat_notice"] = {
            "level": "warning",
            "message": "El backend respondio `204 No Content`: sigue procesando tu mensaje.",
        }
        return

    if result["ok"]:
        apply_successful_backend_result(result)
        return

    add_chat_message("assistant", result["message"], kind="error")


def main() -> None:
    """Run the Streamlit chat frontend."""

    st.set_page_config(
        page_title="PQRS Agent Front",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_session_state()
    render_theme()
    render_view_navigation()

    if st.session_state["current_view"] == "metrics":
        render_metrics_page()
        return

    if st.session_state["current_view"] == "benchmark":
        render_benchmark_page()
        return

    render_chat_page()


if __name__ == "__main__":
    main()
