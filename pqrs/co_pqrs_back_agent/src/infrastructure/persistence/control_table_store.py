"""OpenSearch-backed client control table with app-level TTL handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from infrastructure.core.config import OpenSearchSettings, load_opensearch_settings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.persistence.opensearch_client import OpenSearchClient

logger = get_logger(__name__)


class ControlTableStore:
    """Persist client interaction counters and expire them after a configurable TTL."""

    def __init__(
        self,
        settings: OpenSearchSettings | None = None,
        *,
        env_path: str = ".env",
    ) -> None:
        self.settings = settings or load_opensearch_settings(env_path)
        self.client = OpenSearchClient(self.settings)
        logger.info(
            "ControlTableStore initialized endpoint=%s control_index=%s ttl_days=%s",
            self.settings.endpoint,
            self.settings.control_index,
            self.settings.control_record_ttl_days,
        )

    @log_execution
    async def get_record(self, client_id: str) -> dict[str, Any] | None:
        """Return a control record unless it is expired."""

        record = await self.client.get_document(self.settings.control_index, client_id)

        if record is None:
            return None

        if self._is_expired(record):
            logger.info("Expiring control record client_id=%s", client_id)
            await self.client.delete_by_term(
                self.settings.control_index, "client_id", client_id
            )
            return None

        return record

    @log_execution
    def get_workflow_month_count(
        self,
        record: dict[str, Any] | None,
        workflow_id: str,
        *,
        reference_at: datetime | None = None,
    ) -> int:
        """Return the number of interactions already recorded for the current month."""

        if not record:
            return 0

        month_key = self._month_key(reference_at or datetime.now(timezone.utc))
        monthly_bucket = self._get_month_bucket(record, month_key)
        workflows_bucket = monthly_bucket.get("workflows", {})
        workflow_bucket = workflows_bucket.get(workflow_id, {})

        try:
            return int(workflow_bucket.get("count", 0))
        except (TypeError, ValueError):
            return 0

    @log_execution
    def get_workflow_back_data(
        self,
        record: dict[str, Any] | None,
        workflow_id: str,
        *,
        reference_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Return the back-data payload stored by the co_pqrs_back_data service.

        The back-data service writes results under
        ``monthly[YYYY-MM].workflows[workflow_id].data``.
        """

        if not record:
            return None

        month_key = self._month_key(reference_at or datetime.now(timezone.utc))
        monthly_bucket = self._get_month_bucket(record, month_key)
        workflow_bucket = monthly_bucket.get("workflows", {}).get(workflow_id, {})
        data = workflow_bucket.get("data")
        return data if isinstance(data, dict) else None

    @staticmethod
    def _envelope_from_bucket(workflow_bucket: Any) -> dict[str, Any] | None:
        """Map a persisted workflow bucket to the envelope shape, or None."""

        if not isinstance(workflow_bucket, dict):
            return None
        data = workflow_bucket.get("data")
        return {
            "status": workflow_bucket.get("back_data_status"),
            "run_id": workflow_bucket.get("back_data_run_id"),
            "updated_at": workflow_bucket.get("back_data_updated_at"),
            "data": data if isinstance(data, dict) else None,
            "error": workflow_bucket.get("back_data_error"),
        }

    @log_execution
    def get_workflow_back_data_envelope(
        self,
        record: dict[str, Any] | None,
        workflow_id: str,
        *,
        reference_at: datetime | None = None,
        expected_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the back-data envelope written by co_pqrs_back_data.

        Shape: ``{status, run_id, updated_at, data, error}``. ``data`` is only
        non-None when ``status == "ok"``. Missing fields mean "nothing written"
        (status None), which the caller treats as not-verified.

        Busqueda por MES (C3, 02/09). El mes actual se consulta primero porque es
        donde el sobre deberia estar. Si no aparece ahi y se recibe
        ``expected_run_id``, se buscan los DEMAS meses y se acepta el sobre cuyo
        ``back_data_run_id`` coincida.

        Por que es seguro: ``expected_run_id`` es un UUID nuevo por cada disparo a
        back_data, asi que un sobre de una ejecucion anterior NO puede casar. La
        frescura la garantiza el run_id, no el mes.

        Por que hace falta: el script painless de back_data actualiza el primer
        mes que ya contenga el workflow y, cuando no encuentra ninguno, usa el mes
        de ``last_interaction_at``. Con un cliente que vuelve tras el cambio de
        mes, el sobre puede quedar en un mes anterior mientras el agente lo espera
        en el actual (reproducido en
        ``tests/test_infrastructure/test_control_table_month_bucket.py``).

        SIN ``expected_run_id`` la busqueda NO se amplia: aceptar cualquier sobre
        de cualquier mes serviria un resultado rancio.
        """

        empty = {
            "status": None,
            "run_id": None,
            "updated_at": None,
            "data": None,
            "error": None,
        }
        if not record:
            return empty

        month_key = self._month_key(reference_at or datetime.now(timezone.utc))
        monthly_bucket = self._get_month_bucket(record, month_key)
        actual = self._envelope_from_bucket(
            monthly_bucket.get("workflows", {}).get(workflow_id, {})
        )
        if actual is None:
            return empty

        run_id_esperado = str(expected_run_id or "").strip()

        # El mes en curso manda cuando trae EL sobre que se esta esperando. Sin
        # run_id esperado no se amplia la busqueda: aceptar cualquier sobre de
        # cualquier mes serviria un resultado rancio.
        if not run_id_esperado:
            return actual
        if str(actual["run_id"] or "").strip() == run_id_esperado:
            return actual

        # Aqui el mes en curso NO tiene el sobre de esta ejecucion: puede estar en
        # "pending" (lo dejo asi ``clear_workflow_back_data``) o traer el de una
        # ejecucion anterior. Se buscan los demas meses ANCLANDO al run_id.
        monthly = record.get("monthly")
        if isinstance(monthly, dict):
            for mes, datos_mes in monthly.items():
                if mes == month_key or not isinstance(datos_mes, dict):
                    continue
                workflows = datos_mes.get("workflows")
                if not isinstance(workflows, dict):
                    continue
                candidato = self._envelope_from_bucket(workflows.get(workflow_id))
                if candidato is None:
                    continue
                if str(candidato["run_id"] or "").strip() != run_id_esperado:
                    continue
                logger.warning(
                    "Back-data envelope encontrado en un mes ANTERIOR month=%s "
                    "month_actual=%s workflow_id=%s run_id=%s "
                    "(back_data escribio fuera del mes en curso)",
                    mes,
                    month_key,
                    workflow_id,
                    run_id_esperado,
                )
                return candidato

        # Nada fresco en ningun mes: se devuelve el mes en curso para que el
        # llamador siga sondeando (o agote su presupuesto).
        return actual

    @log_execution
    def describe_back_data_envelopes(
        self,
        record: dict[str, Any] | None,
        workflow_id: str,
        *,
        reference_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Resumen SIN datos de negocio del estado del sobre en el registro.

        Fase 0 (02/09): alimenta la traza de timeout para que el proximo caso se
        diagnostique sin entrar a produccion. Emite METADATOS unicamente -claves
        de mes, estado y run_id truncado-; nunca el contenido de ``data``.
        """

        resumen: dict[str, Any] = {
            "documento_existe": bool(record),
            "mes_actual": self._month_key(reference_at or datetime.now(timezone.utc)),
            "meses_en_el_registro": [],
            "meses_con_el_workflow": [],
            "envelopes": {},
            "expires_at": None,
            "last_interaction_at_mes": None,
        }
        if not record:
            return resumen

        resumen["expires_at"] = record.get("expires_at")
        ultima = record.get("last_interaction_at")
        if isinstance(ultima, str) and len(ultima) >= 7:
            resumen["last_interaction_at_mes"] = ultima[:7]

        monthly = record.get("monthly")
        if not isinstance(monthly, dict):
            return resumen

        resumen["meses_en_el_registro"] = sorted(monthly)
        for mes in sorted(monthly):
            datos_mes = monthly.get(mes)
            if not isinstance(datos_mes, dict):
                continue
            workflows = datos_mes.get("workflows")
            if not isinstance(workflows, dict) or workflow_id not in workflows:
                continue
            resumen["meses_con_el_workflow"].append(mes)
            sobre = self._envelope_from_bucket(workflows.get(workflow_id)) or {}
            run_id = str(sobre.get("run_id") or "")
            resumen["envelopes"][mes] = {
                "status": sobre.get("status"),
                "run_id": run_id[:8] or None,
                "tiene_data": sobre.get("data") is not None,
                "updated_at": sobre.get("updated_at"),
            }
        return resumen

    @log_execution
    def get_last_flow_label(self, record: dict[str, Any] | None) -> str | None:
        """Return the last recorded flow label, if any."""

        if not record:
            return None

        value = str(record.get("last_flow_label", "")).strip()
        return value or None

    @log_execution
    async def record_workflow_completion(
        self,
        *,
        client_id: str,
        workflow_id: str,
        workflow_label: str,
        interaction_at: datetime | None = None,
    ) -> None:
        """Increment the control counters for a completed workflow conversation."""

        now = interaction_at or datetime.now(timezone.utc)
        existing_record = await self.get_record(client_id) or {}
        month_key = self._month_key(now)
        month_bucket = self._get_month_bucket(existing_record, month_key)
        workflows_bucket = month_bucket.setdefault("workflows", {})
        workflow_bucket = workflows_bucket.setdefault(workflow_id, {})

        workflow_bucket["count"] = int(workflow_bucket.get("count", 0) or 0) + 1
        workflow_bucket["last_interaction_at"] = now.isoformat()
        workflow_bucket["label"] = workflow_label

        month_bucket["total_interactions"] = (
            int(month_bucket.get("total_interactions", 0) or 0) + 1
        )
        month_bucket["last_interaction_at"] = now.isoformat()

        total_interactions = int(existing_record.get("total_interactions", 0) or 0) + 1

        record_to_store = {
            **existing_record,
            "client_id": client_id,
            "total_interactions": total_interactions,
            "last_interaction_at": now.isoformat(),
            "last_flow_id": workflow_id,
            "last_flow_label": workflow_label,
            "monthly": {
                **existing_record.get("monthly", {}),
                month_key: month_bucket,
            },
        }

        await self.save_record(record_to_store)

    @log_execution
    def get_daily_session_count(
        self,
        record: dict[str, Any] | None,
        *,
        reference_at: datetime | None = None,
    ) -> int:
        """Return the number of sessions already started for the current day."""

        if not record:
            return 0

        day_key = self._day_key(reference_at or datetime.now(timezone.utc))
        daily_sessions = record.get("daily_sessions", {})

        if not isinstance(daily_sessions, dict):
            return 0

        day_bucket = daily_sessions.get(day_key, {})

        try:
            return int(day_bucket.get("count", 0))
        except (TypeError, ValueError):
            return 0

    @log_execution
    async def record_session_start(
        self,
        client_id: str,
        *,
        interaction_at: datetime | None = None,
    ) -> None:
        """Increment the daily session counter for a client and persist it."""

        now = interaction_at or datetime.now(timezone.utc)
        existing_record = await self.get_record(client_id) or {}
        day_key = self._day_key(now)

        daily_sessions = existing_record.get("daily_sessions", {})
        if not isinstance(daily_sessions, dict):
            daily_sessions = {}

        day_bucket = daily_sessions.get(day_key, {})
        if not isinstance(day_bucket, dict):
            day_bucket = {}

        day_bucket["count"] = int(day_bucket.get("count", 0) or 0) + 1
        day_bucket["last_session_at"] = now.isoformat()

        record_to_store = {
            **existing_record,
            "client_id": client_id,
            "last_session_at": now.isoformat(),
            "daily_sessions": {
                **daily_sessions,
                day_key: day_bucket,
            },
        }

        await self.save_record(record_to_store)

    @log_execution
    def get_category_day_count(
        self,
        record: dict[str, Any] | None,
        category: str,
        *,
        reference_at: datetime | None = None,
    ) -> int:
        """Return the interactions recorded today for a limit category."""

        if not record:
            return 0

        day_key = self._day_key(reference_at or datetime.now(timezone.utc))
        daily_categories = record.get("daily_categories", {})

        if not isinstance(daily_categories, dict):
            return 0

        day_bucket = daily_categories.get(day_key, {})
        if not isinstance(day_bucket, dict):
            return 0

        category_bucket = day_bucket.get(category, {})
        if not isinstance(category_bucket, dict):
            return 0

        try:
            return int(category_bucket.get("count", 0))
        except (TypeError, ValueError):
            return 0

    @log_execution
    def get_category_last_flow_label(
        self,
        record: dict[str, Any] | None,
        category: str,
        *,
        reference_at: datetime | None = None,
    ) -> str | None:
        """Return the last flow label recorded today for a limit category."""

        if not record:
            return None

        day_key = self._day_key(reference_at or datetime.now(timezone.utc))
        daily_categories = record.get("daily_categories", {})
        if not isinstance(daily_categories, dict):
            return None

        day_bucket = daily_categories.get(day_key, {})
        if not isinstance(day_bucket, dict):
            return None

        category_bucket = day_bucket.get(category, {})
        if not isinstance(category_bucket, dict):
            return None

        value = str(category_bucket.get("last_flow_label", "")).strip()
        return value or None

    @log_execution
    async def record_category_interaction(
        self,
        *,
        client_id: str,
        category: str,
        workflow_label: str,
        interaction_at: datetime | None = None,
    ) -> None:
        """Increment the per-category daily counter and store the last flow label."""

        now = interaction_at or datetime.now(timezone.utc)
        existing_record = await self.get_record(client_id) or {}
        day_key = self._day_key(now)

        daily_categories = existing_record.get("daily_categories", {})
        if not isinstance(daily_categories, dict):
            daily_categories = {}

        day_bucket = daily_categories.get(day_key, {})
        if not isinstance(day_bucket, dict):
            day_bucket = {}

        category_bucket = day_bucket.get(category, {})
        if not isinstance(category_bucket, dict):
            category_bucket = {}

        category_bucket["count"] = int(category_bucket.get("count", 0) or 0) + 1
        category_bucket["last_interaction_at"] = now.isoformat()
        category_bucket["last_flow_label"] = workflow_label

        record_to_store = {
            **existing_record,
            "client_id": client_id,
            "last_interaction_at": now.isoformat(),
            "daily_categories": {
                **daily_categories,
                day_key: {
                    **day_bucket,
                    category: category_bucket,
                },
            },
        }

        await self.save_record(record_to_store)

    @log_execution
    def get_recheck_count(
        self,
        record: dict[str, Any] | None,
        category: str,
        *,
        reference_at: datetime | None = None,
    ) -> int:
        """Return the repeat-flow re-checks (insistences) shown today for a category."""

        if not record:
            return 0

        day_key = self._day_key(reference_at or datetime.now(timezone.utc))
        daily_rechecks = record.get("daily_rechecks", {})

        if not isinstance(daily_rechecks, dict):
            return 0

        day_bucket = daily_rechecks.get(day_key, {})
        if not isinstance(day_bucket, dict):
            return 0

        category_bucket = day_bucket.get(category, {})
        if not isinstance(category_bucket, dict):
            return 0

        try:
            return int(category_bucket.get("count", 0))
        except (TypeError, ValueError):
            return 0

    @log_execution
    async def record_recheck(
        self,
        client_id: str,
        category: str,
        *,
        interaction_at: datetime | None = None,
    ) -> None:
        """Increment the daily repeat-flow re-check (insistence) counter for a category."""

        now = interaction_at or datetime.now(timezone.utc)
        existing_record = await self.get_record(client_id) or {}
        day_key = self._day_key(now)

        daily_rechecks = existing_record.get("daily_rechecks", {})
        if not isinstance(daily_rechecks, dict):
            daily_rechecks = {}

        day_bucket = daily_rechecks.get(day_key, {})
        if not isinstance(day_bucket, dict):
            day_bucket = {}

        category_bucket = day_bucket.get(category, {})
        if not isinstance(category_bucket, dict):
            category_bucket = {}

        category_bucket["count"] = int(category_bucket.get("count", 0) or 0) + 1
        category_bucket["last_recheck_at"] = now.isoformat()

        record_to_store = {
            **existing_record,
            "client_id": client_id,
            "daily_rechecks": {
                **daily_rechecks,
                day_key: {
                    **day_bucket,
                    category: category_bucket,
                },
            },
        }

        await self.save_record(record_to_store)

    @log_execution
    def is_blocked_for_day(
        self,
        record: dict[str, Any] | None,
        *,
        reference_at: datetime | None = None,
    ) -> bool:
        """Whether the client is blocked from all consultations for today.

        Set when the client insisted on an already-capped category up to the
        re-check limit: from that point ALL consultations (any category) are
        blocked for the rest of the day.
        """

        if not record:
            return False

        day_key = self._day_key(reference_at or datetime.now(timezone.utc))
        blocked_days = record.get("blocked_days", {})
        if not isinstance(blocked_days, dict):
            return False
        return bool(blocked_days.get(day_key, False))

    @log_execution
    async def set_blocked_for_day(
        self,
        client_id: str,
        *,
        interaction_at: datetime | None = None,
    ) -> None:
        """Mark the client as blocked from all consultations for the rest of today."""

        now = interaction_at or datetime.now(timezone.utc)
        existing_record = await self.get_record(client_id) or {}
        day_key = self._day_key(now)

        blocked_days = existing_record.get("blocked_days", {})
        if not isinstance(blocked_days, dict):
            blocked_days = {}

        record_to_store = {
            **existing_record,
            "client_id": client_id,
            "blocked_days": {
                **blocked_days,
                day_key: True,
            },
        }

        await self.save_record(record_to_store)

    @log_execution
    async def clear_workflow_back_data(
        self,
        *,
        client_id: str,
        workflow_id: str,
        reference_at: datetime | None = None,
    ) -> None:
        """Reset the back-data envelope for a workflow to 'pending' in the current month.

        Drops ``data``, ``back_data_run_id`` and ``back_data_error`` and marks
        ``back_data_status = "pending"`` so a stale successful result (with an
        old run_id) is never served to the agent after a fresh trigger.

        OJO (C5, 02/09): las claves se anulan con NULOS EXPLICITOS, no omitiendolas.
        ``save_record`` persiste con ``POST /_update`` + ``doc`` + ``doc_as_upsert``,
        que es un merge RECURSIVO: solo agrega o sobreescribe claves, nunca las
        elimina. Omitir una clave la dejaba INTACTA, asi que la limpieza no limpiaba
        nada y el proposito declarado de esta funcion no se cumplia. El lector trata
        un ``data`` que no es dict como ausente, asi que ``None`` equivale a borrado.
        """

        existing_record = await self.get_record(client_id)
        if not existing_record:
            return

        month_key = self._month_key(reference_at or datetime.now(timezone.utc))
        month_bucket = self._get_month_bucket(existing_record, month_key)
        workflows_bucket = month_bucket.get("workflows", {})
        workflow_bucket = workflows_bucket.get(workflow_id)

        if not isinstance(workflow_bucket, dict):
            return
        # Nothing to reset if there is neither cached data nor an envelope.
        if not (
            "data" in workflow_bucket
            or "back_data_status" in workflow_bucket
            or "back_data_run_id" in workflow_bucket
        ):
            return

        sanitized_workflow_bucket = {
            key: value
            for key, value in workflow_bucket.items()
            if key not in {"data", "back_data_run_id", "back_data_error"}
        }
        sanitized_workflow_bucket["back_data_status"] = "pending"
        # Nulos explicitos: el merge recursivo no borra claves ausentes.
        sanitized_workflow_bucket["data"] = None
        sanitized_workflow_bucket["back_data_run_id"] = None
        sanitized_workflow_bucket["back_data_error"] = None
        updated_workflows_bucket = {
            **workflows_bucket,
            workflow_id: sanitized_workflow_bucket,
        }
        updated_month_bucket = {
            **month_bucket,
            "workflows": updated_workflows_bucket,
        }
        updated_record = {
            **existing_record,
            "monthly": {
                **existing_record.get("monthly", {}),
                month_key: updated_month_bucket,
            },
        }
        await self.save_record(updated_record)

    @log_execution
    async def save_record(self, record: dict[str, Any]) -> None:
        """Save or refresh a client control record and its TTL metadata."""

        client_id = str(record["client_id"]).strip()
        now = datetime.now(timezone.utc)
        updated_at_value = record.get("updated_at")

        record_to_store = {
            **record,
            "client_id": client_id,
            "updated_at": self._serialize_datetime(updated_at_value) or now.isoformat(),
            "expires_at": self._compute_expires_at(now).isoformat(),
        }

        await self.client.update_document(
            self.settings.control_index,
            client_id,
            record_to_store,
            upsert=True,
        )

    def _is_expired(self, record: dict[str, Any]) -> bool:
        """Return whether the record is older than the configured TTL."""

        expires_at = record.get("expires_at")
        if expires_at:
            parsed_expires_at = self._parse_datetime(expires_at)
            if parsed_expires_at is not None:
                return parsed_expires_at <= datetime.now(timezone.utc)

        updated_at = record.get("updated_at")
        parsed_updated_at = self._parse_datetime(updated_at)

        if parsed_updated_at is None:
            return False

        return parsed_updated_at + timedelta(
            days=self.settings.control_record_ttl_days
        ) <= datetime.now(timezone.utc)

    def _get_month_bucket(
        self, record: dict[str, Any], month_key: str
    ) -> dict[str, Any]:
        """Return the persisted monthly bucket for a specific YYYY-MM key."""

        monthly = record.setdefault("monthly", {})
        month_bucket = monthly.get(month_key)

        if not isinstance(month_bucket, dict):
            month_bucket = {}
            monthly[month_key] = month_bucket

        return month_bucket

    def _month_key(self, value: datetime) -> str:
        """Format a datetime into the month bucket key used by the control table."""

        normalized_value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized_value.astimezone().strftime("%Y-%m")

    def _day_key(self, value: datetime) -> str:
        """Format a datetime into the daily bucket key (``yyyymmdd``).

        Uses the local calendar date so it stays consistent with the
        ``user_id_yyyymmdd`` conversation identifier built by the agent.
        """

        normalized_value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized_value.astimezone().strftime("%Y%m%d")

    def _compute_expires_at(self, now: datetime) -> datetime:
        """Compute the application-managed expiration timestamp."""

        return now + timedelta(days=self.settings.control_record_ttl_days)

    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse an ISO timestamp or datetime-like value safely."""

        if value is None:
            return None

        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        if not isinstance(value, str) or not value.strip():
            return None

        try:
            parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Control-table has an invalid datetime value: %s", value)
            return None

        return (
            parsed_value
            if parsed_value.tzinfo
            else parsed_value.replace(tzinfo=timezone.utc)
        )

    def _serialize_datetime(self, value: Any) -> str | None:
        """Serialize datetime-like values to an ISO timestamp string."""

        if value is None:
            return None

        if isinstance(value, datetime):
            normalized_value = (
                value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            )
            return normalized_value.isoformat()

        if isinstance(value, str) and value.strip():
            return value.strip()

        return None
