"""Cliente ASO para Doble Cobro.

Consume dos servicios del ASO (simulador o real):

* ``GET /financial-overview/v0/financial-overview`` -> productos del cliente.
* ``GET /cards/v2/operations``                      -> movimientos de un día.

No contiene reglas de negocio: solo traduce parámetros y devuelve el JSON.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import hashlib
import time

from infrastructure.core.config import (
    DobleCobroAsoSettings,
    load_doble_cobro_aso_settings,
)
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

# Tope de paginas por consulta: evita un bucle infinito si el ASO devuelve una
# paginacion incoherente. Con 100 operaciones por pagina cubre cualquier dia real.
_MAX_PAGES = 20
_PAGE_SIZE = 100


def _flag(name: str, default: bool = False) -> bool:
    """Toggle booleano del entorno (el .env ya esta cargado por config)."""

    raw = (os.getenv(name) or "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _tsec_debug(tsec: str | None) -> dict[str, Any]:
    """Huella verificable del TSEC para trazas.

    Longitud, prefijo, sufijo y SHA256 permiten contrastar con el ASO que se
    envia exactamente el token que devolvio el grantingTicket. El valor completo
    NUNCA se escribe (KYNS IT 3): el flag ``ASO_TRACE_TSEC_FULL`` se retiro.
    """

    if not tsec:
        return {
            "tsec_enviado": False,
            "tsec_motivo": "el llamador no paso tsec: la peticion sale SIN autenticar",
        }

    debug: dict[str, Any] = {
        "tsec_enviado": True,
        "tsec_longitud": len(tsec),
        "tsec_prefijo": tsec[:12],
        # El sufijo permite ver el padding base64 completo.
        "tsec_sufijo": tsec[-8:],
        "tsec_sha256": hashlib.sha256(
            tsec.encode("utf-8")
        ).hexdigest(),
        "tsec_termina_en_padding": tsec.endswith("="),
    }

    # ``ASO_TRACE_TSEC_FULL`` se retiro (KYNS IT 3): la huella basta para
    # comparar tokens sin escribir la credencial de sesion en las trazas.

    return debug


class DobleCobroAsoClient:
    """Cliente HTTP del ASO."""

    def __init__(
        self,
        *,
        settings: DobleCobroAsoSettings | None = None,
        base_url: str | None = None,
        financial_overview_path: str | None = None,
        operations_path: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.settings = settings or load_doble_cobro_aso_settings()
        self.base_url = (base_url or self.settings.base_url).rstrip("/")
        self.financial_overview_path = (
            financial_overview_path or self.settings.financial_overview_path
        ).rstrip("/")
        self.operations_path = (
            operations_path or self.settings.operations_path
        ).rstrip("/")
        self.timeout = (
            timeout if timeout is not None else self.settings.api_timeout
        )

    def _client(self) -> httpx.AsyncClient:
        """Cliente HTTP con la politica de TLS y el timeout configurados.

        verify sale de DC_ASO_API_VERIFY_SSL: el ASO real presenta un
        certificado corporativo, y verificarlo contra la CA publica rompe el
        handshake del grantingTicket antes siquiera de pedir el TSEC.
        """

        return httpx.AsyncClient(
            verify=self.settings.api_verify_ssl,
            timeout=self.timeout,
        )

    async def get_tsec(self) -> str:
        """Solicita el TSEC al grantingTicket del ASO."""

        url = (
            self.settings.ticket_url
            or f"{self.base_url}/TechArchitecture/co/grantingTicket/V02"
        ).strip()

        payload = {
            "authentication": {
                "userID": self.settings.api_user_id,
                "consumerID": self.settings.api_consumer_id,
                "authenticationType": self.settings.api_authentication_type,
                "authenticationData": [
                    {
                        "idAuthenticationData": "password",
                        "authenticationData": [
                            self.settings.api_password
                        ],
                    }
                ],
            },
            "backendUserRequest": {
                "userId": "",
                "accessCode": "",
                "dialogId": "",
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info(
            "DOBLE_COBRO TSEC REQUEST url=%s user_id=%s source=%s verify_ssl=%s timeout=%s",
            url,
            self.settings.api_user_id,
            self.settings.source,
            self.settings.api_verify_ssl,
            self.timeout,
        )

        start = time.perf_counter()

        try:
            async with self._client() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()

            tsec = (
                response.headers.get("tsec")
                or ""
            ).strip() or (response.text or "").strip()

            logger.info(
                "DOBLE_COBRO TSEC RESPONSE status=%s elapsed_ms=%s debug=%s",
                response.status_code,
                round((time.perf_counter() - start) * 1000, 2),
                _tsec_debug(tsec),
            )

            return tsec

        except Exception:
            logger.exception(
                "DOBLE_COBRO TSEC ERROR url=%s",
                url,
            )
            return ""

    # ------------------------------------------------------------------
    # Transporte
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        tsec: str | None,
        operation: str,
    ) -> dict[str, Any] | None:
        """GET al ASO. Devuelve None ante cualquier fallo, nunca propaga."""

        url = f"{self.base_url}{path}"

        headers = {
            "Accept": "application/json",
        }

        if tsec:
            headers["tsec"] = tsec

        # La traza va SIEMPRE, tambien sin tsec. Estaba dentro del if, asi que
        # el unico caso que hacia falta diagnosticar -- la peticion que sale sin
        # autenticar -- era justo el que no dejaba rastro de la peticion.
        logger.info(
            "DOBLE_COBRO ASO REQUEST "
            "operation=%s url=%s params=%s tsec=%s",
            operation,
            url,
            params,
            _tsec_debug(tsec),
        )

        try:
            async with self._client() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                )

            logger.info(
                "DOBLE_COBRO ASO RESPONSE operation=%s status=%s",
                operation,
                response.status_code,
            )

            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict):
                logger.error(
                    "DOBLE_COBRO ASO INVALID RESPONSE operation=%s type=%s",
                    operation,
                    type(payload).__name__,
                )
                return None

            return payload

        except Exception:
            logger.exception(
                "DOBLE_COBRO ASO ERROR operation=%s url=%s tsec=%s",
                operation,
                url,
                _tsec_debug(tsec),
            )
            return None

    # ------------------------------------------------------------------
    # Servicios
    # ------------------------------------------------------------------

    async def financial_overview(self, *, customer_id: str) -> dict[str, Any] | None:
        """Productos del cliente."""

        customer_id = str(customer_id or "").strip()
        if not customer_id:
            logger.error("DOBLE_COBRO ASO FO ERROR customer_id vacío")
            return None

        tsec = await self.get_tsec()

        return await self._get(
            self.financial_overview_path,
            {"customer.id": customer_id},
            tsec=tsec,
            operation="financial_overview",
        )

    async def operations(
        self,
        *,
        operation_date: str,
        card_id: str = "",
        account_id: str = "",
    ) -> dict[str, Any] | None:
        """Operaciones de un día para una tarjeta o una cuenta.

        ``operation_date`` va en formato AAAAMMDD, que es el que filtra el ASO
        en origen. Se recorren todas las páginas y se devuelve un único payload
        con la forma original, para que el normalizador no sepa de paginación.
        """

        card_id = str(card_id or "").strip()
        account_id = str(account_id or "").strip()

        if not card_id and not account_id:
            logger.error("DOBLE_COBRO ASO OPERATIONS ERROR sin cardId ni accountId")
            return None

        blocks: list[Any] = []
        first_payload: dict[str, Any] | None = None

        tsec = await self.get_tsec()

        for page in range(1, _MAX_PAGES + 1):
            params: dict[str, Any] = {
                "operationDate": operation_date,
                "pageSize": _PAGE_SIZE,
                "paginationKey": page,
            }
            if card_id:
                params["cardId"] = card_id
            else:
                params["accountId"] = account_id

            payload = await self._get(
                self.operations_path,
                params,
                tsec=tsec,
                operation="operations",
            )

            if payload is None:
                # Sin respuesta en la primera página no hay dato que devolver;
                # en páginas siguientes se conserva lo ya recuperado.
                return None if first_payload is None else {"data": blocks}

            if first_payload is None:
                first_payload = payload

            blocks.extend(payload.get("data") or [])

            pagination = payload.get("pagination") or {}
            total_pages = int(pagination.get("totalPages") or 1)
            if page >= total_pages:
                break

        return {**(first_payload or {}), "data": blocks}
