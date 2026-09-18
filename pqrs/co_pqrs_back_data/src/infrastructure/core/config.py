"""Application settings and environment configuration."""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field


class CsvSettings(BaseModel):
    """Customer identity data source settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(
        default="mock",
        description="Customer identity source: mock/csv or postgres.",
    )
    customer_identity_csv_path: Path = Field(
        default=Path("data/datos_ada_000001069759414.csv"),
        description="Path to the PostgreSQL customer identity CSV mock.",
    )
    DB_HOST: str = Field(default="localhost", description="PostgreSQL host.")
    postgres_port: int = Field(default=5432, description="PostgreSQL port.")
    postgres_connect_timeout: int = Field(
        default=5,
        description="PostgreSQL connection timeout seconds.",
    )
    DB_NAME: str = Field(default="pqr_db", description="PostgreSQL database.")
    DB_USER: str = Field(default="pqr_user", description="PostgreSQL user.")
    DB_PASS: str = Field(
        default="pqr_password",
        description="PostgreSQL password.",
    )
    postgres_table: str = Field(
        default="ada_info_detail",
        description="PostgreSQL table with customer identity data.",
    )
    postgres_table_emb: str = Field(
        default="bgdtemb",
        description="PostgreSQL table with embargo customer data.",
    )
    postgres_table_dem: str = Field(
        default="bgdtdem",
        description="PostgreSQL table with embargo contract level data.",
    )
    postgres_table_join: str = Field(
        default="bgdt_salida_join",
        description="PostgreSQL table with the pre-joined embargo (BGDTDEM x BGDTEMB) output.",
    )
    environment: str = Field(
        default="local",
        description="Runtime environment name.",
    )


class CommercialInfoSettings(BaseModel):
    """Commercial-info settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(
        default="mock",
        description="Commercial-info source: mock or api.",
    )
    commercial_info_mock_dir: Path = Field(
        default=Path("data"),
        description="Directory where commercial-info JSON mocks are stored.",
    )
    commercial_info_file_prefix: str = Field(
        default="commercial_info_",
        description="Prefix used to locate commercial-info JSON mock files.",
    )
    ticket_url: str = Field(
        default="",
        description="URL used to request the tsec ticket.",
    )
    overview_url: str = Field(
        default="",
        description="Commercial information API URL.",
    )
    aso_base_url: str = Field(
        default="https://dev-arqaso.work.co.nextgen.igrupobbva:8050",
        description="Base URL used by ASO service calls.",
    )
    api_user_id: str = Field(default="", description="Ticket API user id.")
    api_consumer_id: str = Field(default="", description="Ticket API consumer id.")
    api_authentication_type: str = Field(
        default="04",
        description="Ticket API authentication type.",
    )
    api_password: str = Field(default="", description="Ticket API password.")
    api_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for commercial-info API calls.",
    )
    api_timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="Commercial-info API request timeout seconds.",
    )
    api_customer_id_length: int = Field(
        default=8,
        ge=1,
        description="Length used to left-pad document number for the commercial API.",
    )
    # Plantillas de path de los extractos por familia de producto (ASO). Usan los
    # placeholders {contract_id} y {id_extracto}. La base la aporta aso_base_url.
    extracto_prestamos_listado: str = Field(
        default="/loans/v1/loans/{contract_id}/financial-statements"
    )
    extracto_prestamos_pdf: str = Field(
        default="/loans/v1/loans/{contract_id}/financial-statements/{id_extracto}"
    )
    extracto_cuentas_listado: str = Field(
        default="/accounts/v0/accounts/{contract_id}/financial-statements"
    )
    extracto_cuentas_pdf: str = Field(
        default="/accounts/v0/accounts/{contract_id}/financial-statements/{id_extracto}"
    )
    extracto_tdc_listado: str = Field(
        default="/cards/v1/cards/{contract_id}/financial-statements"
    )
    extracto_tdc_pdf: str = Field(
        default="/cards/v1/cards/{contract_id}/financial-statements/{id_extracto}"
    )
    extracto_leasing_listado: str = Field(
        default="/leasings/v0/leasings/{contract_id}/financial-statements"
    )
    extracto_leasing_pdf: str = Field(
        default="/leasings/v0/leasings/{contract_id}/financial-statements/{id_extracto}"
    )
    extracto_fondos_listado: str = Field(
        default=(
            "/investment-funds/v0/investment-funds/"
            "{contract_id}/funds/{contract_id}/financial-statements"
        )
    )
    extracto_fondos_pdf: str = Field(
        default=(
            "/investment-funds/v0/investment-funds/"
            "{contract_id}/funds/{contract_id}/financial-statements/{id_extracto}"
        )
    )


