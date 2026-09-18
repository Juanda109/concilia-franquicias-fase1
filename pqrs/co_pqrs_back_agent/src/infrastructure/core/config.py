"""Application settings and environment configuration."""

import os
from pathlib import Path

from dotenv import dotenv_values
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

# Selector de transacciones de doble cobro (paso 3.4.0.6).
DEFAULT_TRANSACTIONS_PER_PAGE = 6
# Tope estructural: casillas `transaccion_N` declaradas en doble_cobro.yml.
MAX_TRANSACTIONS_PER_PAGE = 10
from infrastructure.entrypoint.api.errors.exceptions import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field


class OpenSearchSettings(BaseModel):
    """OpenSearch connection settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    endpoint: str = Field(description="OpenSearch base endpoint.")
    user: str = Field(description="OpenSearch username.")
    password: str = Field(description="OpenSearch password.")
    verify_ssl: bool = Field(
        default=False,
        description="Whether SSL certificates should be verified.",
    )
    conversations_index: str = Field(
        default="conversations-reference",
        description="Index used to store conversation reference documents.",
    )
    messages_index: str = Field(
        default="conversations-messages",
        description="Index used to store message documents.",
    )
    control_index: str = Field(
        default="client-control-table",
        description="Index used to store client flow control documents.",
    )
    control_record_ttl_days: int = Field(
        default=30,
        ge=1,
        description="Maximum number of days a control record should remain valid.",
    )
    control_max_monthly_interactions: int = Field(
        default=3,
        ge=1,
        description="Maximum number of monthly interactions allowed per client and workflow.",
    )
    timeout: float = Field(
        default=10.0,
        ge=1.0,
        description="HTTP timeout in seconds for OpenSearch requests.",
    )


class CorsSettings(BaseModel):
    """CORS middleware settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    allow_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed origins for browser cross-origin requests.",
    )
    allow_methods: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed HTTP methods for cross-origin requests.",
    )
    allow_headers: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed request headers for cross-origin requests.",
    )
    expose_headers: list[str] = Field(
        default_factory=list,
        description="Headers exposed to the browser.",
    )
    allow_credentials: bool = Field(
        default=False,
        description="Whether credentialed cross-origin requests are allowed.",
    )
    max_age: int = Field(
        default=600,
        ge=0,
        description="How long browsers can cache the preflight response in seconds.",
    )


def load_assistant_name(
    env_path: str | Path = ".env",
    *,
    default: str = "blue",
) -> str:
    """
    Load the configured assistant display name from the environment.

    Args:
        env_path: Relative or absolute path to the `.env` file.
        default: Fallback assistant name used when no explicit value exists.

    Returns:
        Normalized assistant display name.
    """

    constants = load_env_constants(env_path)
    assistant_name = (constants.get("BOT_NAME") or default).strip()
    return assistant_name or default


def load_end_conversation_callback_url(
    env_path: str | Path = ".env",
) -> str | None:
    """
    Load the optional callback URL triggered after closing a conversation.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        The configured callback URL, or `None` when it is blank or missing.
    """

    constants = load_env_constants(env_path)
    callback_url = (constants.get("END_CONVERSATION_CALLBACK_URL") or "").strip()
    return callback_url or None


