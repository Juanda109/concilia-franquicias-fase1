"""Puerto de publicacion del resultado de una autorizacion.

Hoy el repo no tiene consumidor de eventos en el agente (Rabbit existe solo
como publicacion fire-and-forget hacia analitica), asi que la integracion
inicial es deliberadamente simple: el resultado queda DURABLE en el store y
el agente lo LEE via API. Este puerto deja lista la interfaz para evolucionar
a un broker sin tocar el worker (pliego, seccion 7).

El evento minimo: authorization_id, conversation_id, workflow, step, status,
timestamp.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ResultPublisher(Protocol):
    async def publicar(self, job: Any) -> None: ...


def _evento(job: Any) -> dict[str, Any]:
    return {
        "event": f"AUTHORIZATION_{job.status}",
        "authorization_id": job.authorization_id,
        "conversation_id": job.conversation_id,
        "workflow": job.workflow,
        "step": job.step,
        "status": job.status,
        "timestamp": time.time(),
    }


class LogResultPublisher:
    """Implementacion por defecto: traza estructurada (INFO) del evento.

    Suficiente para observabilidad hoy; el contrato del evento ya esta
    definido para cuando exista un consumidor real.
    """

    async def publicar(self, job: Any) -> None:
        logger.info(
            "AUTHORIZATION RESULT %s",
            json.dumps(_evento(job), ensure_ascii=False),
        )
