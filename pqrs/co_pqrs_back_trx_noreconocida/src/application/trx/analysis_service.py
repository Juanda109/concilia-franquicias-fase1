"""
Application service for the unrecognized-transaction path.
Conforms to the sequence diagram specs and ID MSG protocols (201, 202, 203, 204).
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from domain.trx.models import TrxCase, TrxResult
from infrastructure.core.config import (
    load_postgres_settings,
    load_identity_csv_path,
    load_trx_aso_settings,
    load_trx_source_settings,
)
from infrastructure.core.logger import get_logger
from infrastructure.observability.trace_audit import schedule_trace_event

logger = get_logger(__name__)


def _mocks_allowed() -> bool:
    """Guardrail global: con ``TRX_ALLOW_MOCKS=false`` NINGUN camino puede usar mocks.

    Se usa cuando el entorno apunta a Postgres/ASO reales (QA/prod), para que un
    fallo de infraestructura NUNCA se disfrace de datos simulados.
    """

    import os as _os

    raw = (_os.getenv("TRX_ALLOW_MOCKS") or "true").strip().casefold()
    return raw in {"1", "true", "yes", "on"}


def _aso_is_real() -> bool:
    """True si el toggle de ASO apunta al ASO real."""

    import os as _os

    return (_os.getenv("ASO_SOURCE") or "simulator").strip().casefold() == "real"


class TrxAnalysisService:
    """Orchestrator for trx_noreconocida path matching sequence diagram spec."""

    _IDENTITY_DOC_TYPE_COLUMNS = (
        "personal_type",
        "document_type",
        "doc_type",
        "identity_document_type",
    )
    _IDENTITY_DOC_NUMBER_COLUMNS = (
        "personal_id",
        "document_number",
        "doc_number",
        "identity_document_number",
    )

    def _normalize_customer_id(self, value: str | None) -> str:
        """Normalize IDs so leading zeros do not break comparisons."""

        raw = str(value or "").strip()
        if not raw:
            return ""
        normalized = raw.lstrip("0")
        return normalized or "0"

    def _normalize_doc_type(self, value: str | None) -> str:
        """Normalize document type preserving leading zeros (01)."""

        raw = str(value or "").strip()
        return raw

    def _request_tsec(self) -> str:
        """Request a TSEC ticket from the ASO mock login endpoint."""

        settings = load_trx_aso_settings()
        if not settings.ticket_url:
            return ""

        try:
            import httpx
        except ImportError:
            logger.exception("httpx is required for TSEC request")
            return ""

        payload = {
            "authentication": {
                "userID": settings.api_user_id,
                "consumerID": settings.api_consumer_id,
                "authenticationType": settings.api_authentication_type,
                "authenticationData": [
                    {
                        "idAuthenticationData": "password",
                        "authenticationData": [settings.api_password],
                    }
                ],
            },
            "backendUserRequest": {
                "userId": "",
                "accessCode": "",
                "dialogId": "",
            },
        }

        try:
            with httpx.Client(verify=settings.api_verify_ssl, timeout=settings.api_timeout) as client:
                response = client.post(
                    settings.ticket_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
            response.raise_for_status()
        except Exception:
            logger.exception("TSEC request failed ticket_url=%s", settings.ticket_url)
            return ""

        return response.headers.get("tsec", "").strip() or response.text.strip()

    def _load_identity_from_postgres(
        self,
        customer_id: str,
    ) -> tuple[str, str] | None:
        """Resolve (document_type, document_number) for a customer from Postgres."""

        settings = load_postgres_settings()
        if settings is None:
            logger.warning(
                "Identity lookup skipped: missing DB settings customer_id=%s",
                customer_id,
            )
            return None

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            logger.exception("psycopg is required for identity lookup")
            return None

        query = (
            f"SELECT * FROM {settings.table} "
            "WHERE customer_id = %s "
            "OR NULLIF(LTRIM(customer_id, '0'), '') = NULLIF(LTRIM(%s, '0'), '') "
            "LIMIT 1"
        )
        params = (customer_id.strip(), customer_id.strip())
        connection_settings = {
            "host": settings.host,
            "port": settings.port,
            "dbname": settings.database,
            "user": settings.user,
            "password": settings.password,
            "connect_timeout": settings.connect_timeout,
            "row_factory": dict_row,
        }

        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
        except Exception:
            logger.exception(
                "Identity lookup failed customer_id=%s table=%s",
                customer_id,
                settings.table,
            )
            return None

        if not isinstance(row, dict):
            return None

        doc_type = ""
        for column in self._IDENTITY_DOC_TYPE_COLUMNS:
            raw_doc_type = row.get(column)
            if raw_doc_type is None:
                continue
            doc_type = self._normalize_doc_type(str(raw_doc_type))
            if doc_type:
                break

        doc_number = ""
        for column in self._IDENTITY_DOC_NUMBER_COLUMNS:
            raw_doc_number = row.get(column)
            if raw_doc_number is None:
                continue
            doc_number = str(raw_doc_number).strip()
            if doc_number:
                break

        if not doc_type or not doc_number:
            return None

        return doc_type, doc_number

    def get_trx_identity_by_card(
        self,
        *,
        customer_id: str,
        last_four: str,
        origin_flag: str = "TDC",
    ) -> dict[str, str]:
        """Obtiene account_id y personal_id para una tarjeta TXNR.

        Antes vivia en co_pqrs_back_data (mismo nombre, via HTTP GET
        /trx/account-id); TXNR es el UNICO consumidor de ese endpoint, asi
        que la consulta se trae aqui tal cual y se conecta directo a Postgres.
        """

        normalized_customer_id = str(customer_id or "").strip()
        normalized_last_four = str(last_four or "").strip()
        normalized_origin_flag = str(origin_flag or "TDC").strip()

        if not normalized_customer_id or not normalized_last_four:
            logger.warning(
                "TXNR identity lookup skipped: customer_id/last_four vacio "
                "customer_id=%s last_four=%s",
                normalized_customer_id,
                normalized_last_four,
            )
            return {
                "account_id": self._synthetic_account_id_if_local_contingency(
                    normalized_last_four
                ),
                "personal_id": "",
            }

        settings = load_postgres_settings()
        if settings is None:
            logger.warning(
                "TXNR identity lookup skipped: missing DB settings customer_id=%s",
                normalized_customer_id,
            )
            csv_identity = self._load_identity_from_csv(
                customer_id=normalized_customer_id,
                last_four=normalized_last_four,
                origin_flag=normalized_origin_flag,
            )
            if csv_identity:
                return csv_identity
            return {
                "account_id": self._synthetic_account_id_if_local_contingency(
                    normalized_last_four
                ),
                "personal_id": "",
            }

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            logger.exception("psycopg is required for TXNR identity lookup")
            return {
                "account_id": self._synthetic_account_id_if_local_contingency(
                    normalized_last_four
                ),
                "personal_id": "",
            }

        query = (
            f"SELECT account_id, personal_id FROM {settings.table} "
            "WHERE customer_id = %s "
            "AND origin_flag = %s "
            "AND last_four_pan_id = %s "
            "LIMIT 1"
        )
        params = (
            normalized_customer_id,
            normalized_origin_flag,
            normalized_last_four,
        )
        connection_settings = {
            "host": settings.host,
            "port": settings.port,
            "dbname": settings.database,
            "user": settings.user,
            "password": settings.password,
            "connect_timeout": settings.connect_timeout,
            "row_factory": dict_row,
        }

        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
        except Exception:
            logger.exception(
                "TXNR identity lookup failed customer_id=%s table=%s",
                normalized_customer_id,
                settings.table,
            )
            return {
                "account_id": self._synthetic_account_id_if_local_contingency(
                    normalized_last_four
                ),
                "personal_id": "",
            }

        if not row:
            logger.warning(
                "TXNR identity no encontrada customer_id=%s last_four=%s",
                normalized_customer_id,
                normalized_last_four,
            )
            return {
                "account_id": self._synthetic_account_id_if_local_contingency(
                    normalized_last_four
                ),
                "personal_id": "",
            }

        return {
            "account_id": str(row.get("account_id") or "").strip(),
            "personal_id": str(row.get("personal_id") or "").strip(),
        }

    def _load_identity_from_csv(
        self,
        *,
        customer_id: str,
        last_four: str = "",
        origin_flag: str = "",
    ) -> dict[str, str]:
        """Read the local TXNR identity/address fixture when DB is unavailable."""

        path = Path(load_identity_csv_path())
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                for raw_row in reader:
                    row = {
                        str(key or "").strip(): str(value or "").strip()
                        for key, value in raw_row.items()
                    }
                    if row.get("customer_id") != customer_id:
                        continue
                    if last_four and row.get("last_four_pan_id") != last_four:
                        continue
                    if origin_flag and row.get("origin_flag") != origin_flag:
                        continue
                    return {
                        "account_id": row.get("account_id", ""),
                        "personal_id": row.get("personal_id", ""),
                        "customer_address": row.get("customer_address", ""),
                    }
        except (OSError, csv.Error):
            logger.exception("TXNR identity CSV lookup failed path=%s", path)
        return {}

    def _synthetic_account_id_if_local_contingency(self, last_four: str) -> str:
        """account_id sintetico para pruebas locales sin Postgres real.

        Formato que el simulador ASO acepta: 20 digitos que terminan en los
        ultimos 4 del PAN. Solo se activa con LOCAL_CONTINGENCY_MODE=true.
        """

        import os as _os

        raw = (_os.getenv("LOCAL_CONTINGENCY_MODE") or "").strip().casefold()
        if raw not in {"1", "true", "yes", "on"}:
            return ""
        suffix = (last_four or "0000").strip()[-4:].zfill(4)
        return f"0013006700020094{suffix}"

    def _parse_salesforce_date(self, value: str) -> datetime | None:
        """Parse Salesforce date values like 2026-07-03T10:05:28.000-0500."""

        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
        return None

    def _load_salesforce_mock_payload(
        self,
        case: TrxCase,
        source_settings: Any,
    ) -> dict[str, Any] | None:
        """Load Salesforce mock payload from case.data or an optional JSON file."""

        inline_payload = case.data.get("salesforce_mock")
        if isinstance(inline_payload, dict):
            return inline_payload

        file_path = str(
            getattr(source_settings, "salesforce_mock_file", "") or ""
        ).strip()
        if not file_path:
            return None

        try:
            payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except Exception:
            logger.exception(
                "Could not read Salesforce mock file path=%s",
                file_path,
            )
            return None
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {"data": payload}
        return None

    def _real_salesforce_recurrence(self, case: TrxCase) -> dict[str, Any]:
        """Recurrencia usando el ASO REAL de Salesforce (sin mocks).

        Devuelve además ``error`` cuando el ASO no responde, para que el flujo NO
        confunda "no hay recurrencia" con "no se pudo consultar".
        """

        from application.trx.aso_rules import recurrencia_por_subject
        from infrastructure.core.config import load_trx_flow_settings
        from infrastructure.persistence.aso_client import TrxAsoClient

        identity = self._load_identity_from_postgres(case.customer_id)
        target_user_id = ""
        if identity is not None:
            doc_type, doc_number = identity
            target_user_id = f"{doc_type}-{doc_number}"
        if not target_user_id:
            # Sin identidad (Postgres) no se puede consultar el ASO real.
            return {
                "has_recurrence": False,
                "target_user_id": "",
                "tsec_requested": False,
                "matched_total": 0,
                "recent_total": 0,
                "error": "identity_not_found",
            }

        client = TrxAsoClient()
        tsec = client.get_tsec()
        payload = client.salesforce_issues(target_user_id, tsec=tsec)
        if payload is None:
            return {
                "has_recurrence": False,
                "target_user_id": target_user_id,
                "tsec_requested": bool(tsec),
                "matched_total": 0,
                "recent_total": 0,
                "error": "aso_unavailable",
            }

        rows = payload.get("data") if isinstance(payload, dict) else None
        issues = rows if isinstance(rows, list) else []
        flow = load_trx_flow_settings()
        rec = recurrencia_por_subject(
            issues,
            subjects_txnr=flow.subjects_txnr,
            now=datetime.utcnow(),
            months=flow.recurrencia_meses,
            max_solicitudes=flow.max_bot_recurrence,
        )
        return {
            "has_recurrence": rec["has_recurrence"],
            "target_user_id": target_user_id,
            "tsec_requested": bool(tsec),
            "matched_total": rec["matched_total"],
            "recent_total": rec["recent_total"],
        }

    def _mock_salesforce_recurrence(self, case: TrxCase) -> dict[str, Any]:
        """Return recurrence details from the ASO seam or an ASO-style mock payload."""

        source_settings = load_trx_source_settings()
        identity = self._load_identity_from_postgres(case.customer_id)
        target_user_id = ""
        if identity is not None:
            doc_type, doc_number = identity
            target_user_id = f"{doc_type}-{doc_number}"

        tsec = self._request_tsec()

        # TRX_SALESFORCE_SOURCE=aso -> la costura real: TrxAsoClient decide
        # simulator o real segun ASO_SOURCE, igual que productos y movimientos.
        # Antes salesforce_issues() era codigo muerto y la recurrencia solo
        # leia el fichero mock local: el escenario A del simulador no podia
        # funcionar sin montar su fixture a mano (hallazgo H-04).
        # `source_used` viaja hasta la traza: una recurrencia decidida por el
        # mock de fallback tiene que ser distinguible de una respuesta real
        # del ASO, porque ese dato decide el REDIRECT_PQR.
        payload: dict[str, Any] | None = None
        source_used = "mock"
        if source_settings.salesforce_source == "aso":
            if not target_user_id:
                source_used = "aso_fallback_sin_identidad"
                logger.warning(
                    "TRX Salesforce: source=aso pero sin identidad en Postgres "
                    "customer_id=%s; usando mock local",
                    case.customer_id,
                )
            else:
                from infrastructure.persistence.aso_client import TrxAsoClient

                client = TrxAsoClient()
                # El TSEC se pide al propio cliente ASO, que deriva el granting
                # ticket de ASO_BASE_URL (como los endpoints de trx_router). El
                # legacy _request_tsec() depende de TRX_TICKET_URL, que el
                # configmap desplegado deja vacio: sin esto la costura llamaba
                # sin tsec, recibia 401 y caia SIEMPRE al mock en silencio.
                aso_tsec = client.get_tsec() or tsec or None
                # tsec_requested reporta el ticket que se USO en la llamada, no
                # el legacy: desde que el TSEC lo pide TrxAsoClient (granting
                # ticket via ASO_BASE_URL), el campo decia False aunque el
                # ticket se hubiera pedido y usado -- un dato de traza que
                # enganaba justo donde se audita la llamada al ASO.
                tsec = aso_tsec or tsec
                aso_payload = client.salesforce_issues(target_user_id, aso_tsec)
                if isinstance(aso_payload, dict):
                    payload = aso_payload
                    source_used = "aso"
                else:
                    source_used = "aso_fallback_error"
                    logger.warning(
                        "Salesforce ASO sin respuesta; fallback al mock local customer_id=%s",
                        case.customer_id,
                    )
        if payload is None:
            payload = self._load_salesforce_mock_payload(case, source_settings)

        if isinstance(payload, dict) and "identificacion_6_meses" in payload:
            forced = bool(payload.get("identificacion_6_meses"))
            return {
                "has_recurrence": forced,
                "target_user_id": target_user_id,
                "tsec_requested": bool(tsec),
                "source_used": "mock_forzado",
                "matched_total": 0,
                "recent_total": 1 if forced else 0,
            }

        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                from application.trx.aso_rules import recurrencia_por_subject
                from infrastructure.core.config import load_trx_flow_settings

                flow = load_trx_flow_settings()
                customer_id = self._normalize_customer_id(case.customer_id)
                normalized_doc_number = self._normalize_customer_id(
                    target_user_id.split("-", maxsplit=1)[1]
                    if "-" in target_user_id
                    else ""
                )

                def _belongs(row: dict[str, Any]) -> bool:
                    issuer = row.get("issuer") if isinstance(row, dict) else None
                    iddoc = issuer.get("identityDocument") if isinstance(issuer, dict) else None
                    row_doc = self._normalize_customer_id(
                        str((iddoc or {}).get("documentNumber") or "")
                    )
                    return row_doc == customer_id or (
                        bool(normalized_doc_number) and row_doc == normalized_doc_number
                    )

                customer_rows = [r for r in rows if isinstance(r, dict) and _belongs(r)]
                rec = recurrencia_por_subject(
                    customer_rows,
                    subjects_txnr=flow.subjects_txnr,
                    now=datetime.utcnow(),
                    months=flow.recurrencia_meses,
                    max_solicitudes=flow.max_bot_recurrence,
                )
                return {
                    "has_recurrence": rec["has_recurrence"],
                    "target_user_id": target_user_id,
                    "tsec_requested": bool(tsec),
                    "source_used": source_used,
                    "matched_total": rec["matched_total"],
                    "recent_total": rec["recent_total"],
                }

        forced_flag = bool(case.data.get("identificacion_6_meses", False))
        return {
            "has_recurrence": forced_flag,
            "target_user_id": target_user_id,
            "tsec_requested": bool(tsec),
            "source_used": source_used,
            "matched_total": 0,
            "recent_total": 1 if forced_flag else 0,
        }

    def _load_products_from_postgres(
        self, customer_id: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Lee productos del cliente en PostgreSQL.

        Devuelve ``(rows, error)``:
        - ``([], None)``  -> la consulta corrió y el cliente NO tiene filas.
        - ``([], "...")`` -> FALLO de infraestructura (settings/driver/conexión).
        Distinguirlos es obligatorio: con Postgres real NUNCA se cae a mocks, y un
        error de infra no puede confundirse con "cliente sin productos".
        """

        settings = load_postgres_settings()
        if settings is None:
            logger.warning(
                "Postgres source selected but DB settings are missing customer_id=%s",
                customer_id,
            )
            return [], "missing_db_settings"

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            logger.exception("psycopg is required for postgres product source")
            return [], "psycopg_not_installed"

        query = (
            f"SELECT * FROM {settings.table} "
            "WHERE customer_id = %s "
            "OR NULLIF(LTRIM(customer_id, '0'), '') = NULLIF(LTRIM(%s, '0'), '')"
        )
        params = (customer_id.strip(), customer_id.strip())
        connection_settings = {
            "host": settings.host,
            "port": settings.port,
            "dbname": settings.database,
            "user": settings.user,
            "password": settings.password,
            "connect_timeout": settings.connect_timeout,
            "row_factory": dict_row,
        }

        start = time.perf_counter()
        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
        except Exception as exc:
            logger.exception(
                "Postgres products read failed customer_id=%s table=%s",
                customer_id,
                settings.table,
            )
            schedule_trace_event(
                event_type="postgres",
                operation="productos_activos",
                outcome="error",
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                target=settings.table,
                customer_id=customer_id,
                request_summary={"params_count": len(params)},
                error_type=type(exc).__name__,
                error_message=str(exc),
                tags=["postgres", "productos"],
            )
            return [], f"db_error:{type(exc).__name__}"

        result_rows = [row for row in rows if isinstance(row, dict)]
        # Normalize/mapping: ensure a canonical `customer_address` and
        # `last_four_pan_id` exist on each row regardless of source column names.
        for row in result_rows:
            try:
                # customer_address: accept several possible column names
                if not row.get("customer_address"):
                    for alt in (
                        "customer_address",
                        "address",
                        "direccion",
                        "address_line",
                        "full_address",
                        "customer_address_line",
                    ):
                        if alt in row and row.get(alt):
                            row["customer_address"] = str(row.get(alt) or "").strip()
                            break

                # last_four_pan_id: normalize from various possible columns
                if not row.get("last_four_pan_id"):
                    for alt in ("last_four", "pan_last4", "masked_pan", "last4"):
                        if alt in row and row.get(alt):
                            val = str(row.get(alt) or "").strip()
                            # keep only the last 4 chars when appropriate
                            row["last_four_pan_id"] = val[-4:] if len(val) >= 4 else val
                            break
            except Exception:
                # Non-fatal: do not break product loading on normalization errors
                logger.debug("product row normalization failed", exc_info=True)
        schedule_trace_event(
            event_type="postgres",
            operation="productos_activos",
            outcome="ok",
            elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
            target=settings.table,
            customer_id=customer_id,
            request_summary={"params_count": len(params)},
            response_summary={"rows": len(result_rows)},
            tags=["postgres", "productos"],
        )
        # Devolvemos las filas CRUDAS de ada_info_detail; el filtro del flujo TXNR
        # (vigente/activo + origin_flag + card_flag) lo aplica aso_rules.filtrar_productos.
        return result_rows, None

    def resolve_customer_address_from_postgres(self, customer_id: str) -> str:
        """Direccion del cliente directo de Postgres (ada_info_detail).

        Reutiliza `_load_products_from_postgres`: con TRX_PRODUCTS_SOURCE=fo
        (el modo activo hoy) el array de productos NUNCA trae customer_address
        -- el financial-overview no la conoce -- asi que hay que ir a Postgres
        aparte para esta unica columna. Fail-open: cualquier fallo devuelve "".
        """

        if load_postgres_settings() is None:
            row = self._load_identity_from_csv(customer_id=customer_id)
            return str(row.get("customer_address") or "").strip()

        rows, error = self._load_products_from_postgres(customer_id)
        if error:
            logger.warning(
                "Customer address lookup failed customer_id=%s error=%s",
                customer_id,
                error,
            )
            return ""
        for row in rows:
            direccion = str(row.get("customer_address") or "").strip()
            if direccion:
                return direccion
        return ""

    # =========================================================================
    # PASO 2.4.0.1: VALIDACIÓN DE RECURRENCIA SALESFORCE (ID MSG 201)
    # =========================================================================
    def consultar_recurrencia_salesforce(self, case: TrxCase) -> TrxResult:
        """
        Paso 2.4.0.1: Consulta en Salesforce si tiene consultas en los últimos 6 meses.
        """
        logger.info("Paso 2.4.0.1: consultar_recurrencia_salesforce customer_id=%s", case.customer_id)

        source_settings = load_trx_source_settings()
        mocks_allowed = _mocks_allowed()
        salesforce_source = (source_settings.salesforce_source or "").strip().casefold()
        # Con ASO real, TRX_SALESFORCE_SOURCE!=mock, o mocks deshabilitados => ASO REAL.
        use_real = (
            not mocks_allowed
            or _aso_is_real()
            or salesforce_source in {"aso_real", "real", "api"}
        )
        if use_real:
            recurrence = self._real_salesforce_recurrence(case)
            source_label = "aso_real"
        else:
            recurrence = self._mock_salesforce_recurrence(case)
            source_label = (
                "aso_mock"
                if salesforce_source in {"aso", "mock", "aso_mock"}
                else source_settings.salesforce_source
            )
        recurrence_error = str(recurrence.get("error") or "")
        tiene_consulta_6_meses = bool(recurrence.get("has_recurrence"))
        target_user_id = str(recurrence.get("target_user_id") or "")
        # Union del merge: dev calcula source_label (aso_real/mock) y costuras
        # aporta el 'source_used' real de la consulta; gana el segundo si existe.
        source_label = str(recurrence.get("source_used") or source_label)

        schedule_trace_event(
            event_type="recurrencia",
            operation="recurrencia_salesforce",
            outcome=(
                "error" if recurrence_error
                else ("redirect_pqr" if tiene_consulta_6_meses else "ok")
            ),
            customer_id=case.customer_id,
            request_summary={"source": source_label, "target_user_id": target_user_id},
            response_summary={
                "has_recurrence": tiene_consulta_6_meses,
                "matched_total": recurrence.get("matched_total"),
                "recent_total": recurrence.get("recent_total"),
            },
            error_message=recurrence_error or None,
            tags=["recurrencia", "salesforce"],
        )

        if recurrence_error:
            # No se pudo verificar recurrencia con el ASO real: NO se asume "sin
            # recurrencia" ni se usan mocks; se reporta error al orquestador.
            logger.error(
                "Recurrencia REAL fallo customer_id=%s error=%s",
                case.customer_id,
                recurrence_error,
            )
            return TrxResult(
                status="error",
                id_message=201,
                step="2.4.0.1",
                detail="No fue posible verificar la recurrencia en Salesforce.",
                data={
                    "identificacion_6_meses": False,
                    "source": source_label,
                    "error": recurrence_error,
                },
            )

        if tiene_consulta_6_meses:
            return TrxResult(
                status="REDIRECT_PQR",
                id_message=201,
                step="2.4.0.1",
                detail="El cliente registra consultas en la tipología en los últimos 6 meses.",
                data={
                    "identificacion_6_meses": True,
                    "action": "REDIRECT_PQR",
                    "source": source_label,
                    "targetUserId": target_user_id,
                    "tsec_requested": bool(recurrence.get("tsec_requested")),
                    "matched_total": int(recurrence.get("matched_total") or 0),
                    "recent_total": int(recurrence.get("recent_total") or 0),
                },
            )

        return TrxResult(
            status="ok",
            id_message=201,
            step="2.4.0.1",
            detail="Validación Salesforce OK (Sin recurrencia en 6 meses).",
            data={
                "identificacion_6_meses": False,
                "action": "CONTINUE",
                "source": source_label,
                "targetUserId": target_user_id,
                "tsec_requested": bool(recurrence.get("tsec_requested")),
                "matched_total": int(recurrence.get("matched_total") or 0),
                "recent_total": int(recurrence.get("recent_total") or 0),
            },
        )

    # =========================================================================
    # PASO 2.4.0.2: CONSULTA PRODUCTOS VIGENTES DE POSTGRES / ADA (ID MSG 202)
    # =========================================================================
    def consultar_productos_activos(self, case: TrxCase) -> TrxResult:
        """
        Paso 2.4.0.1.4: productos vigentes en Postgres (ADA) para TXNR.
        Filtro (doc): contract_status_type_desc VIGENTE u ACTIVO (la Postgres real
        trae ACTIVO) + origin_flag in {TDC,Pasivo}
        + card_flag=true. Ver aso_rules.filtrar_productos.
        """
        logger.info("Paso 2.4.0.1.4: consultar_productos_activos customer_id=%s", case.customer_id)

        from application.trx.aso_rules import filtrar_productos

        source_settings = load_trx_source_settings()
        mocks_allowed = _mocks_allowed()

        # MOCK explícito: SOLO si la fuente es mock y los mocks están permitidos.
        mock_rows = case.data.get("mock_ada_products", [
            {
                "contract_id": "4912680517944979",
                "last_four_pan_id": "4979",
                "contract_status_type_desc": "ACTIVO",
                "origin_flag": "TDC",
                "card_type": "M",
                "customer_address": "Calle de Prueba 123",
                "card_flag": True,
                "card_brand": "VISA",
                "product_desc": "Tarjeta de Credito",
                "commercial_product_desc": "Tarjeta de Credito",
            },
            {
                "contract_id": "00320011234567",
                "last_four_pan_id": "4567",
                "contract_status_type_desc": "VIGENTE",
                "origin_flag": "PASIVO",
                "customer_address": "Calle de Prueba 123",
                "card_flag": True,
                "card_brand": "MASTERCARD",
                "product_desc": "Cuenta de Ahorros",
                "commercial_product_desc": "Cuenta de Ahorros",
            },
            {
                "contract_id": "4912680517940060",
                "last_four_pan_id": "0060",
                "contract_status_type_desc": "ACTIVO",
                "origin_flag": "TDC",
                "card_type": "M",
                "customer_address": "Calle de Prueba 123",
                "card_flag": True,
                "card_brand": "VISA",
                "product_desc": "Tarjeta de Credito",
                "commercial_product_desc": "VISA ORO LM",
            },
        ])

        rows: list[dict[str, Any]]
        # El origen REAL de las filas, que no siempre es el configurado.
        fuente_real = source_settings.products_source
        if source_settings.products_source in {"fo", "financial_overview", "financial-overview"}:
            # FINANCIAL-OVERVIEW (roadmap PO 24/08): se salta la Consulta ADA y
            # el portafolio se valida directamente con el FO (solo customer.id).
            # Fail-closed: si el FO no contesta, error honesto -- nunca "no
            # tienes productos". La direccion NO viaja en el FO: se intenta
            # enriquecer desde Postgres en modo fail-open (solo direccion; un
            # fallo ahi no bloquea la validacion de productos).
            from application.trx.aso_rules import productos_desde_fo
            from infrastructure.persistence.aso_client import TrxAsoClient

            aso = TrxAsoClient()
            fo = aso.financial_overview(
                customer_id=case.customer_id,
                tsec=aso.get_tsec(),
            )
            if fo is None:
                logger.error(
                    "financial-overview FAILED para productos (fail-closed) customer_id=%s",
                    case.customer_id,
                )
                return TrxResult(
                    status="error",
                    id_message=202,
                    step="2.4.0.1.4",
                    detail="No fue posible consultar los productos en el financial-overview.",
                    data={
                        "products": [],
                        "origin_flag": "FO",
                        "source": fuente_real,
                        "error": "fo_error",
                    },
                )

            productos_validos = productos_desde_fo(fo)

            # solo-FO v3 (24/08): Postgres/ADA no se consulta y el array ya no
            # lleva customer_address (el FO no trae direccion). El agente lee
            # el campo con .get() tolerante y el .17.2 degrada al copy
            # generico. Cuando exista la fuente real (servicio de datos de la
            # NET del roadmap) se reintroduce aqui.

            schedule_trace_event(
                event_type="validation",
                operation="filtrar_productos",
                outcome="ok" if productos_validos else "empty",
                customer_id=case.customer_id,
                request_summary={
                    "rows_in": len((((fo or {}).get("data") or {}).get("contracts"))
                                   or (fo or {}).get("contracts") or []),
                    "source": fuente_real,
                },
                response_summary={
                    "valid_out": len(productos_validos),
                    "kept_last4": [str(p.get("last_four") or "")[-4:] for p in productos_validos][:5],
                    "regla": "productType=CARD + status OPERATIVE/ACTIVATED + subProductType DEBIT/CREDIT + BLOCKABLE",
                },
                tags=["validation", "productos", "fo"],
            )

            if not productos_validos:
                return TrxResult(
                    status="not_found",
                    id_message=202,
                    step="2.4.0.1.4",
                    detail="No se encontraron tarjetas operativas en el financial-overview.",
                    data={"products": [], "origin_flag": "FO", "source": fuente_real},
                )

            return TrxResult(
                status="ok",
                id_message=202,
                step="2.4.0.1.4",
                detail="Productos validados con el financial-overview.",
                data={
                    "products": productos_validos,
                    "origin_flag": "FO",
                    "source": fuente_real,
                },
            )

        if source_settings.products_source in {"postgres", "postgresql", "db"}:
            # DEPRECADO (solo-FO, 24/08): la fuente de productos es el
            # financial-overview. Esta rama queda un ciclo como via de escape y
            # se retira en H5 con el OK de Fabian.
            logger.warning(
                "TRX_PRODUCTS_SOURCE=%s esta DEPRECADO: la fuente de productos "
                "es el financial-overview (fo). Esta rama se retirara.",
                source_settings.products_source,
            )
            # POSTGRES REAL: prohibido caer a mocks. Un error de infraestructura se
            # reporta como error (NO como "cliente sin productos").
            rows, db_error = self._load_products_from_postgres(case.customer_id)
            if db_error:
                logger.error(
                    "Postgres products FAILED (sin fallback mock) customer_id=%s error=%s",
                    case.customer_id,
                    db_error,
                )
                return TrxResult(
                    status="error",
                    id_message=202,
                    step="2.4.0.1.4",
                    detail="No fue posible consultar los productos del cliente en Postgres.",
                    data={
                        "products": [],
                        "origin_flag": "ADA",
                        "source": source_settings.products_source,
                        "error": db_error,
                    },
                )
        elif mocks_allowed:
            rows = mock_rows
        else:
            # Fuente mock pedida pero mocks deshabilitados (TRX_ALLOW_MOCKS=false).
            logger.error(
                "products_source=%s es mock pero TRX_ALLOW_MOCKS=false customer_id=%s",
                source_settings.products_source,
                case.customer_id,
            )
            return TrxResult(
                status="error",
                id_message=202,
                step="2.4.0.1.4",
                detail="Fuente de productos mock deshabilitada por configuración.",
                data={
                    "products": [],
                    "origin_flag": "ADA",
                    "source": source_settings.products_source,
                    "error": "mocks_disabled",
                },
            )

        productos_validos = filtrar_productos(rows)

        # Traza de la VALIDACION de productos (cuantos entraron/quedaron y por que).
        schedule_trace_event(
            event_type="validation",
            operation="filtrar_productos",
            outcome="ok" if productos_validos else "empty",
            customer_id=case.customer_id,
            request_summary={"rows_in": len(rows), "source": fuente_real},
            response_summary={
                "valid_out": len(productos_validos),
                "dropped": max(len(rows) - len(productos_validos), 0),
                "kept_last4": [str(p.get("last_four_pan_id") or "")[-4:] for p in productos_validos][:5],
                "regla": "contract_status_type_desc in {VIGENTE,ACTIVO} + origin_flag in {TDC,PASIVO} + card_flag=true",
            },
            tags=["validation", "productos"],
        )

        if not productos_validos:
            return TrxResult(
                status="not_found",
                id_message=202,
                step="2.4.0.1.4",
                detail="No se encontraron productos vigentes con tarjeta asociada.",
                data={"products": [], "origin_flag": "ADA", "source": fuente_real},
            )

        return TrxResult(
            status="ok",
            id_message=202,
            step="2.4.0.1.4",
            detail="Productos vigentes consultados correctamente.",
            data={
                "products": productos_validos,
                "origin_flag": "ADA",
                "source": fuente_real,
                "customer_address": (
                    str(productos_validos[0].get("customer_address") or "")
                    if productos_validos else ""
                ),
            },
        )

    # =========================================================================
    # PASO 2.4.0.3: VIGENCIA POR FRANQUICIA + MOVIMIENTOS (ID MSG 203 / 204)
    # =========================================================================
    _FRANCHISE_VIGENCIA_DAYS = {"VISA": 180, "MASTER": 120, "MASTERCARD": 120}

    def _parse_user_date(self, value: str) -> datetime | None:
        """Parse a user date in DD/MM/AAAA (or ISO) into a naive datetime."""

        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _load_movements_mock(
        self,
        customer_id: str,
        contract_id: str,
        fecha_iso: str,
    ) -> list[dict[str, Any]]:
        """Load mock movements filtered by customer + product + date (YYYY-MM-DD).

        Simula una consulta a BD/ASO: al cambiar TRX_MOVEMENTS_SOURCE a
        postgres/aso, esta función se reemplaza por el repositorio real y el
        resto del flujo no cambia.
        """

        source_settings = load_trx_source_settings()
        path = source_settings.movements_mock_file
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Could not read movements mock file path=%s", path)
            return []

        if isinstance(payload, dict):
            rows = payload.get("movements") or payload.get("data") or []
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []

        norm_customer = self._normalize_customer_id(customer_id)
        norm_contract = str(contract_id or "").strip()
        result: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if self._normalize_customer_id(row.get("customer_id")) != norm_customer:
                continue
            if norm_contract and str(row.get("contract_id") or "").strip() != norm_contract:
                continue
            if fecha_iso and str(row.get("movement_date") or "").strip() != fecha_iso:
                continue
            result.append(row)
        return result

    def consultar_movimientos_aso(self, case: TrxCase) -> TrxResult:
        """
        Paso 2.4.0.3: valida la vigencia por franquicia (VISA 180 / MASTER 120)
        contada desde la fecha indicada y lista los movimientos del producto+fecha.
        """
        logger.info("Paso 2.4.0.3: consultar_movimientos_aso customer_id=%s", case.customer_id)

        source_settings = load_trx_source_settings()
        data = case.data or {}
        contract_id = str(
            data.get("contract_id") or data.get("product_id") or case.product_id or ""
        ).strip()
        card_franchise = str(
            data.get("card_franchise") or data.get("card_brand") or "VISA"
        ).strip().upper()
        raw_date = str(data.get("fecha") or data.get("date") or "").strip()

        parsed = self._parse_user_date(raw_date)
        if parsed is None:
            return TrxResult(
                status="not_found",
                id_message=203,
                step="2.4.0.3",
                detail="No pude interpretar la fecha. Usa el formato DD/MM/AAAA.",
                data={"fecha": raw_date, "invalid_date": True},
            )
        fecha_iso = parsed.strftime("%Y-%m-%d")

        # Vigencia por franquicia contada desde la fecha indicada.
        max_dias = self._FRANCHISE_VIGENCIA_DAYS.get(card_franchise, 120)
        dias = (datetime.now() - parsed).days
        if dias > max_dias:
            return TrxResult(
                status="not_found",
                id_message=203,
                step="2.4.0.3",
                detail="La fecha supera el plazo permitido por la franquicia para reportar la transacción.",
                data={
                    "fecha": fecha_iso,
                    "card_franchise": card_franchise,
                    "max_dias": max_dias,
                    "dias": dias,
                    "vencida": True,
                },
            )

        movimientos: list[dict[str, Any]] = []
        if source_settings.movements_source in {"mock", "aso_mock"}:
            if _mocks_allowed():
                movimientos = self._load_movements_mock(case.customer_id, contract_id, fecha_iso)
            else:
                # TRX_ALLOW_MOCKS=false (ASO/Postgres reales): NO se usan movimientos mock.
                logger.error(
                    "movements_source=mock pero TRX_ALLOW_MOCKS=false customer_id=%s",
                    case.customer_id,
                )
                return TrxResult(
                    status="error",
                    id_message=203,
                    step="2.4.0.3",
                    detail="Fuente de movimientos mock deshabilitada por configuración.",
                    data={
                        "fecha": fecha_iso,
                        "contract_id": contract_id,
                        "card_franchise": card_franchise,
                        "vencida": False,
                        "movimientos": [],
                        "error": "mocks_disabled",
                    },
                )
        # source 'aso'/'postgres' -> el flujo F4 usa /v1/trx/movimientos-aso (ASO real).

        if not movimientos:
            return TrxResult(
                status="not_found",
                id_message=203,
                step="2.4.0.3",
                detail="No encontramos movimientos en la fecha seleccionada para este producto.",
                data={
                    "fecha": fecha_iso,
                    "contract_id": contract_id,
                    "card_franchise": card_franchise,
                    "vencida": False,
                    "movimientos": [],
                },
            )

        return TrxResult(
            status="ok",
            id_message=204,
            step="2.4.0.3",
            detail="Movimientos encontrados.",
            data={
                "fecha": fecha_iso,
                "contract_id": contract_id,
                "card_franchise": card_franchise,
                "max_dias": max_dias,
                "movimientos": movimientos,
                "source": source_settings.movements_source,
            },
        )

    def evaluar_transaccion_individual(
        self,
        current_trx_monto: float,
        accumulated_trxs: list[dict[str, Any]] | None = None,
    ) -> TrxResult:
        """Evaluate a single transaction amount against the per-transaction range.

        Regla (Fase 1): el valor de CADA transacción debe estar entre TRX_MONTO_MIN y
        TRX_MONTO_MAX ($35.000–$500.000 por defecto). Son parámetros de configuración,
        los mismos que aplica el filtro de movimientos.
        Fuera de ese rango -> se ofrece el formulario PQR para esa transacción (el
        conteo ">3" lo controla el agente). Se conserva ``accumulated_trxs`` como
        contexto informativo (no altera la decisión por-transacción).
        """

        from infrastructure.core.config import load_trx_flow_settings

        flow = load_trx_flow_settings()
        monto_min = float(flow.monto_min)
        monto_max = float(flow.monto_max)
        monto = float(current_trx_monto)
        previous = accumulated_trxs or []
        count_with_new = len(previous) + 1

        def _pesos(valor: float) -> str:
            return "$" + f"{int(round(valor)):,}".replace(",", ".")

        if monto < monto_min:
            return TrxResult(
                status="REDIRECT_PQR",
                id_message=206,
                step="2.4.0.1.4",
                detail=(
                    f"El valor de la transacción es menor a {_pesos(monto_min)}. "
                    "Para reportarla necesitas radicar el formulario PQR."
                ),
                data={
                    "current_trx_monto": monto,
                    "accumulated_count": count_with_new,
                    "in_range": False,
                    "rule": "monto_menor_minimo",
                    "monto_min": monto_min,
                    "monto_max": monto_max,
                },
            )

        if monto > monto_max:
            return TrxResult(
                status="REDIRECT_PQR",
                id_message=205,
                step="2.4.0.1.4",
                detail=(
                    f"El valor de la transacción es mayor a {_pesos(monto_max)}. "
                    "Para reportarla necesitas radicar el formulario PQR."
                ),
                data={
                    "current_trx_monto": monto,
                    "accumulated_count": count_with_new,
                    "in_range": False,
                    "rule": "monto_mayor_maximo",
                    "monto_min": monto_min,
                    "monto_max": monto_max,
                },
            )

        return TrxResult(
            status="APPROVED",
            id_message=209,
            step="2.4.0.1.4",
            detail="Transacción dentro del rango permitido ($35.000–$500.000).",
            data={
                "current_trx_monto": monto,
                "accumulated_count": count_with_new,
                "in_range": True,
                "rule": "in_range",
            },
        )