def load_env_constants(
    env_path: str | Path = ".env",
    required_keys: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """
    Load constants from a .env file into a dictionary.

    Args:
        env_path: Relative or absolute path to the .env file.
        required_keys: Optional keys that must exist in the loaded constants.

    Returns:
        Dictionary with the parsed constants.
    """

    path = _resolve_env_path(env_path)
    file_constants: dict[str, str] = {}

    if path is not None:
        file_constants = {
            key: value
            for key, value in dotenv_values(path).items()
            if value is not None
        }

    constants = {
        **file_constants,
        **{
            key: value
            for key, value in os.environ.items()
            if value is not None
        },
    }

    if path is None and not constants:
        raise ConfigurationError(
            "Environment configuration was not found in a .env file or runtime variables.",
            details={"env_path": str(env_path)},
        )

    # Emit simple info logs to help local debugging about key env flags.
    try:
        logger.info(
            "env load: path=%s LOCAL_CONTINGENCY_MODE=%s DIAS_HABILES_TARJETA=%s DIAS_HABILES_DEVOLUCION=%s",
            path or str(env_path),
            constants.get("LOCAL_CONTINGENCY_MODE"),
            constants.get("DIAS_HABILES_TARJETA"),
            constants.get("DIAS_HABILES_DEVOLUCION"),
        )
        # Extra explicit log to make it obvious in startup logs which
        # DIAS_HABILES values are in effect and which env file provided them.
        logger.info(
            "env values: DIAS_HABILES_DEVOLUCION=%s DIAS_HABILES_TARJETA=%s (env_path=%s)",
            constants.get("DIAS_HABILES_DEVOLUCION"),
            constants.get("DIAS_HABILES_TARJETA"),
            path or str(env_path),
        )
    except Exception:
        # Non-fatal: logging should not break config loading.
        pass

    if required_keys:
        missing_keys = [key for key in required_keys if key not in constants]

        if missing_keys:
            raise ConfigurationError(
                "Required environment variables are missing.",
                details={
                    "env_path": str(path),
                    "missing_keys": missing_keys,
                },
            )

        return {key: constants[key] for key in required_keys}

    return constants


def load_opensearch_settings(env_path: str | Path = ".env") -> OpenSearchSettings:
    """
    Load OpenSearch connection settings from the environment file.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        Validated OpenSearch settings.
    """

    constants = load_env_constants(env_path)

    return OpenSearchSettings(
        endpoint=constants.get("OPENSEARCH_ENDPOINT", "https://localhost:9200"),
        user=constants.get("OPENSEARCH_USER", "admin"),
        password=constants.get("OPENSEARCH_PASSWORD", "admin"),
        verify_ssl=_parse_bool(constants.get("OPENSEARCH_VERIFY_SSL"), default=False),
        conversations_index=constants.get(
            "OPENSEARCH_CONVERSATIONS_INDEX",
            "conversations-reference",
        ),
        messages_index=constants.get(
            "OPENSEARCH_MESSAGES_INDEX",
            "conversations-messages",
        ),
        control_index=constants.get(
            "OPENSEARCH_CONTROL_INDEX",
            "client-control-table",
        ),
        control_record_ttl_days=int(
            constants.get("OPENSEARCH_CONTROL_RECORD_TTL_DAYS", "30")
        ),
        control_max_monthly_interactions=int(
            constants.get("OPENSEARCH_CONTROL_MAX_MONTHLY_INTERACTIONS", "3")
        ),
        timeout=float(constants.get("OPENSEARCH_TIMEOUT", "10")),
    )


def load_cors_settings(env_path: str | Path = ".env") -> CorsSettings:
    """
    Load CORS middleware settings from the environment file.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        Validated CORS settings.
    """

    constants = load_env_constants(env_path)

    return CorsSettings(
        allow_origins=_parse_csv(constants.get("CORS_ALLOW_ORIGINS"), default=["*"]),
        allow_methods=_parse_csv(constants.get("CORS_ALLOW_METHODS"), default=["*"]),
        allow_headers=_parse_csv(constants.get("CORS_ALLOW_HEADERS"), default=["*"]),
        expose_headers=_parse_csv(constants.get("CORS_EXPOSE_HEADERS"), default=[]),
        allow_credentials=_parse_bool(
            constants.get("CORS_ALLOW_CREDENTIALS"),
            default=False,
        ),
        max_age=int(constants.get("CORS_MAX_AGE", "600")),
    )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    """Parse a boolean-like environment variable value."""

    if value is None:
        return default

    return value.strip().casefold() not in {"0", "false", "no", "off"}


def _parse_csv(value: str | None, *, default: list[str]) -> list[str]:
    """Parse a comma-separated environment variable into a list of strings."""

    if value is None or not value.strip():
        return default

    parsed_values = [item.strip() for item in value.split(",") if item.strip()]
    return parsed_values or default


def load_max_daily_sessions(
    env_path: str | Path = ".env",
    *,
    default: int = 3,
) -> int:
    """
    Load the maximum number of sessions a user may start per calendar day.

    Args:
        env_path: Relative or absolute path to the `.env` file.
        default: Fallback limit used when no explicit value exists or it is invalid.

    Returns:
        The configured daily session limit (always >= 1).
    """

    constants = load_env_constants(env_path)
    raw_value = (constants.get("MAX_DAILY_SESSIONS") or "").strip()

    if not raw_value:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= 1 else default


def load_max_daily_category_interactions(
    env_path: str | Path = ".env",
    *,
    default: int = 3,
) -> int:
    """
    Load the maximum interactions allowed per limit category and calendar day.

    Args:
        env_path: Relative or absolute path to the `.env` file.
        default: Fallback limit used when no explicit value exists or it is invalid.

    Returns:
        The configured per-category daily interaction limit (always >= 1).
    """

    constants = load_env_constants(env_path)
    raw_value = (constants.get("MAX_DAILY_CATEGORY_INTERACTIONS") or "").strip()

    if not raw_value:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= 1 else default


def load_max_repeat_rechecks(
    env_path: str | Path = ".env",
    *,
    default: int = 3,
) -> int:
    """
    Load the maximum number of repeat-flow re-checks shown per client and day.

    Args:
        env_path: Relative or absolute path to the `.env` file.
        default: Fallback limit used when no explicit value exists or it is invalid.

    Returns:
        The configured maximum repeat-flow re-checks (always >= 1).
    """

    constants = load_env_constants(env_path)
    raw_value = (constants.get("MAX_REPEAT_RECHECKS") or "").strip()

    if not raw_value:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= 1 else default


def load_back_data_service_url(env_path: str | Path = ".env") -> str | None:
    """
    Load the optional base URL for the co_pqrs_back_data service.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        The configured base URL (without trailing slash), or `None` when not set.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("BACK_DATA_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_trx_service_url(env_path: str | Path = ".env") -> str | None:
    """
    Load the optional base URL for the co_pqrs_back_trx_noreconocida service.

    The trx path is still a MOCK skeleton; this URL is defined so the client can be
    wired later without code changes. Returns the base URL (without trailing slash),
    or ``None`` when not configured.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("TRX_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_authorization_service_url(env_path: str | Path = ".env") -> str | None:
    """
    Load the optional base URL for the co_pqrs_authorization service (Fase 4).

    Empty/absent means the authorization service is not wired: the trx flow
    falls back to the legacy direct consultation, so this can roll out
    gradually per environment without code changes.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("AUTHORIZATION_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_error_handler_service_url(env_path: str | Path = ".env") -> str | None:
    """
    Load the optional base URL for the co_pqrs_back_error_handler service.

    When configured, the agent pushes a structured error report (fire-and-forget)
    to this service whenever a chat turn fails, for auditing in MinIO.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        The configured base URL (without trailing slash), or `None` when not set.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("ERROR_HANDLER_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_audit_min_status(env_path: str | Path = ".env", *, default: int = 400) -> int:
    """
    Load the minimum HTTP status code that triggers an error audit.

    Responses with a status >= this value are audited to the error-handler.
    Defaults to 400 (audit every client and server error). Set to 500 to audit
    only server errors.

    Args:
        env_path: Relative or absolute path to the `.env` file.
        default: Fallback threshold when unset or invalid.

    Returns:
        The configured threshold (clamped to a sane minimum of 400).
    """

    constants = load_env_constants(env_path)
    raw_value = (constants.get("AUDIT_MIN_STATUS") or "").strip()

    if not raw_value:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= 400 else default


class RabbitMQSettings(BaseModel):
    """RabbitMQ event-publishing settings loaded from environment variables.

    Publishing is gated by ``enabled`` so the agent stays inert until RabbitMQ is
    deployed and the flag is switched on from the IaC config.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = Field(default=False, description="Whether to publish events.")
    url: str | None = Field(default=None, description="Full AMQP URL override.")
    host: str = Field(default="rabbitmq", description="RabbitMQ host.")
    port: int = Field(default=5672, ge=1, description="AMQP port.")
    vhost: str = Field(default="/", description="RabbitMQ virtual host.")
    user: str = Field(default="guest", description="RabbitMQ username.")
    password: str = Field(default="guest", description="RabbitMQ password.")
    exchange: str = Field(default="pqr.events", description="Topic exchange name.")
    exchange_type: str = Field(default="topic", description="Exchange type.")
    publish_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        description="Per-publish timeout to avoid hanging the background task.",
    )

    def effective_url(self) -> str:
        """Build the AMQP URL, preferring an explicit override when present."""

        if self.url:
            return self.url

        from urllib.parse import quote

        vhost_path = quote(self.vhost, safe="") if self.vhost not in ("", "/") else ""
        return (
            f"amqp://{quote(self.user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}:{self.port}/{vhost_path}"
        )


def _parse_amqp_port(value: str | None, *, default: int = 5672) -> int:
    """Parse an AMQP port, tolerating Kubernetes service-link values.

    Kubernetes injects ``RABBITMQ_PORT=tcp://<ip>:<port>`` for a Service named
    ``rabbitmq``, which (via os.environ precedence) shadows a plain ``"5672"``
    from the .env. Extract the numeric port from such a value, or fall back to
    the default instead of crashing.
    """

    if value is None:
        return default
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    # e.g. "tcp://172.25.25.184:5672" -> "5672"
    tail = text.rsplit(":", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return default


def load_rabbitmq_settings(env_path: str | Path = ".env") -> RabbitMQSettings:
    """
    Load RabbitMQ publishing settings from the environment file.

    Args:
        env_path: Relative or absolute path to the `.env` file.

    Returns:
        Validated RabbitMQ settings (disabled by default).
    """

    constants = load_env_constants(env_path)

    return RabbitMQSettings(
        enabled=_parse_bool(constants.get("RABBITMQ_ENABLED"), default=False),
        url=(constants.get("RABBITMQ_URL") or "").strip() or None,
        host=constants.get("RABBITMQ_HOST", "rabbitmq"),
        port=_parse_amqp_port(constants.get("RABBITMQ_PORT")),
        vhost=constants.get("RABBITMQ_VHOST", "/"),
        user=constants.get("RABBITMQ_USER", "guest"),
        password=constants.get("RABBITMQ_PASSWORD", "guest"),
        exchange=constants.get("RABBITMQ_EXCHANGE", "pqr.events"),
        exchange_type=constants.get("RABBITMQ_EXCHANGE_TYPE", "topic"),
        publish_timeout_seconds=float(
            constants.get("RABBITMQ_PUBLISH_TIMEOUT_SECONDS", "5")
        ),
    )


def _resolve_env_path(env_path: str | Path) -> Path | None:
    """Resolve the environment file path from cwd or project root."""

    path = Path(env_path).expanduser()
    if path.is_absolute() and path.exists():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    project_root = Path(__file__).resolve().parents[3]
    project_candidate = project_root / path
    if project_candidate.exists():
        return project_candidate

    return None


def load_doble_cobro_service_url(env_path: str | Path = ".env") -> str | None:
    """
    Load the optional base URL for the co_pqrs_back_doble_cobro service.

    Returns the base URL (without trailing slash), or ``None`` when not configured,
    in which case the client falls back to its local default.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("DC_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_transactions_per_page(env_path: str | Path = ".env") -> int:
    """
    Load the page size of the doble_cobro transaction selector.

    It is the ONLY knob for that list: the hook uses it to move between pages
    and the render action to decide how many checkboxes to paint, so both read
    it from here instead of keeping their own copy.

    Capped at the number of ``transaccion_N`` options declared by the workflow
    YAML: painting more than that is impossible, and silently showing fewer
    than configured would be confusing.
    """

    constants = load_env_constants(env_path)
    raw_value = (constants.get("TRANSACTIONS_PER_PAGE") or "").strip()

    try:
        value = int(raw_value) if raw_value else DEFAULT_TRANSACTIONS_PER_PAGE
    except ValueError:
        logger.warning(
            "TRANSACTIONS_PER_PAGE invalido (%s); se usa %s",
            raw_value,
            DEFAULT_TRANSACTIONS_PER_PAGE,
        )
        return DEFAULT_TRANSACTIONS_PER_PAGE

    if value < 1:
        return DEFAULT_TRANSACTIONS_PER_PAGE

    if value > MAX_TRANSACTIONS_PER_PAGE:
        logger.warning(
            "TRANSACTIONS_PER_PAGE=%s supera las %s casillas del YAML; se recorta",
            value,
            MAX_TRANSACTIONS_PER_PAGE,
        )
        return MAX_TRANSACTIONS_PER_PAGE

    return value
