from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import requests
import urllib3

APP_DIR = Path(__file__).resolve().parent
KNOWN_OPENSEARCH_ENV_FILES = [
    APP_DIR.parent / "agentepqr" / "co_pqrs_back_agent" / ".env",
]


def format_duration_ms(value: float | int | None) -> str:
    """Format a duration in milliseconds for compact display."""

    if value is None:
        return "N/D"

    duration = float(value)
    if duration < 1000:
        return f"{duration:.0f} ms"

    return f"{duration / 1000:.2f} s"


def format_timestamp(value: datetime | None) -> str:
    """Format a timestamp for UI tables and summary cards."""

    if value is None:
        return "N/D"

    normalized = value.astimezone()
    return normalized.strftime("%Y-%m-%d %H:%M:%S")


def build_metrics_snapshot(source: str | None = None) -> dict[str, Any]:
    """Build the metrics snapshot from OpenSearch only."""

    source_value = (source or DEFAULT_METRICS_SOURCE).strip()
    if not _looks_like_url(source_value):
        raise ValueError(
            "La fuente de metricas debe ser una URL de OpenSearch, por ejemplo "
            "`https://localhost:9200`."
        )

    settings = _resolve_opensearch_settings(source_value)
    conversations, conversations_found = _load_opensearch_documents(
        settings,
        settings["conversations_index"],
    )
    messages, messages_found = _load_opensearch_documents(
        settings,
        settings["messages_index"],
    )

    missing_sources: list[str] = []
    if not conversations_found:
        missing_sources.append(settings["conversations_index"])
    if not messages_found:
        missing_sources.append(settings["messages_index"])

    return _build_snapshot_from_records(
        conversations=conversations,
        messages=messages,
        source_label=settings["endpoint"],
        source_details={
            "conversations_index": settings["conversations_index"],
            "messages_index": settings["messages_index"],
            "known_sources": _known_metric_sources(settings["endpoint"]),
            "missing_sources": missing_sources,
            "source_type": "opensearch",
        },
    )


