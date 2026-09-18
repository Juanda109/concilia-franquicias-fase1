"""API v1 de autorizaciones: crear y consultar.

Contrato minimo del pliego (seccion 6). La creacion NO dispara el push
(decision de Luis, 03/09): recibe el challenge ya creado por el flujo que
inicio la ceremonia, y desde ahi este servicio es dueno del ciclo de vida.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from application.authorization.service import AuthorizationService


class CrearAutorizacionRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    workflow: str = Field(..., min_length=1)
    step: str = Field(..., min_length=1)
    challenge: str = Field(..., min_length=1)
    idempotency_key: str = ""
    # metadatos OPACOS del solicitante (device_id, profile_id, last_four...):
    # viajan de vuelta en las consultas; este servicio no los interpreta.
    metadata: dict = Field(default_factory=dict)


class AutorizacionResponse(BaseModel):
    authorization_id: str
    conversation_id: str
    workflow: str
    step: str
    status: str
    technical_status: str
    deadline: float
    attempts: int
    created: bool | None = None


def _respuesta(job, created: bool | None = None) -> AutorizacionResponse:
    return AutorizacionResponse(
        authorization_id=job.authorization_id,
        conversation_id=job.conversation_id,
        workflow=job.workflow,
        step=job.step,
        status=job.status,
        technical_status=job.technical_status,
        deadline=job.deadline,
        attempts=job.attempts,
        created=created,
    )


def construir_router(service: AuthorizationService) -> APIRouter:
    router = APIRouter(prefix="/v1/authorizations", tags=["authorizations"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def crear(cuerpo: CrearAutorizacionRequest) -> AutorizacionResponse:
        job, creada = await service.crear(
            conversation_id=cuerpo.conversation_id,
            workflow=cuerpo.workflow,
            step=cuerpo.step,
            challenge=cuerpo.challenge,
            idempotency_key=cuerpo.idempotency_key,
            metadata=cuerpo.metadata,
        )
        return _respuesta(job, created=creada)

    @router.get("/{authorization_id}")
    async def obtener(authorization_id: str) -> AutorizacionResponse:
        job = await service.obtener(authorization_id)
        if job is None:
            raise HTTPException(status_code=404, detail="authorization not found")
        return _respuesta(job)

    @router.get("")
    async def por_conversacion(conversation_id: str) -> list[AutorizacionResponse]:
        jobs = await service.por_conversacion(conversation_id)
        return [_respuesta(j) for j in jobs]

    return router
