"""Cliente ASO minimo: granting (tsec) + order-chanel.

Este servicio NO dispara el push (decision de Luis, 03/09): solo consulta el
estado de un challenge ya creado. Por eso el cliente es deliberadamente
pequeno y sin ningun payload de negocio.

Devuelve SIEMPRE la pareja (estado_negocio | None, error_tecnico): un fallo
de transporte o un 5xx es error tecnico, nunca un rechazo.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from domain.authorization.models import normalizar_estado_aso
from infrastructure.core.config import load_aso_settings

logger = logging.getLogger(__name__)


class AsoAuthorizationClient:
    def __init__(self) -> None:
        self._settings = load_aso_settings()

    async def _obtener_tsec(self, cliente: httpx.AsyncClient) -> str:
        s = self._settings
        cuerpo = {
            "authentication": {
                "userID": s.api_user_id,
                "consumerID": s.api_consumer_id,
                "authenticationType": s.api_authentication_type,
                "authenticationData": [
                    {
                        "idAuthenticationData": "password",
                        "authenticationData": [s.api_password],
                    }
                ],
            },
            "backendUserRequest": {"userId": "", "accessCode": "", "dialogId": ""},
        }
        resp = await cliente.post(
            f"{s.base_url}{s.granting_path}",
            json=cuerpo,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp.raise_for_status()
        # El granting de dev puede responder tsec en cabecera o en el cuerpo
        # (mismo matiz que maneja el servicio TXNR).
        return (resp.headers.get("tsec") or "").strip() or (resp.text or "").strip()

    async def consultar_estado(self, challenge: str) -> tuple[str | None, str]:
        """(estado_negocio, error_tecnico) del challenge en order-chanel."""

        s = self._settings
        url = s.challenge_base_url + s.order_channel_path.format(challenge=challenge)
        try:
            async with httpx.AsyncClient(timeout=s.timeout) as cliente:
                tsec = await self._obtener_tsec(cliente)
                if not tsec:
                    return None, "granting sin tsec"
                resp = await cliente.get(url, headers={"tsec": tsec})
                if resp.status_code >= 500:
                    return None, f"ASO {resp.status_code}"
                if resp.status_code == 404:
                    # El reto no existe (nunca se creo o el ASO lo purgo):
                    # es un dato de negocio no resoluble, no transporte roto.
                    return None, "challenge desconocido en el ASO (404)"
                resp.raise_for_status()
                cuerpo: dict[str, Any] = resp.json() if resp.text.strip() else {}
        except httpx.HTTPError as exc:
            logger.warning(
                "order-chanel inaccesible challenge=%s error=%s", challenge, exc
            )
            return None, f"transporte: {type(exc).__name__}"
        except ValueError:
            return None, "respuesta del ASO no es JSON"

        estado_crudo = (
            ((cuerpo.get("data") or {}).get("status") or {}).get("id")
            if isinstance((cuerpo.get("data") or {}).get("status"), dict)
            else (cuerpo.get("data") or {}).get("status")
        )
        estado = normalizar_estado_aso(estado_crudo)
        if estado is None:
            return None, f"estado no reconocible: {str(estado_crudo)[:60]}"
        return estado, ""
