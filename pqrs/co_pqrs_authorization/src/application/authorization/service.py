"""Casos de uso del servicio de autorizacion: crear y consultar.

La creacion es idempotente por diseno: el authorization_id deriva de la
idempotency_key y el store hace create-if-absent, asi que dos peticiones
equivalentes (doble clic, reintento del agente, dos pods) devuelven el
MISMO job sin registrar dos autorizaciones.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from domain.authorization.models import (
    AuthorizationJob,
    authorization_id_desde,
)
from infrastructure.core.config import load_deadline_segundos
from infrastructure.observability.trace_audit import schedule_trace_event

logger = logging.getLogger(__name__)


class AuthorizationService:
    def __init__(self, store: Any) -> None:
        self._store = store

    async def crear(
        self,
        *,
        conversation_id: str,
        workflow: str,
        step: str,
        challenge: str,
        idempotency_key: str = "",
        metadata: dict[str, Any] | None = None,
        deadline_segundos: float | None = None,
    ) -> tuple[AuthorizationJob, bool]:
        """Registra una autorizacion (o devuelve la existente). -> (job, creada)."""

        clave = idempotency_key.strip() or f"{conversation_id}:{step}:{challenge}"
        ahora = time.time()
        ventana = deadline_segundos or load_deadline_segundos()
        job = AuthorizationJob(
            authorization_id=authorization_id_desde(clave),
            conversation_id=conversation_id,
            workflow=workflow,
            step=step,
            challenge=challenge,
            idempotency_key=clave,
            created_at=ahora,
            deadline=ahora + ventana,
            next_check_at=ahora,  # el worker puede consultarla de inmediato
            metadata=dict(metadata or {}),
        )
        persistido, creada = await self._store.crear_si_no_existe(job)
        schedule_trace_event(
            event_type="authorization",
            operation="authorization_created" if creada else "authorization_duplicate",
            outcome="ok",
            conversation_id=conversation_id,
            target="co_pqrs_authorization",
            request_summary={"workflow": workflow, "step": step, "has_challenge": bool(challenge)},
            response_summary={"authorization_id": persistido.authorization_id, "status": persistido.status},
            tags=["authorization", workflow, "created" if creada else "idempotent"],
        )
        logger.info(
            "Autorizacion %s conversation_id=%s workflow=%s step=%s challenge=%s",
            "creada" if creada else "ya existia (idempotente)",
            conversation_id, workflow, step, bool(challenge),
        )
        return persistido, creada

    async def obtener(self, authorization_id: str) -> AuthorizationJob | None:
        return await self._store.obtener(authorization_id)

    async def por_conversacion(self, conversation_id: str) -> list[AuthorizationJob]:
        return await self._store.buscar_por_conversacion(conversation_id)
