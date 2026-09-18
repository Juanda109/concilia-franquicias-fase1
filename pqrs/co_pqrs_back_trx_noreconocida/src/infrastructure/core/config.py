"""Configuration helpers for the MOCK trx service."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Carga el .env montado por el configmap (o el del CWD en local) hacia os.environ,
# SIN sobreescribir variables ya presentes. Sin esto, os.getenv(...) no veria el
# configmap (que se monta como archivo /app/.env, no como envFrom).
try:  # pragma: no cover - best-effort, nunca rompe el arranque
    from dotenv import load_dotenv as _load_dotenv

    for _env_path in (os.getenv("ENV_FILE") or "", "/app/.env", ".env"):
        if _env_path and os.path.exists(_env_path):
            _load_dotenv(_env_path, override=False)
            break
except Exception:
    pass

SERVICE_NAME = "co_pqrs_back_trx_noreconocida"
DEFAULT_PORT = 8004
DEFAULT_POSTGRES_TABLE = "ada_info_detail"
DEFAULT_SALESFORCE_SOURCE = "mock"
# solo-FO (Fabian, 24/08): la unica fuente de productos es el financial-overview.
# "postgres" queda como valor legado, deprecado -- ver analysis_service.
DEFAULT_PRODUCTS_SOURCE = "fo"
DEFAULT_MOVEMENTS_SOURCE = "mock"
DEFAULT_MOVEMENTS_MOCK_FILE = "data/movimientos_mock.json"
DEFAULT_IDENTITY_CSV_FILE = "data/unifi.csv"
DEFAULT_SALESFORCE_MOCK_FILE = "data/aso_salesforce.json"
DEFAULT_ASO_SOURCE = "simulator"


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    table: str
    connect_timeout: int


@dataclass(frozen=True)
class TrxSourceSettings:
    salesforce_source: str
    products_source: str
    salesforce_mock_file: str
    movements_source: str
    movements_mock_file: str


@dataclass(frozen=True)
class TrxAsoSettings:
    source: str
    base_url: str
    challenge_base_url: str
    ticket_url: str
    aso_base_url: str
    api_user_id: str
    api_consumer_id: str
    api_authentication_type: str
    api_password: str
    api_verify_ssl: bool
    api_timeout: float
    api_customer_id_length: int
    # Paths de cada ASO (configurables). {card_id} se reemplaza en tiempo de ejecución.
    salesforce_path: str
    financial_overview_path: str
    operations_path: str
    activations_path: str
    reissuance_path: str
    # --- Subida de nivel (notificacion push previa al bloqueo) -------------
    # MISMA base URL que el resto: solo cambian los paths.
    user_status_path: str
    order_channel_path: str
    # Constantes del contrato del reto. Fijas, pero configurables por si el ASO
    # las cambia en otro ambiente.
    challenge_channel: str
    challenge_smc: str
    challenge_operation: str
    challenge_reason: str
    challenge_retention_name: str
    challenge_description: str
    challenge_auth_type: str


@dataclass(frozen=True)
class TrxFlowSettings:
    """Campos configurables del flujo TXNR (rutas de match/validación y reglas)."""
    fo_contract_match_field: str
    fo_card_number_path: str
    tx_op_id_field: str
    eci_path: str
    ecard_path: str
    response_oper_path: str
    eci_chargeback_set: frozenset[str]
    vigencia_visa_dias: int
    vigencia_master_dias: int
    monto_min: float
    monto_max: float
    max_bot_recurrence: int
    recurrencia_meses: int
    subjects_txnr: tuple[str, ...]
    dias_habiles_devolucion: int


def load_port() -> int:
    """Return the configured service port (defaults to 8004)."""

    raw = (os.getenv("TRX_SERVICE_PORT") or "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return value if value > 0 else DEFAULT_PORT


def load_postgres_settings() -> PostgresSettings | None:
    """Return Postgres settings when fully configured, else `None`."""

    host = (os.getenv("DB_HOST") or "").strip()
    database = (os.getenv("DB_NAME") or "pqr_db").strip()
    user = (os.getenv("DB_USER") or "pqr_user").strip()
    password = (os.getenv("DB_PASS") or "pqr_password").strip()
    if not host:
        return None
    raw_port = (os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT") or "").strip()
    raw_timeout = (os.getenv("POSTGRES_CONNECT_TIMEOUT") or "").strip()
    try:
        port = int(raw_port) if raw_port else 5432
    except ValueError:
        port = 5432
    try:
        connect_timeout = int(raw_timeout) if raw_timeout else 5
    except ValueError:
        connect_timeout = 5
    table = (
        os.getenv("TRX_POSTGRES_TABLE")
        or os.getenv("POSTGRES_CUSTOMER_IDENTITY_TABLE")
        or DEFAULT_POSTGRES_TABLE
    ).strip()
    return PostgresSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        table=table or DEFAULT_POSTGRES_TABLE,
        connect_timeout=max(connect_timeout, 1),
    )


def load_identity_csv_path() -> str:
    """Return the TXNR-owned local identity CSV path."""

    return (
        os.getenv("TRX_IDENTITY_CSV_FILE")
        or os.getenv("DATA_CSV")
        or DEFAULT_IDENTITY_CSV_FILE
    ).strip() or DEFAULT_IDENTITY_CSV_FILE


def load_trx_source_settings() -> TrxSourceSettings:
    """Return source selector flags for trx integrations."""

    salesforce_source = (
        os.getenv("TRX_SALESFORCE_SOURCE")
        or os.getenv("SALESFORCE_SOURCE")
        or DEFAULT_SALESFORCE_SOURCE
    )
    products_source = (
        os.getenv("TRX_PRODUCTS_SOURCE")
        or os.getenv("CUSTOMER_IDENTITY_SOURCE")
        or DEFAULT_PRODUCTS_SOURCE
    )
    salesforce_mock_file = (
        os.getenv("TRX_SALESFORCE_MOCK_FILE")
        or os.getenv("SALESFORCE_MOCK_FILE")
        or DEFAULT_SALESFORCE_MOCK_FILE
    )
    movements_source = (
        os.getenv("TRX_MOVEMENTS_SOURCE")
        or os.getenv("MOVEMENTS_SOURCE")
        or DEFAULT_MOVEMENTS_SOURCE
    )
    movements_mock_file = (
        os.getenv("TRX_MOVEMENTS_MOCK_FILE")
        or os.getenv("MOVEMENTS_MOCK_FILE")
        or DEFAULT_MOVEMENTS_MOCK_FILE
    )
    return TrxSourceSettings(
        salesforce_source=str(salesforce_source).strip().casefold() or DEFAULT_SALESFORCE_SOURCE,
        products_source=str(products_source).strip().casefold() or DEFAULT_PRODUCTS_SOURCE,
        salesforce_mock_file=str(salesforce_mock_file).strip() or DEFAULT_SALESFORCE_MOCK_FILE,
        movements_source=str(movements_source).strip().casefold() or DEFAULT_MOVEMENTS_SOURCE,
        movements_mock_file=str(movements_mock_file).strip() or DEFAULT_MOVEMENTS_MOCK_FILE,
    )


def _load_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def load_trx_aso_settings() -> TrxAsoSettings:
    """Return ASO ticket/endpoint settings for the trx Salesforce mock."""

    api_timeout_raw = (os.getenv("TRX_API_TIMEOUT") or "").strip()
    api_customer_id_length_raw = (os.getenv("TRX_API_CUSTOMER_ID_LENGTH") or "").strip()
    try:
        api_timeout = float(api_timeout_raw) if api_timeout_raw else 30.0
    except ValueError:
        api_timeout = 30.0
    try:
        api_customer_id_length = (
            int(api_customer_id_length_raw) if api_customer_id_length_raw else 15
        )
    except ValueError:
        api_customer_id_length = 15

    return TrxAsoSettings(
        source=(os.getenv("ASO_SOURCE") or DEFAULT_ASO_SOURCE).strip().casefold() or DEFAULT_ASO_SOURCE,
        base_url=_resolve_aso_base_url(),
        challenge_base_url=(os.getenv("ASO_CHALLENGE_BASE_URL") or "").strip().rstrip("/"),
        ticket_url=(os.getenv("TRX_TICKET_URL") or "").strip(),
        aso_base_url=(os.getenv("ASO_REAL_URL") or os.getenv("TRX_ASO_BASE_URL") or "").strip().rstrip("/"),
        api_user_id=(os.getenv("TRX_API_USER_ID") or "").strip(),
        api_consumer_id=(os.getenv("TRX_API_CONSUMER_ID") or "").strip(),
        api_authentication_type=(os.getenv("TRX_API_AUTHENTICATION_TYPE") or "04").strip(),
        api_password=(os.getenv("TRX_API_PASSWORD") or "").strip(),
        api_verify_ssl=_load_bool("TRX_API_VERIFY_SSL", True),
        api_timeout=api_timeout,
        api_customer_id_length=max(api_customer_id_length, 1),
        salesforce_path=(os.getenv("ASO_SALESFORCE_PATH") or "/salesforce-issue-tracker/v0/issues").strip(),
        financial_overview_path=(os.getenv("ASO_FO_PATH") or "/financial-overview/v0/financial-overview").strip(),
        operations_path=(os.getenv("ASO_OPERATIONS_PATH") or "/cards/v2/operations").strip(),
        activations_path=(os.getenv("ASO_ACTIVATIONS_PATH") or "/cards/v1/cards/{card_id}/activations").strip(),
        reissuance_path=(os.getenv("ASO_REISSUANCE_PATH") or "/cards/v2/operations").strip(),
        user_status_path=(os.getenv("ASO_USER_STATUS_PATH") or "/security/v0/user-status").strip(),
        order_channel_path=(
            os.getenv("ASO_ORDER_CHANNEL_PATH") or "/security/v0/order-chanel/{challenge}"
        ).strip(),
        challenge_channel=(os.getenv("ASO_CHALLENGE_CHANNEL") or "12000035").strip(),
        challenge_smc=(os.getenv("ASO_CHALLENGE_SMC") or "SMGG20210970").strip(),
        challenge_operation=(os.getenv("ASO_CHALLENGE_OPERATION") or "NMONETARY").strip(),
        challenge_reason=(os.getenv("ASO_CHALLENGE_REASON") or "Fraude").strip(),
        challenge_retention_name=(os.getenv("ASO_CHALLENGE_RETENTION_NAME") or "Titular").strip(),
        challenge_description=(
            os.getenv("ASO_CHALLENGE_DESCRIPTION")
            or "bloqueo y reexpedicion"
        ).strip(),
        challenge_auth_type=(os.getenv("ASO_CHALLENGE_AUTH_TYPE") or "241").strip(),
    )


def load_error_handler_service_url() -> str | None:
    """URL base del co_pqrs_back_error_handler para trazas/errores (None si no esta)."""
    url = (os.getenv("ERROR_HANDLER_SERVICE_URL") or "").strip().rstrip("/")
    return url or None


def _resolve_aso_base_url() -> str:
    """Base URL del ASO según ASO_SOURCE.

    - ASO_BASE_URL (si se define) SIEMPRE gana (override manual).
    - source == "real"      -> ASO_REAL_URL (o TRX_ASO_BASE_URL).
    - source == "simulator" -> ASO_SIMULATOR_URL (o el service del simulador).
    """
    override = (os.getenv("ASO_BASE_URL") or "").strip().rstrip("/")
    if override:
        return override
    source = (os.getenv("ASO_SOURCE") or DEFAULT_ASO_SOURCE).strip().casefold()
    if source == "real":
        return (os.getenv("ASO_REAL_URL") or os.getenv("TRX_ASO_BASE_URL") or "").strip().rstrip("/")
    return (
        os.getenv("ASO_SIMULATOR_URL")
        or "http://co-pqrs-back-trx-aso-simulator.pqr-genai-dev.svc.cluster.local:8050"
    ).strip().rstrip("/")


def _load_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _load_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def load_trx_flow_settings() -> TrxFlowSettings:
    """Campos/reglas configurables del flujo TXNR (defaults del doc)."""

    eci_set_raw = (os.getenv("ECI_CHARGEBACK_SET") or "0,1,2,3,7").strip()
    eci_set = frozenset(x.strip() for x in eci_set_raw.split(",") if x.strip())
    subjects_raw = (
        os.getenv("SUBJECTS_TXNR")
        or "no reconoce,transaccion no reconocida,transacción no reconocida"
    )
    subjects = tuple(s.strip().casefold() for s in subjects_raw.split(",") if s.strip())
    return TrxFlowSettings(
        fo_contract_match_field=(os.getenv("FO_CONTRACT_MATCH_FIELD") or "number").strip(),
        fo_card_number_path=(os.getenv("FO_CARD_NUMBER_PATH") or "id").strip(),
        tx_op_id_field=(os.getenv("TX_OP_ID_FIELD") or "id").strip(),
        eci_path=(os.getenv("ECI_PATH") or "eci").strip(),
        ecard_path=(os.getenv("ECARD_PATH") or "eCard").strip(),
        response_oper_path=(os.getenv("RESPONSE_OPER_PATH") or "responseOperati").strip(),
        eci_chargeback_set=eci_set,
        vigencia_visa_dias=_load_int("VIGENCIA_VISA_DIAS", 180),
        vigencia_master_dias=_load_int("VIGENCIA_MASTER_DIAS", 120),
        monto_min=_load_float("TRX_MONTO_MIN", 35000.0),
        monto_max=_load_float("TRX_MONTO_MAX", 500000.0),
        # Politica IT4.6: maximo 3 solicitudes por tipologia en una ventana de 6 meses.
        # El mismo parametro gobierna el contador del agente y la consulta a Salesforce.
        max_bot_recurrence=_load_int("MAX_TRX_BOT_RECURRENCE", 3),
        recurrencia_meses=_load_int("TRX_RECURRENCIA_MESES", 6),
        subjects_txnr=subjects,
        dias_habiles_devolucion=_load_int("DIAS_HABILES_DEVOLUCION", 10),
    )


# Log DIAS values at startup so operators can verify which values are active.
try:  # pragma: no cover - best-effort logging, never break startup
    from infrastructure.core.logger import get_logger

    _logger = get_logger(__name__)
    try:
        _dias_dev = _load_int("DIAS_HABILES_DEVOLUCION", 10)
    except Exception:
        _dias_dev = 10
    try:
        _dias_tarj = _load_int("DIAS_HABILES_TARJETA", 10)
    except Exception:
        _dias_tarj = 10
    _env_file = os.getenv("ENV_FILE") or "/app/.env or .env"
    _logger.info(
        "DIAS_HABILES_DEVOLUCION=%s DIAS_HABILES_TARJETA=%s ENV_FILE=%s",
        _dias_dev,
        _dias_tarj,
        _env_file,
    )
except Exception:
    pass