def _build_snapshot_from_records(
    *,
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    source_label: str,
    source_details: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate metrics from normalized conversation and message records."""

    status_counts = Counter(
        str(conversation.get("status") or "Sin estado")
        for conversation in conversations
    )
    workflow_counts = Counter(
        _resolve_workflow_name(conversation)
        for conversation in conversations
    )

    messages_by_conversation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        conversation_id = str(message.get("conversation_id") or "Sin ID")
        messages_by_conversation[conversation_id].append(message)

    assistant_messages = [
        message
        for message in messages
        if str(message.get("role") or "").lower() == "assistant"
    ]
    user_messages = [
        message
        for message in messages
        if str(message.get("role") or "").lower() == "user"
    ]

    assistant_response_durations = [
        duration
        for duration in (_message_duration_ms(message) for message in assistant_messages)
        if duration is not None
    ]
    user_turn_durations = [
        duration
        for duration in (_message_duration_ms(message) for message in user_messages)
        if duration is not None
    ]

    total_input_tokens = sum(
        _message_token_value(message, "input_tokens")
        for message in assistant_messages
    )
    total_output_tokens = sum(
        _message_token_value(message, "output_tokens")
        for message in assistant_messages
    )
    total_tokens = sum(
        _message_token_value(message, "total_tokens")
        for message in assistant_messages
    )
    turns_with_model_usage = sum(
        1
        for message in assistant_messages
        if _message_token_value(message, "total_tokens") > 0
    )

    workflow_tokens: Counter[str] = Counter()
    workflow_durations: dict[str, list[int]] = defaultdict(list)
    workflow_messages: Counter[str] = Counter()
    workflow_assistant_turns: Counter[str] = Counter()

    activity_dates = [
        parsed_date
        for parsed_date in (
            _parse_datetime(conversation.get("last_msg_date"))
            for conversation in conversations
        )
        if parsed_date is not None
    ]
    latest_activity = max(activity_dates, default=None)

    conversation_rows: list[dict[str, Any]] = []
    for conversation in conversations:
        conversation_id = str(conversation.get("conversation_id") or "Sin ID")
        workflow_name = _resolve_workflow_name(conversation)
        status = str(conversation.get("status") or "Sin estado")
        conversation_messages = messages_by_conversation.get(conversation_id, [])
        conversation_assistant_messages = [
            message
            for message in conversation_messages
            if str(message.get("role") or "").lower() == "assistant"
        ]
        conversation_durations = [
            duration
            for duration in (
                _message_duration_ms(message)
                for message in conversation_assistant_messages
            )
            if duration is not None
        ]
        conversation_total_tokens = sum(
            _message_token_value(message, "total_tokens")
            for message in conversation_assistant_messages
        )
        average_response_ms = _mean_or_none(conversation_durations)
        max_response_ms = max(conversation_durations, default=None)
        last_msg_date = _parse_datetime(conversation.get("last_msg_date"))

        workflow_tokens[workflow_name] += conversation_total_tokens
        workflow_messages[workflow_name] += len(conversation_messages)
        workflow_assistant_turns[workflow_name] += len(conversation_assistant_messages)
        workflow_durations[workflow_name].extend(conversation_durations)

        conversation_rows.append(
            {
                "_sort_last_msg_ts": (
                    last_msg_date.timestamp() if last_msg_date is not None else float("-inf")
                ),
                "Conversation ID": conversation_id,
                "Workflow": workflow_name,
                "Estado": status,
                "Paso actual": str(conversation.get("current_step") or "N/D"),
                "Mensajes": len(conversation_messages),
                "Turns asistente": len(conversation_assistant_messages),
                "Tokens": conversation_total_tokens,
                "Resp. prom. asistente": format_duration_ms(average_response_ms),
                "Resp. max. asistente": format_duration_ms(max_response_ms),
                "Ultima actividad": format_timestamp(last_msg_date),
            }
        )

    conversation_rows.sort(
        key=lambda row: row["_sort_last_msg_ts"],
        reverse=True,
    )

    workflow_rows = [
        {
            "Workflow": workflow_name,
            "Conversaciones": workflow_counts[workflow_name],
            "Mensajes": workflow_messages[workflow_name],
            "Turns asistente": workflow_assistant_turns[workflow_name],
            "Tokens": workflow_tokens[workflow_name],
            "Resp. prom. asistente": format_duration_ms(
                _mean_or_none(workflow_durations[workflow_name])
            ),
        }
        for workflow_name, _ in workflow_counts.most_common()
    ]

    error_rows = [
        {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        for row in conversation_rows
        if row["Estado"] == "Error"
    ]
    recent_rows = [
        {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        for row in conversation_rows[:10]
    ]

    return {
        "source": source_label,
        "conversations_index": source_details["conversations_index"],
        "messages_index": source_details["messages_index"],
        "known_sources": source_details["known_sources"],
        "missing_sources": source_details["missing_sources"],
        "source_type": source_details["source_type"],
        "conversation_count": len(conversations),
        "message_count": len(messages),
        "assistant_message_count": len(assistant_messages),
        "user_message_count": len(user_messages),
        "active_count": status_counts.get("Active", 0),
        "closed_count": status_counts.get("Closed", 0),
        "error_count": status_counts.get("Error", 0),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "turns_with_model_usage": turns_with_model_usage,
        "avg_assistant_response_ms": _mean_or_none(assistant_response_durations),
        "p95_assistant_response_ms": _percentile(assistant_response_durations, 95),
        "avg_user_turn_ms": _mean_or_none(user_turn_durations),
        "latest_activity": latest_activity,
        "workflow_rows": workflow_rows,
        "recent_rows": recent_rows,
        "error_rows": error_rows,
    }


def _load_opensearch_documents(
    settings: dict[str, Any],
    index_name: str,
    *,
    page_size: int = 500,
) -> tuple[list[dict[str, Any]], bool]:
    """Load all documents from an OpenSearch index using `search_after` paging."""

    if not settings["verify_ssl"]:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    endpoint = settings["endpoint"].rstrip("/")
    url = f"{endpoint}/{index_name}/_search"
    auth = (settings["user"], settings["password"])
    verify_ssl = settings["verify_ssl"]
    timeout = _opensearch_metrics_timeout(settings)

    documents: list[dict[str, Any]] = []
    search_after: list[Any] | None = None

    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "track_total_hits": True,
            "sort": [{"_id": {"order": "asc"}}],
        }
        if search_after is not None:
            body["search_after"] = search_after

        try:
            response = requests.post(
                url,
                auth=auth,
                verify=verify_ssl,
                timeout=timeout,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise ValueError(
                "No pude leer OpenSearch dentro del tiempo esperado. "
                f"Indice: `{index_name}`. Detalle: {exc}"
            ) from exc

        if response.status_code == 404:
            return [], False

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(
                f"No pude leer el indice `{index_name}` en OpenSearch: {exc}"
            ) from exc

        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        if not hits:
            break

        documents.extend(
            hit["_source"]
            for hit in hits
            if isinstance(hit.get("_source"), dict)
        )

        search_after = hits[-1].get("sort")
        if len(hits) < page_size or not search_after:
            break

    return documents, True


def _opensearch_metrics_timeout(settings: dict[str, Any]) -> tuple[float, float]:
    """Return a more forgiving `(connect, read)` timeout for metrics snapshot reads."""

    base_timeout = float(settings.get("timeout", 10.0) or 10.0)
    connect_timeout = min(max(base_timeout, 10.0), 20.0)
    read_timeout = max(base_timeout, 60.0)
    return (connect_timeout, read_timeout)


def _resolve_opensearch_settings(endpoint_override: str | None = None) -> dict[str, Any]:
    """Build OpenSearch settings from known `.env` files plus sane local defaults."""

    settings = {
        "endpoint": endpoint_override or "https://localhost:9200",
        "user": "admin",
        "password": "admin",
        "verify_ssl": False,
        "conversations_index": "conversations-reference",
        "messages_index": "conversations-messages",
        "timeout": 10.0,
    }

    for env_path in KNOWN_OPENSEARCH_ENV_FILES:
        if not env_path.exists():
            continue

        constants = _load_simple_env_file(env_path)
        settings.update(
            {
                "endpoint": endpoint_override
                or constants.get("OPENSEARCH_ENDPOINT", settings["endpoint"]),
                "user": constants.get("OPENSEARCH_USER", settings["user"]),
                "password": constants.get("OPENSEARCH_PASSWORD", settings["password"]),
                "verify_ssl": _parse_bool(
                    constants.get("OPENSEARCH_VERIFY_SSL"),
                    default=settings["verify_ssl"],
                ),
                "conversations_index": constants.get(
                    "OPENSEARCH_CONVERSATIONS_INDEX",
                    settings["conversations_index"],
                ),
                "messages_index": constants.get(
                    "OPENSEARCH_MESSAGES_INDEX",
                    settings["messages_index"],
                ),
                "timeout": float(
                    constants.get("OPENSEARCH_TIMEOUT", str(settings["timeout"]))
                ),
            }
        )
        break

    return settings


def _detect_default_metrics_source() -> str:
    """Choose the preferred metrics source for the current local setup."""

    return _resolve_opensearch_settings()["endpoint"]


def _known_metric_sources(current_endpoint: str | None = None) -> list[str]:
    """Return the visible OpenSearch endpoints to help the UI explain what it found."""

    sources: list[str] = []
    default_endpoint = _resolve_opensearch_settings()["endpoint"]
    for candidate in (current_endpoint, default_endpoint):
        if candidate and candidate not in sources:
            sources.append(candidate)

    return sources


def _looks_like_url(value: str) -> bool:
    """Return whether the source string looks like an HTTP endpoint."""

    normalized = value.strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def _resolve_workflow_name(conversation: dict[str, Any]) -> str:
    """Resolve workflow names from persisted data without hard-coded flow lists."""

    workflow_name = _clean_string(conversation.get("workflow"))
    if workflow_name:
        return workflow_name

    flow_answers = conversation.get("flow_answers")
    if isinstance(flow_answers, dict):
        for key in ("workflow", "workflow_name", "flow_name"):
            candidate = _clean_string(flow_answers.get(key))
            if candidate:
                return candidate

    captured_data = conversation.get("captured_data")
    if isinstance(captured_data, dict):
        for key in ("workflow", "workflow_name", "flow_name"):
            candidate = _clean_string(captured_data.get(key))
            if candidate:
                return candidate

    return "Sin workflow"


def _clean_string(value: Any) -> str:
    """Return a trimmed string representation when the value is meaningful."""

    if value is None:
        return ""

    return str(value).strip()


def _load_simple_env_file(path: Path) -> dict[str, str]:
    """Load a simple `.env` file without external dependencies."""

    constants: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        constants[key.strip()] = value.strip().strip('"').strip("'")

    return constants


def _message_token_value(message: dict[str, Any], field_name: str) -> int:
    """Read a token field from a message record."""

    tokens = message.get("tokens")
    if not isinstance(tokens, dict):
        return 0

    return _as_int(tokens.get(field_name))


def _message_duration_ms(message: dict[str, Any]) -> int | None:
    """Extract the persisted duration from a message timing payload."""

    timing = message.get("timing")
    if not isinstance(timing, dict):
        return None

    raw_duration = timing.get("total_duration_ms")
    if raw_duration is None:
        return None

    return _as_int(raw_duration)


def _parse_datetime(value: Any) -> datetime | None:
    """Parse persisted ISO datetimes from the agent store."""

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_bool(value: str | None, *, default: bool) -> bool:
    """Parse a boolean-like environment variable value."""

    if value is None:
        return default

    return value.strip().casefold() not in {"0", "false", "no", "off"}


def _as_int(value: Any) -> int:
    """Convert numeric-looking values into integers."""

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0

    return 0


def _mean_or_none(values: list[int]) -> float | None:
    """Return the arithmetic mean or None when there is no data."""

    if not values:
        return None

    return mean(values)


def _percentile(values: list[int], percentile: int) -> int | None:
    """Return a compact percentile approximation for the provided values."""

    if not values:
        return None

    ordered = sorted(values)
    position = max(math.ceil(len(ordered) * (percentile / 100)) - 1, 0)
    return ordered[position]


DEFAULT_METRICS_SOURCE = (
    os.getenv("PQRS_AGENT_METRICS_SOURCE")
    or _detect_default_metrics_source()
)
