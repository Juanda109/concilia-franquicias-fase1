"""Adapter del agente hacia co_pqrs_authorization (Fase 3 del plan de Luis).

Mismo patron que back_data_client/trx_client: timeouts cortos, fail-open y
cero conocimiento de negocio. El agente registra la autorizacion (con el
challenge que creo el flujo) y despues LEE el estado ya resuelto por el
worker del servicio -- aqui no se consulta el ASO ni se decide nada.

NOTA (Fase 4 pendiente): este cliente todavia NO esta cableado en
chat_service; la migracion del gate se hara como cambio aparte y quirurgico.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0


async def registrar_autorizacion(
    *,
    base_url: str,
    conversation_id: str,
    workflow: str,
    step: str,
    challenge: str,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """POST /v1/authorizations. Fail-open: None si el servicio no responde."""

    if not base_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as cliente:
            resp = await cliente.post(
                f"{base_url.rstrip('/')}/v1/authorizations",
                json={
                    "conversation_id": conversation_id,
                    "workflow": workflow,
                    "step": step,
                    "challenge": challenge,
                    "idempotency_key": idempotency_key,
                    "metadata": dict(metadata or {}),
                },
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "authorization no disponible al registrar conversation_id=%s error=%s",
            conversation_id,
            exc,
        )
        return None


async def consultar_autorizacion(
    *, base_url: str, authorization_id: str
) -> dict[str, Any] | None:
    """GET /v1/authorizations/{id}. Fail-open: None si no responde o no existe."""

    if not base_url or not authorization_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as cliente:
            resp = await cliente.get(
                f"{base_url.rstrip('/')}/v1/authorizations/{authorization_id}"
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "authorization no disponible al consultar id=%s error=%s",
            authorization_id,
            exc,
        )
        return None
