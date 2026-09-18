"""Worker durable de autorizaciones.

Cada tick (pliego, seccion 4):
  1. busca jobs PENDING con next_check_at <= now y sin lease vigente
  2. CLAIM: escribe lease_until con if_seq_no/if_primary_term -> si otro
     worker gano la carrera (409), suelta el job y sigue
  3. consulta order-chanel UNA vez
  4. aplica resolver_consulta (dominio) -> terminal o next_check_at
  5. persiste (de nuevo con version) y, si es terminal, publica el
     resultado UNA sola vez (result_published con claim)

No hay `while True + sleep` en el agente ni HTTP abierto 180 s: el trabajo
vive en OpenSearch y sobrevive a reinicios y replicas. El deadline lo hace
cumplir ESTE worker aunque el usuario jamas vuelva a la conversacion.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from domain.authorization.models import resolver_consulta
from infrastructure.observability.trace_audit import schedule_trace_event
from infrastructure.core.config import load_worker_settings
from infrastructure.persistence.authorizations_store import ConflictoDeVersion

logger = logging.getLogger(__name__)


class AuthorizationWorker:
    def __init__(self, store: Any, aso_client: Any, publisher: Any) -> None:
        self._store = store
        self._aso = aso_client
        self._publisher = publisher
        self._settings = load_worker_settings()
        self._detener = asyncio.Event()

    async def procesar_uno(self, authorization_id: str, ahora: float | None = None) -> str:
        """Procesa UN job con claim. Devuelve el desenlace del intento.

        'claimed_por_otro' | 'resuelto:<STATUS>' | 'pendiente' | 'error'
        Extraido del loop para poder testearlo sin tiempo real.
        """

        ahora = ahora if ahora is not None else time.time()
        leido = await self._store.obtener_con_version(authorization_id)
        if leido is None:
            return "error"
        job, seq, prim = leido
        if job.es_terminal():
            return f"resuelto:{job.status}"

        # --- claim: el lease es solo un candado temporal entre workers ---
        try:
            await self._store.guardar_si_version(
                job, seq, prim,
                lease_until=ahora + self._settings.lease_segundos,
            )
        except ConflictoDeVersion:
            return "claimed_por_otro"

        # --- consulta unica al ASO ---
        estado, error_tecnico = await self._aso.consultar_estado(job.challenge)
        job = resolver_consulta(
            job, estado, error_tecnico, ahora, self._settings.intervalo_reintento
        )

        # --- persistir el resultado (con la version del claim) ---
        releido = await self._store.obtener_con_version(authorization_id)
        if releido is None:
            return "error"
        _, seq2, prim2 = releido
        try:
            await self._store.guardar_si_version(job, seq2, prim2, lease_until=0.0)
        except ConflictoDeVersion:
            # Otro proceso escribio entre medias: se abandona este intento;
            # el estado que haya quedado manda.
            return "claimed_por_otro"

        if job.es_terminal():
            await self._publicar_una_vez(authorization_id)
            schedule_trace_event(
                event_type="authorization",
                operation="authorization_resolved",
                outcome=job.status.lower(),
                conversation_id=job.conversation_id,
                target="co_pqrs_authorization.worker",
                request_summary={"workflow": job.workflow, "step": job.step,
                                 "attempts": job.attempts},
                response_summary={"status": job.status,
                                  "technical_status": job.technical_status},
                error_message=job.last_error or None,
                tags=["authorization", job.workflow, "resolved", job.status],
            )
            return f"resuelto:{job.status}"
        return "pendiente"

    async def _publicar_una_vez(self, authorization_id: str) -> None:
        """Emite el resultado terminal exactamente UNA vez (claim sobre el flag)."""

        leido = await self._store.obtener_con_version(authorization_id)
        if leido is None:
            return
        job, seq, prim = leido
        if job.result_published:
            return
        job.result_published = True
        try:
            await self._store.guardar_si_version(job, seq, prim, lease_until=0.0)
        except ConflictoDeVersion:
            return  # otro proceso publico primero
        try:
            await self._publisher.publicar(job)
        except Exception:
            logger.exception(
                "Fallo publicando resultado authorization_id=%s (el estado ya es durable)",
                authorization_id,
            )

    async def tick(self) -> int:
        """Un pase completo: procesa el lote de jobs vencidos. -> cuantos toco."""

        ahora = time.time()
        pendientes = await self._store.pendientes_para_revisar(
            ahora, self._settings.lote
        )
        procesados = 0
        for authorization_id in pendientes:
            try:
                resultado = await self.procesar_uno(authorization_id, ahora)
                procesados += 1
                logger.info(
                    "Worker job=%s -> %s", authorization_id, resultado
                )
            except Exception:
                logger.exception("Worker fallo con job=%s", authorization_id)
        return procesados

    async def correr(self) -> None:
        """Loop del worker (arrancado en el lifespan del servicio)."""

        logger.info(
            "Authorization worker arrancado (tick=%ss)", self._settings.intervalo_tick
        )
        while not self._detener.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("Tick del worker fallo; se reintenta")
            try:
                await asyncio.wait_for(
                    self._detener.wait(), timeout=self._settings.intervalo_tick
                )
            except asyncio.TimeoutError:
                continue

    def parar(self) -> None:
        self._detener.set()
