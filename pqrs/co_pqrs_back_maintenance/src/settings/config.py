from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from classes.models import Settings


def load_settings() -> Settings:
    load_dotenv()

    raw_hosts = read_required_env("OPENSEARCH_HOSTS")
    hosts, embedded_auth = parse_hosts(raw_hosts)

    username = os.getenv("OPENSEARCH_USERNAME")
    password = os.getenv("OPENSEARCH_PASSWORD")
    http_auth = embedded_auth

    if username:
        http_auth = (username, password or "")

    return Settings(
        hosts=hosts,
        http_auth=http_auth,
        verify_certs=parse_bool_env("OPENSEARCH_VERIFY_CERTS", default=True),
        timeout_seconds=parse_int_env("OPENSEARCH_TIMEOUT_SECONDS", default=30),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
        conversations_index=first_env(
            "OPENSEARCH_CONVERSATIONS_INDEX",
            "CONVERSATIONS_INDEX",
            default="conversations",
        ),
        messages_index=first_env(
            "OPENSEARCH_MESSAGES_INDEX",
            "MESSAGES_INDEX",
            default="messages",
        ),
        output_dir=Path(os.getenv("OUTPUT_DIR", "./output")),
        batch_size=parse_int_env("BATCH_SIZE", default=250),
        scroll_keepalive=os.getenv("SCROLL_KEEPALIVE", "2m"),
        inactive_minutes=parse_int_env("INACTIVE_MINUTES", default=5),
        conversation_status_field=os.getenv("CONVERSATION_STATUS_FIELD", "status"),
        active_status_value=os.getenv("ACTIVE_STATUS_VALUE", "Active"),
        closed_status_value=os.getenv("CLOSED_STATUS_VALUE", "Closed"),
        conversation_id_field=empty_to_none(os.getenv("CONVERSATION_ID_FIELD")),
        message_conversation_id_field=os.getenv(
            "MESSAGE_CONVERSATION_ID_FIELD",
            "conversation_id",
        ),
        last_interaction_fields=parse_csv_env(
            "LAST_INTERACTION_FIELDS",
            default=["last_msg_date", "last_interaction_at", "updated_at", "last_message_at"],
        ),
        message_timestamp_fields=parse_csv_env(
            "MESSAGE_TIMESTAMP_FIELDS",
            default=["created_at", "timestamp", "sent_at"],
        ),
        closed_at_field=os.getenv("CLOSED_AT_FIELD", "closed_at"),
        exported_at_field=os.getenv(
            "EXPORTED_AT_FIELD",
            "maintenance_exported_at",
        ),
        exported_path_field=os.getenv(
            "EXPORTED_PATH_FIELD",
            "maintenance_export_path",
        ),
        locked_at_field=os.getenv(
            "LOCKED_AT_FIELD",
            "maintenance_locked_at",
        ),
        locked_by_field=os.getenv(
            "LOCKED_BY_FIELD",
            "maintenance_locked_by",
        ),
        lock_timeout_seconds=parse_int_env(
            "LOCK_TIMEOUT_SECONDS",
            default=300,
        ),
        archive_lookup_retries=parse_int_env(
            "ARCHIVE_LOOKUP_RETRIES",
            default=3,
        ),
        archive_lookup_retry_seconds=parse_int_env(
            "ARCHIVE_LOOKUP_RETRY_SECONDS",
            default=1,
        ),
        api_token=empty_to_none(os.getenv("MAINTENANCE_API_TOKEN")),
        delete_exported_conversations=parse_bool_env(
            "DELETE_EXPORTED_CONVERSATIONS",
            default=True,
        ),
        delete_exported_messages=parse_bool_env(
            "DELETE_EXPORTED_MESSAGES",
            default=True,
        ),
        minio_enabled=parse_bool_env("MINIO_ENABLED", default=False),
        minio_endpoint_url=empty_to_none(os.getenv("MINIO_ENDPOINT_URL")),
        minio_bucket=empty_to_none(os.getenv("MINIO_BUCKET")),
        minio_region=os.getenv("MINIO_REGION", "us-east-1"),
        minio_access_key=empty_to_none(os.getenv("MINIO_ACCESS_KEY")),
        minio_secret_key=empty_to_none(os.getenv("MINIO_SECRET_KEY")),
        minio_addressing_style=os.getenv("MINIO_ADDRESSING_STYLE", "path"),
        control_index=first_env(
            "OPENSEARCH_CONTROL_INDEX",
            "CONTROL_INDEX",
            default="client-control-table",
        ),
        error_handler_service_url=empty_to_none(os.getenv("ERROR_HANDLER_SERVICE_URL")),
    )


def parse_hosts(raw_hosts: str) -> tuple[list[dict[str, object]], tuple[str, str] | None]:
    hosts: list[dict[str, object]] = []
    http_auth: tuple[str, str] | None = None

    for raw_host in [item.strip() for item in raw_hosts.split(",") if item.strip()]:
        candidate = raw_host if "://" in raw_host else f"https://{raw_host}"
        parsed = urlparse(candidate)
        if not parsed.hostname:
            raise ValueError(f"Invalid OpenSearch host: {raw_host}")

        host_config: dict[str, object] = {
            "host": parsed.hostname,
            "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            "use_ssl": parsed.scheme == "https",
        }

        if parsed.path and parsed.path != "/":
            host_config["url_prefix"] = parsed.path.rstrip("/")

        hosts.append(host_config)

        if http_auth is None and parsed.username:
            http_auth = (parsed.username, parsed.password or "")

    if not hosts:
        raise ValueError("At least one host must be configured in OPENSEARCH_HOSTS")

    return hosts, http_auth


def parse_csv_env(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return [item.strip() for item in raw_value.split(",") if item.strip()] or default


def parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw_value}")


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


def read_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def first_env(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default
