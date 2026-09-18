"""Dominio de la autorizacion OOB: job, estados y normalizacion.

Separacion deliberada (pliego de Luis, 03/09):

- ESTADO DE NEGOCIO: que decidio el cliente / el tiempo.
    PENDING | ACCEPTED | REJECTED | EXPIRED
- ESTADO TECNICO: que paso con la ultima consulta al ASO.
    SUCCESS | BUSINESS_RESULT | TECHNICAL_ERROR

Un fallo del ASO JAMAS se convierte en REJECTED: "el usuario rechazo" y
"no pude preguntar" son cosas distintas. El deadline (180 s por defecto)
lo controla el backend: al vencer, el worker marca EXPIRED aunque nadie
haya vuelto a preguntar.

Este modulo NO conoce reglas de TXNR ni de ningun workflow: `workflow` y
`step` son metadatos opacos que viajan de vuelta en el resultado.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# ---- estados de negocio ----
PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"

ESTADOS_TERMINALES = frozenset({ACCEPTED, REJECTED, EXPIRED})

# ---- estados tecnicos de la ultima consulta ----
TECH_SUCCESS = "SUCCESS"
TECH_BUSINESS_RESULT = "BUSINESS_RESULT"
TECH_ERROR = "TECHNICAL_ERROR"

DEADLINE_SEGUNDOS_DEFAULT = 180.0

# Sinonimos observados en el ASO real y el simulador (mismas familias que
# ya maneja el agente; se re-declaran aqui porque este servicio no importa
# codigo de otros modulos).
_ACEPTADO = frozenset({
    "accepted", "accept", "approved", "approve", "authorized", "authorised",
    "autorizado", "autorizada", "aprobado", "aprobada",
})
_RECHAZADO = frozenset({
    "rejected", "reject", "denied", "deny", "declined", "cancelled",
    "canceled", "refused", "unauthorized", "not_authorized", "not-authorized",
    "rechazado", "rechazada", "denegado", "denegada", "cancelado", "cancelada",
})
_VENCIDO = frozenset({
    "expired", "expire", "timeout", "timed_out", "timed-out",
    "vencido", "vencida",
})
_PENDIENTE = frozenset({
    "pending", "pendiente", "processing", "in_progress", "in-progress",
    "waiting", "wait", "created", "initiated",
})


def normalizar_estado_aso(estado_crudo: Any) -> str | None:
    """Estado de negocio a partir del id que entrega order-chanel.

    Devuelve None cuando el valor no es reconocible: el llamador decide si
    eso es TECHNICAL_ERROR (nunca un rechazo implicito). "ok"/"success" NO
    significan aceptado: son palabras de sobre, no del reto (leccion del
    normalizador del agente, 28/08).
    """

    texto = str(estado_crudo or "").strip().casefold()
    if not texto:
        return None
    if texto in _ACEPTADO:
        return ACCEPTED
    if texto in _RECHAZADO:
        return REJECTED
    if texto in _VENCIDO:
        return EXPIRED
    if texto in _PENDIENTE:
        return PENDING
    return None


def authorization_id_desde(idempotency_key: str) -> str:
    """Id DETERMINISTA a partir de la idempotency_key.

    Dos peticiones de creacion equivalentes producen el MISMO id, y la
    creacion en el store usa create-if-absent: no puede haber dos jobs
    para la misma clave aunque lleguen en paralelo a pods distintos.
    """

    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"auth-{digest[:24]}"


@dataclass
class AuthorizationJob:
    """El job persistido: todo lo que el worker necesita para operar solo."""

    authorization_id: str
    conversation_id: str
    workflow: str
    step: str
    challenge: str
    idempotency_key: str
    status: str = PENDING
    technical_status: str = TECH_SUCCESS
    created_at: float = 0.0
    deadline: float = 0.0
    next_check_at: float = 0.0
    attempts: int = 0
    resolved_at: float | None = None
    result_published: bool = False
    last_error: str = ""
    # metadatos opacos del solicitante (viajan de vuelta; NO se interpretan)
    metadata: dict[str, Any] = field(default_factory=dict)

    def es_terminal(self) -> bool:
        return self.status in ESTADOS_TERMINALES

    def vencido(self, ahora: float) -> bool:
        return bool(self.deadline) and ahora > self.deadline

    def a_documento(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "conversation_id": self.conversation_id,
            "workflow": self.workflow,
            "step": self.step,
            "challenge": self.challenge,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "technical_status": self.technical_status,
            "created_at": self.created_at,
            "deadline": self.deadline,
            "next_check_at": self.next_check_at,
            "attempts": self.attempts,
            "resolved_at": self.resolved_at,
            "result_published": self.result_published,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }

    @classmethod
    def desde_documento(cls, doc: dict[str, Any]) -> "AuthorizationJob":
        return cls(
            authorization_id=str(doc.get("authorization_id") or ""),
            conversation_id=str(doc.get("conversation_id") or ""),
            workflow=str(doc.get("workflow") or ""),
            step=str(doc.get("step") or ""),
            challenge=str(doc.get("challenge") or ""),
            idempotency_key=str(doc.get("idempotency_key") or ""),
            status=str(doc.get("status") or PENDING),
            technical_status=str(doc.get("technical_status") or TECH_SUCCESS),
            created_at=float(doc.get("created_at") or 0.0),
            deadline=float(doc.get("deadline") or 0.0),
            next_check_at=float(doc.get("next_check_at") or 0.0),
            attempts=int(doc.get("attempts") or 0),
            resolved_at=doc.get("resolved_at"),
            result_published=bool(doc.get("result_published")),
            last_error=str(doc.get("last_error") or ""),
            metadata=dict(doc.get("metadata") or {}),
        )


def resolver_consulta(
    job: AuthorizationJob,
    estado_aso: str | None,
    error_tecnico: str,
    ahora: float,
    intervalo_reintento: float,
) -> AuthorizationJob:
    """Aplica UNA consulta del worker sobre el job y devuelve el job mutado.

    Reglas (pliego, seccion 5):
    - accepted/rejected del ASO  -> terminal BUSINESS_RESULT.
    - pending                    -> sigue PENDING, next_check_at avanza.
    - deadline vencido           -> terminal EXPIRED (BUSINESS_RESULT):
      el tiempo es una decision de negocio, no un fallo.
    - fallo tecnico              -> TECHNICAL_ERROR, se reintenta; NUNCA
      degrada a REJECTED. Si el deadline vence entre errores, EXPIRED.
    """

    job.attempts += 1

    if error_tecnico:
        job.technical_status = TECH_ERROR
        job.last_error = error_tecnico[:300]
        if job.vencido(ahora):
            job.status = EXPIRED
            job.technical_status = TECH_BUSINESS_RESULT
            job.resolved_at = ahora
        else:
            job.next_check_at = ahora + intervalo_reintento
        return job

    job.last_error = ""
    if estado_aso in (ACCEPTED, REJECTED):
        job.status = estado_aso
        job.technical_status = TECH_BUSINESS_RESULT
        job.resolved_at = ahora
        return job
    if estado_aso == EXPIRED or job.vencido(ahora):
        job.status = EXPIRED
        job.technical_status = TECH_BUSINESS_RESULT
        job.resolved_at = ahora
        return job

    # pending explicito o estado no reconocible SIN error de transporte:
    # se sigue esperando dentro de la ventana.
    job.status = PENDING
    job.technical_status = TECH_SUCCESS if estado_aso == PENDING else TECH_ERROR
    if job.technical_status == TECH_ERROR:
        job.last_error = "estado del ASO no reconocible"
    job.next_check_at = ahora + intervalo_reintento
    return job
