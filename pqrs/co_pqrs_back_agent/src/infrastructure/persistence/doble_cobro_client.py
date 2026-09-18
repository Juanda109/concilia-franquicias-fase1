"""
Cliente del backend co_pqrs_back_doble_cobro.

Agent -> Doble Cobro :8006

El servicio resuelve REGLAS (productos, vigencia, detección de duplicados) y no
persiste nada: el registro del caso vive en OpenSearch y lo escribe el agente,
igual que en transacción no reconocida.

Fail-open, igual que el resto de clientes del agente: cualquier fallo se
registra y se devuelve ``None``; una dependencia degradada nunca rompe el turno
de la conversacion. Cada gate decide como atender ese ``None``.
"""

from __future__ import annotations

from typing import Any

import httpx

from infrastructure.core.config import load_doble_cobro_service_url
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:8006"
_BASE_PATH = "/v0/doble-cobro"
_DEFAULT_TIMEOUT = 10.0


class DobleCobroClient:
    """Cliente HTTP del microservicio Doble Cobro."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (
            base_url or load_doble_cobro_service_url() or _DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Transporte
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.base_url}{_BASE_PATH}{path}"

        logger.info("DOBLE_COBRO SERVICE REQUEST %s %s", method, url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, params=params, json=json_body
                )

            logger.info(
                "DOBLE_COBRO SERVICE RESPONSE %s %s status=%s",
                method,
                url,
                response.status_code,
            )
            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict):
                logger.error("DOBLE_COBRO SERVICE INVALID RESPONSE url=%s", url)
                return None

            return payload

        except Exception:
            logger.exception("DOBLE_COBRO SERVICE ERROR %s %s", method, url)
            return None

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def consultar_productos(
        self,
        *,
        customer_id: str,
        family: str = "",
    ) -> dict[str, Any] | None:
        """Productos activos del cliente, acotados a la familia elegida."""

        customer_id = str(customer_id or "").strip()
        if not customer_id:
            logger.error("DOBLE_COBRO SERVICE ERROR customer_id vacío")
            return None

        return await self._request(
            "GET",
            "/productos-activos",
            params={"customer_id": customer_id, "family": family},
        )

    async def validar_vigencia(
        self,
        *,
        transaction_date: str,
        product_type: str,
        card_brand: str = "",
    ) -> dict[str, Any] | None:
        """Días hábiles de conciliación + vigencia de la fecha reportada."""

        return await self._request(
            "POST",
            "/validar-vigencia",
            json_body={
                "transaction_date": transaction_date,
                "product_type": product_type,
                "card_brand": card_brand,
            },
        )

    async def buscar_grupos(
        self,
        *,
        customer_id: str,
        transaction_date: str,
        amount: float,
        card_id: str = "",
        account_id: str = "",
    ) -> dict[str, Any] | None:
        """Grupos de cobros duplicados del día indicado."""

        return await self._request(
            "POST",
            "/grupos-duplicados",
            json_body={
                "customer_id": customer_id,
                "transaction_date": transaction_date,
                "amount": amount,
                "card_id": card_id,
                "account_id": account_id,
            },
        )
