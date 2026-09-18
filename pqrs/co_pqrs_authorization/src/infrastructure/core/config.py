"""Configuracion del servicio de autorizacion (.env + entorno real).

Mismo patron que el resto del repo: valores del fichero .env fusionados con
-- y pisados por -- las variables de entorno reales. Nada de os.getenv suelto
fuera de este modulo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_CONSTANTES: dict[str, str] = {}


def _cargar_env_file() -> None:
    for ruta in (os.getenv("ENV_FILE") or "", "/app/.env", ".env"):
        if not ruta or not os.path.exists(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as flujo:
                for linea in flujo:
                    linea = linea.strip()
                    if not linea or linea.startswith("#") or "=" not in linea:
                        continue
                    clave, _, valor = linea.partition("=")
                    _CONSTANTES.setdefault(clave.strip(), valor.strip())
        except OSError:
            continue
        break


_cargar_env_file()


def _valor(nombre: str, por_defecto: str = "") -> str:
    return (os.getenv(nombre) or _CONSTANTES.get(nombre) or por_defecto).strip()


@dataclass(frozen=True)
class OpenSearchSettings:
    base_url: str
    username: str
    password: str
    indice: str
    verify_ssl: bool


@dataclass(frozen=True)
class AsoSettings:
    """Solo lo que este servicio necesita del ASO: granting + order-chanel.

    La ceremonia del push NO vive aqui (decision de Luis, 03/09): este
    cliente unicamente consulta el estado del reto ya creado.
    """

    source: str
    base_url: str
    challenge_base_url: str
    granting_path: str
    order_channel_path: str
    api_user_id: str
    api_consumer_id: str
    api_authentication_type: str
    api_password: str
    timeout: float


@dataclass(frozen=True)
class WorkerSettings:
    habilitado: bool
    intervalo_tick: float
    intervalo_reintento: float
    lease_segundos: float
    lote: int


def load_opensearch_settings() -> OpenSearchSettings:
    return OpenSearchSettings(
        base_url=_valor("OPENSEARCH_URL", "https://localhost:9200").rstrip("/"),
        username=_valor("OPENSEARCH_USER", "admin"),
        password=_valor("OPENSEARCH_PASS", "admin"),
        indice=_valor("AUTHORIZATIONS_INDEX", "authorizations"),
        verify_ssl=_valor("OPENSEARCH_VERIFY_SSL", "false").casefold() == "true",
    )


def _resolver_aso_base() -> str:
    override = _valor("ASO_BASE_URL")
    if override:
        return override.rstrip("/")
    if _valor("ASO_SOURCE", "simulator").casefold() == "real":
        return (_valor("ASO_REAL_URL") or _valor("TRX_ASO_BASE_URL")).rstrip("/")
    return _valor(
        "ASO_SIMULATOR_URL", "http://localhost:8050"
    ).rstrip("/")


def load_aso_settings() -> AsoSettings:
    base = _resolver_aso_base()
    return AsoSettings(
        source=_valor("ASO_SOURCE", "simulator").casefold(),
        base_url=base,
        # En algunos entornos el challenge vive en otra pasarela
        # (ASO_CHALLENGE_BASE_URL, ver cambio de Luis 099a7ff en TXNR).
        challenge_base_url=_valor("ASO_CHALLENGE_BASE_URL").rstrip("/") or base,
        granting_path=_valor(
            "ASO_GRANTING_PATH", "/TechArchitecture/co/grantingTicket/V02"
        ),
        order_channel_path=_valor(
            "ASO_ORDER_CHANNEL_PATH", "/security/v0/order-chanel/{challenge}"
        ),
        api_user_id=_valor("TRX_API_USER_ID"),
        api_consumer_id=_valor("TRX_API_CONSUMER_ID", "12000035"),
        api_authentication_type=_valor("TRX_API_AUTHENTICATION_TYPE", "04"),
        api_password=_valor("TRX_API_PASSWORD"),
        timeout=float(_valor("ASO_TIMEOUT", "8") or "8"),
    )


def load_worker_settings() -> WorkerSettings:
    return WorkerSettings(
        habilitado=_valor("AUTHORIZATION_WORKER_ENABLED", "true").casefold() == "true",
        intervalo_tick=float(_valor("AUTHORIZATION_WORKER_TICK", "5") or "5"),
        intervalo_reintento=float(_valor("AUTHORIZATION_RETRY_SECONDS", "10") or "10"),
        lease_segundos=float(_valor("AUTHORIZATION_LEASE_SECONDS", "30") or "30"),
        lote=int(_valor("AUTHORIZATION_WORKER_BATCH", "20") or "20"),
    )


def load_deadline_segundos() -> float:
    return float(_valor("AUTHORIZATION_DEADLINE_SECONDS", "180") or "180")


def load_error_handler_service_url() -> str:
    """URL del error_handler para trazas MinIO. Vacio = trazas desactivadas."""

    return _valor("ERROR_HANDLER_SERVICE_URL").rstrip("/")


def load_service_port() -> int:
    return int(_valor("AUTHORIZATION_SERVICE_PORT", "8005") or "8005")
