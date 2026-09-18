"""Registro DURABLE de casos en OpenSearch (índice dedicado, SIN TTL).

A diferencia del control-table (TTL 30 días), este índice conserva los casos
indefinidamente para: (a) recurrencia-bot (¿el cliente ya pasó por op4?),
(b) auditoría/RPA. Se recomienda además una copia en bucket (fuera de este store).

El índice atiende a MÁS DE UN FLUJO (transacción no reconocida y doble cobro),
así que el identificador del documento incluye el tipo de notificación: un mismo
cliente puede tener un caso abierto en cada flujo y no deben pisarse. Antes el
id era solo el ``client_id``, de modo que el segundo flujo reemplazaba el
``trx_case_state_snapshot`` del primero y perdía sus transacciones.

El tipo viaja también como campo (``tipo_de_notificacion``) para que el job de
exportación sepa de qué flujo es cada ficha sin tener que interpretar el id.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from infrastructure.core.config import OpenSearchSettings, load_opensearch_settings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.opensearch_client import OpenSearchClient

logger = get_logger(__name__)

DEFAULT_TRX_CASES_INDEX = "trx-no-reconocida-cases"

# Tipos de notificación que escriben en este índice. Coinciden con el nombre del
# workflow en el catálogo, para que no haya que traducir entre ambos mundos.
NOTIFICATION_TRX_NO_RECONOCIDA = "trx_no_reconocida"
NOTIFICATION_DOBLE_COBRO = "doble_cobro"


class TrxCaseStore:
    """Persistencia durable (sin TTL) de casos de Transacción No Reconocida."""

    def __init__(
        self,
        settings: OpenSearchSettings | None = None,
        *,
        index: str | None = None,
        env_path: str = ".env",
    ) -> None:
        self.settings = settings or load_opensearch_settings(env_path)
        self.index = (index or os.getenv("TRX_CASES_INDEX") or DEFAULT_TRX_CASES_INDEX).strip()
        self.client = OpenSearchClient(self.settings)
        logger.info("TrxCaseStore initialized endpoint=%s index=%s", self.settings.endpoint, self.index)

    @staticmethod
    def document_id(client_id: str, tipo_de_notificacion: str) -> str:
        """Identificador de la ficha dentro del índice.

        Transacción no reconocida CONSERVA su id histórico (el ``client_id`` a
        secas). Prefijarlo dejaría huérfanas las fichas ya guardadas en
        producción y reiniciaría los contadores de recurrencia. Los flujos
        nuevos sí llevan prefijo, que es lo que evita la colisión.
        """

        cid = str(client_id).strip()
        tipo = str(tipo_de_notificacion or "").strip()
        if not tipo or tipo == NOTIFICATION_TRX_NO_RECONOCIDA:
            return cid
        return f"{tipo}_{cid}"

    @log_execution
    async def get_case(
        self,
        client_id: str,
        *,
        tipo_de_notificacion: str = NOTIFICATION_TRX_NO_RECONOCIDA,
    ) -> dict[str, Any] | None:
        """Devuelve el registro durable del flujo indicado (NO expira)."""
        return await self.client.get_document(
            self.index,
            self.document_id(client_id, tipo_de_notificacion),
        )

    def get_bot_recurrence_count(
        self,
        record: dict[str, Any] | None,
        *,
        months: int = 6,
        reference_at: datetime | None = None,
    ) -> int:
        """Cuántas veces el cliente entró al flujo (op4) dentro de la ventana."""
        if not record:
            return 0
        reference = reference_at or datetime.now(timezone.utc)
        threshold = reference - timedelta(days=months * 30)
        count = 0
        for entry in record.get("entries") or []:
            parsed = self._parse_dt(entry)
            if parsed is not None and parsed >= threshold:
                count += 1
        return count

    @log_execution
    async def record_milestone(
        self,
        *,
        client_id: str,
        conversation_id: str,
        milestone: str,
        snapshot: dict[str, Any] | None = None,
        outcome: str | None = None,
        at: datetime | None = None,
        tipo_de_notificacion: str = NOTIFICATION_TRX_NO_RECONOCIDA,
    ) -> None:
        """Registra un hito del caso (entered_op4, reached_block, completed_report...)."""
        now = at or datetime.now(timezone.utc)
        cid = str(client_id).strip()
        doc_id = self.document_id(cid, tipo_de_notificacion)
        record = await self.get_case(
            cid, tipo_de_notificacion=tipo_de_notificacion
        ) or {
            "client_id": cid,
            "created_at": now.isoformat(),
            "milestones": [],
            "entries": [],
        }

        milestones = list(record.get("milestones") or [])
        if milestone and milestone not in milestones:
            milestones.append(milestone)

        entries = list(record.get("entries") or [])
        if milestone == "entered_op4":
            entries.append(now.isoformat())

        record.update(
            {
                # `client_id` se guarda SIEMPRE pelado, sin el prefijo del tipo:
                # es el número que el job entrega a Tantia.
                "client_id": cid,
                "tipo_de_notificacion": str(tipo_de_notificacion or "").strip()
                or NOTIFICATION_TRX_NO_RECONOCIDA,
                "conversation_id": conversation_id,
                "updated_at": now.isoformat(),
                "milestones": milestones,
                "entries": entries,
            }
        )
        if outcome is not None:
            record["outcome"] = outcome
        if snapshot is not None:
            record["trx_case_state_snapshot"] = snapshot

        await self.client.update_document(self.index, doc_id, record, upsert=True)

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