class OpenSearchSettings(BaseModel):
    """OpenSearch settings loaded from environment configuration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    endpoint: str = Field(
        default="https://localhost:9200",
        description="OpenSearch URL.",
    )
    user: str = Field(default="admin", description="OpenSearch username.")
    password: str = Field(default="admin", description="OpenSearch password.")
    verify_ssl: bool = Field(default=False, description="Verify SSL certificates.")
    timeout: float = Field(default=10.0, ge=1.0, description="Request timeout seconds.")
    conversations_index: str = Field(
        default="conversations-reference",
        description="Index where conversation documents are stored.",
    )
    messages_index: str = Field(
        default="conversations-messages",
        description="Index where conversation messages are stored.",
    )
    control_index: str = Field(
        default="client-control-table",
        description="Index where client flow control documents are stored.",
    )

    @property
    def base_url(self) -> str:
        return self.endpoint.rstrip("/")


class CorsSettings(BaseModel):
    """CORS middleware settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    expose_headers: list[str] = Field(default_factory=list)
    allow_credentials: bool = False
    max_age: int = Field(default=600, ge=0)


def load_env_constants(env_path: str | Path = ".env") -> dict[str, str]:
    """Load constants from .env and runtime variables."""

    path = _resolve_env_path(env_path)
    file_constants: dict[str, str] = {}

    if path is not None:
        file_constants = {
            key: value
            for key, value in dotenv_values(path).items()
            if value is not None
        }

    environment = _resolve_environment(file_constants)

    return {
        **file_constants,
        **{
            key: value
            for key, value in os.environ.items()
            if value is not None
        },
        "APP_ENV": environment,
    }


def load_csv_settings(env_path: str | Path = ".env") -> CsvSettings:
    """Load customer identity source settings from the environment."""

    constants = load_env_constants(env_path)
    configured_path = _resolve_data_csv_path(
        constants.get("DATA_CSV")
        or constants.get("CUSTOMER_IDENTITY_CSV_PATH")
        or "datos_ada_000001069759414"
    )

    if configured_path.is_absolute():
        customer_identity_csv_path = configured_path
    else:
        customer_identity_csv_path = Path(__file__).resolve().parents[3] / configured_path

    return CsvSettings(
        source=constants.get("CUSTOMER_IDENTITY_SOURCE", "mock").strip().lower(),
        customer_identity_csv_path=customer_identity_csv_path,
        DB_HOST=constants.get("DB_HOST", "localhost"),
        postgres_port=int(constants.get("POSTGRES_PORT", "5432")),
        postgres_connect_timeout=int(constants.get("POSTGRES_CONNECT_TIMEOUT", "5")),
        DB_NAME=constants.get("DB_NAME", "pqr_db"),
        DB_USER=constants.get("DB_USER", "pqr_user"),
        DB_PASS=constants.get("DB_PASS", "pqr_password"),
        postgres_table=constants.get("POSTGRES_CUSTOMER_IDENTITY_TABLE", "ada_info_detail"),
        postgres_table_emb=constants.get("POSTGRES_TABLE_EMB", "bgdtemb"),
        postgres_table_dem=constants.get("POSTGRES_TABLE_DEM", "bgdtdem"),
        postgres_table_join=constants.get("POSTGRES_TABLE_JOIN", "bgdt_salida_join"),
        environment=constants.get("APP_ENV", "local"),
    )


