"""Configuration helpers for the doble_cobro service."""

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

def _load_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _load_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _load_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DobleCobroSettings:
    """Parámetros de negocio del flujo, todos ajustables por entorno."""

    log_level: str

    # Ventana de conciliación con el comercio antes de poder reclamar.
    # Es la misma para cuentas y para tarjetas débito.
    settlement_days: int

    # Vigencia para reportar: primero el plazo general, luego el de franquicia.
    max_report_months: int
    visa_validity_days: int
    master_validity_days: int

    # Detección de duplicados. La agrupación es por día completo, así que no
    # hay ventana horaria configurable.
    amount_tolerance: float


def load_doble_cobro_settings() -> DobleCobroSettings:
    """Lee la configuración del flujo desde el entorno."""

    return DobleCobroSettings(
        log_level=os.getenv("DOBLE_COBRO_LOG_LEVEL") or "INFO",
        settlement_days=_load_int("DC_SETTLEMENT_DAYS", 7),
        max_report_months=_load_int("DC_MAX_REPORT_MONTHS", 6),
        visa_validity_days=_load_int("DC_VISA_VALIDITY_DAYS", 180),
        master_validity_days=_load_int("DC_MASTER_VALIDITY_DAYS", 120),
        amount_tolerance=_load_float("DC_AMOUNT_TOLERANCE", 2000.0),
    )


# ---------------------------------------------------------------------------
# ASO
# ---------------------------------------------------------------------------

DEFAULT_ASO_SOURCE = "simulator"
DEFAULT_SIMULATOR_URL = "http://127.0.0.1:8050"
DEFAULT_FO_PATH = "/financial-overview/v0/financial-overview"
DEFAULT_OPERATIONS_PATH = "/cards/v2/operations"


@dataclass(frozen=True)
class DobleCobroAsoSettings:
    """Conexion con el ASO (simulador o real).

    Misma forma que ``TrxAsoSettings`` del flujo de transaccion no reconocida:
    los dos consumen la misma pasarela y no tiene sentido que uno respete
    ``verify_ssl``/``timeout`` y el otro los ignore.
    """

    source: str
    base_url: str
    ticket_url: str
    api_user_id: str
    api_consumer_id: str
    api_authentication_type: str
    api_password: str
    api_verify_ssl: bool
    api_timeout: float
    financial_overview_path: str
    operations_path: str


def _resolve_aso_base_url() -> str:
    """Base URL del ASO segun ``ASO_SOURCE``.

    - ``DC_ASO_BASE_URL`` SIEMPRE gana (override manual, tambien sobre
      ``ASO_SOURCE``: definirla deja el switch sin efecto).
    - ``real``      -> ``DC_ASO_REAL_URL``.
    - ``simulator`` -> ``DC_ASO_SIMULATOR_URL`` o el simulador local.
    """

    override = (os.getenv("DC_ASO_BASE_URL") or "").strip().rstrip("/")
    if override:
        return override

    source = (os.getenv("ASO_SOURCE") or DEFAULT_ASO_SOURCE).strip().casefold()
    if source == "real":
        return (os.getenv("DC_ASO_REAL_URL") or "").strip().rstrip("/")

    return (
        os.getenv("DC_ASO_SIMULATOR_URL") or DEFAULT_SIMULATOR_URL
    ).strip().rstrip("/")


def load_doble_cobro_aso_settings() -> DobleCobroAsoSettings:
    """Lee del entorno como se habla con el ASO."""

    return DobleCobroAsoSettings(
        source=(os.getenv("ASO_SOURCE") or DEFAULT_ASO_SOURCE).strip().casefold()
        or DEFAULT_ASO_SOURCE,
        base_url=_resolve_aso_base_url(),
        ticket_url=(os.getenv("DC_ASO_TICKET_URL") or "").strip(),
        api_user_id=(os.getenv("DC_ASO_API_USER_ID") or "").strip(),
        api_consumer_id=(os.getenv("DC_ASO_API_CONSUMER_ID") or "").strip(),
        api_authentication_type=(
            os.getenv("DC_ASO_API_AUTHENTICATION_TYPE") or "04"
        ).strip(),
        api_password=(os.getenv("DC_ASO_API_PASSWORD") or "").strip(),
        # El ASO real de BBVA presenta un certificado corporativo que la CA
        # publica no firma: sin esto el grantingTicket muere en el handshake,
        # el TSEC queda vacio y las llamadas salen sin autenticar.
        api_verify_ssl=_load_bool("DC_ASO_API_VERIFY_SSL", True),
        api_timeout=_load_float("DC_ASO_API_TIMEOUT", 30.0),
        financial_overview_path=(
            os.getenv("DC_ASO_FO_PATH") or DEFAULT_FO_PATH
        ).strip().rstrip("/"),
        operations_path=(
            os.getenv("DC_ASO_OPERATIONS_PATH") or DEFAULT_OPERATIONS_PATH
        ).strip().rstrip("/"),
    )