def load_commercial_info_settings(
    env_path: str | Path = ".env",
) -> CommercialInfoSettings:
    """Load commercial-info settings from the environment."""

    constants = load_env_constants(env_path)
    configured_dir = Path(constants.get("COMMERCIAL_INFO_MOCK_DIR", "data"))

    if configured_dir.is_absolute():
        commercial_info_mock_dir = configured_dir
    else:
        commercial_info_mock_dir = Path(__file__).resolve().parents[3] / configured_dir

    return CommercialInfoSettings(
        source=constants.get("COMMERCIAL_INFO_SOURCE", "mock").strip().lower(),
        commercial_info_mock_dir=commercial_info_mock_dir,
        commercial_info_file_prefix=constants.get(
            "COMMERCIAL_INFO_FILE_PREFIX",
            "commercial_info_",
        ),
        ticket_url=constants.get("COMMERCIAL_INFO_TICKET_URL", ""),
        overview_url=constants.get("COMMERCIAL_INFO_OVERVIEW_URL", ""),
        aso_base_url=constants.get(
            "COMMERCIAL_INFO_ASO_BASE_URL",
            "https://dev-arqaso.work.co.nextgen.igrupobbva:8050",
        ),
        api_user_id=constants.get("COMMERCIAL_INFO_API_USER_ID", ""),
        api_consumer_id=constants.get("COMMERCIAL_INFO_API_CONSUMER_ID", ""),
        api_authentication_type=constants.get(
            "COMMERCIAL_INFO_API_AUTHENTICATION_TYPE",
            "04",
        ),
        api_password=constants.get("COMMERCIAL_INFO_API_PASSWORD", ""),
        api_verify_ssl=_parse_bool(
            constants.get("COMMERCIAL_INFO_API_VERIFY_SSL"),
            default=True,
        ),
        api_timeout=float(constants.get("COMMERCIAL_INFO_API_TIMEOUT", "30")),
        api_customer_id_length=int(
            constants.get("COMMERCIAL_INFO_API_CUSTOMER_ID_LENGTH", "8")
        ),
        extracto_prestamos_listado=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_PRESTAMOS_LISTADO",
            "/loans/v1/loans/{contract_id}/financial-statements",
        ),
        extracto_prestamos_pdf=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_PRESTAMOS_PDF",
            "/loans/v1/loans/{contract_id}/financial-statements/{id_extracto}",
        ),
        extracto_cuentas_listado=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_CUENTAS_LISTADO",
            "/accounts/v0/accounts/{contract_id}/financial-statements",
        ),
        extracto_cuentas_pdf=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_CUENTAS_PDF",
            "/accounts/v0/accounts/{contract_id}/financial-statements/{id_extracto}",
        ),
        extracto_tdc_listado=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_TDC_LISTADO",
            "/cards/v1/cards/{contract_id}/financial-statements",
        ),
        extracto_tdc_pdf=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_TDC_PDF",
            "/cards/v1/cards/{contract_id}/financial-statements/{id_extracto}",
        ),
        extracto_leasing_listado=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_LEASING_LISTADO",
            "/leasings/v0/leasings/{contract_id}/financial-statements",
        ),
        extracto_leasing_pdf=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_LEASING_PDF",
            "/leasings/v0/leasings/{contract_id}/financial-statements/{id_extracto}",
        ),
        extracto_fondos_listado=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_FONDOS_LISTADO",
            "/investment-funds/v0/investment-funds/"
            "{contract_id}/funds/{contract_id}/financial-statements",
        ),
        extracto_fondos_pdf=constants.get(
            "COMMERCIAL_INFO_EXTRACTO_FONDOS_PDF",
            "/investment-funds/v0/investment-funds/"
            "{contract_id}/funds/{contract_id}/financial-statements/{id_extracto}",
        ),
    )


def load_opensearch_settings(env_path: str | Path = ".env") -> OpenSearchSettings:
    """Load OpenSearch settings from the active environment."""

    constants = load_env_constants(env_path)

    return OpenSearchSettings(
        endpoint=constants.get("OPENSEARCH_ENDPOINT", "https://localhost:9200"),
        user=constants.get("OPENSEARCH_USER", "admin"),
        password=constants.get("OPENSEARCH_PASSWORD", "admin"),
        verify_ssl=_parse_bool(
            constants.get("OPENSEARCH_VERIFY_SSL") or constants.get("SSL_VERIFY"),
            default=False,
        ),
        timeout=float(constants.get("OPENSEARCH_TIMEOUT", "10")),
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
    )


def load_cors_settings(env_path: str | Path = ".env") -> CorsSettings:
    """Load CORS middleware settings from the environment file."""

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


def load_error_handler_service_url(env_path: str | Path = ".env") -> str | None:
    """Load the optional base URL of the co_pqrs_back_error_handler service.

    When configured, back_data pushes a structured error report (fire-and-forget)
    on failures so they are audited in MinIO ``audit-logs``.
    """

    constants = load_env_constants(env_path)
    url = (constants.get("ERROR_HANDLER_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def load_audit_min_status(env_path: str | Path = ".env", *, default: int = 400) -> int:
    """Load the minimum HTTP status code that triggers an error audit (>= 400)."""

    constants = load_env_constants(env_path)
    raw_value = (constants.get("AUDIT_MIN_STATUS") or "").strip()

    if not raw_value:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= 400 else default


def _parse_csv(value: str | None, *, default: list[str]) -> list[str]:
    """Parse a comma-separated environment variable into a list of strings."""

    if value is None or not value.strip():
        return default

    parsed_values = [item.strip() for item in value.split(",") if item.strip()]
    return parsed_values or default


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


def _resolve_environment(constants: dict[str, str]) -> str:
    """Resolve the active runtime environment."""

    environment = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or constants.get("APP_ENV")
        or constants.get("ENVIRONMENT")
        or constants.get("ENV")
        or "local"
    )
    return environment.strip().lower() or "local"


def _resolve_data_csv_path(value: str) -> Path:
    """Resolve a CSV config value to a project-relative path."""

    configured_path = Path(value.strip())

    if configured_path.suffix.casefold() != ".csv":
        configured_path = configured_path.with_suffix(".csv")

    if configured_path.is_absolute() or configured_path.parts[:1] == ("data",):
        return configured_path

    return Path("data") / configured_path
