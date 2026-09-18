"""Repository for customer identity lookup."""

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from pandas import DataFrame

from domain.customer.models import CustomerIdentity
from infrastructure.core.config import CsvSettings, load_csv_settings, load_env_constants
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import DataSourceError
from infrastructure.observability.trace_audit import schedule_trace_event

logger = get_logger(__name__)


def _e2e_debug_enabled() -> bool:
    """Whether E2E DEBUG tracing (full rows, no masking) is enabled.

    Reads from the merged .env constants (the configmap mounts .env as a file,
    so os.getenv alone would NOT see it), falling back to real env vars.
    """

    try:
        value = load_env_constants().get("E2E_DEBUG_TRACE")
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        value = os.getenv("E2E_DEBUG_TRACE")
    return str(value or "false").strip().casefold() in {"1", "true", "yes", "on"}


REQUIRED_IDENTITY_COLUMNS = ("customer_id", "personal_id", "personal_type")
EMPTY_IDENTITY_COLUMNS = (*REQUIRED_IDENTITY_COLUMNS, "customer_name")


class CustomerIdentityRepository:
    """Read customer identifiers from CSV mocks or PostgreSQL."""

    def __init__(self, settings: CsvSettings | None = None) -> None:
        self.settings = settings or load_csv_settings()

    @log_execution
    def read_customer_identity_df(self, customer_id: str | None = None) -> DataFrame:
        """Read customer identity rows from the configured source."""

        if self.settings.source in {"postgres", "postgresql", "db"}:
            logger.info(
                "Reading customer identity PostgreSQL table=%s host=%s database=%s customer_id=%s",
                self.settings.postgres_table,
                self.settings.DB_HOST,
                self.settings.DB_NAME,
                customer_id,
            )
            return self._read_postgres_df(customer_id=customer_id)

        csv_path = self.settings.customer_identity_csv_path
        logger.info(
            "Reading customer identity CSV path=%s environment=%s customer_id=%s",
            csv_path,
            self.settings.environment,
            customer_id,
        )
        customer_identity_df = self._read_df(csv_path)
        self._log_df_snapshot(
            customer_identity_df,
            source="csv",
            customer_id=customer_id,
        )
        if customer_id is None:
            return customer_identity_df

        return self._filter_df_by_customer_id(customer_identity_df, customer_id)

    @log_execution
    def find_by_customer_id(self, customer_id: str) -> CustomerIdentity | None:
        """Find the personal API identifiers related to a customer id."""

        logger.info("Finding customer identity customer_id=%s", customer_id)
        return self.find_by_customer_id_in_df(
            customer_id=customer_id,
            customer_identity_df=self.read_customer_identity_df(customer_id=customer_id),
        )

    @log_execution
    def find_by_customer_id_in_df(
        self,
        *,
        customer_id: str,
        customer_identity_df: DataFrame,
    ) -> CustomerIdentity | None:
        """Find the personal API identifiers in an already loaded CSV table."""

        self._log_df_snapshot(
            customer_identity_df,
            source="identity lookup input",
            customer_id=customer_id,
        )
        if customer_identity_df.empty:
            logger.warning(
                "Customer identity lookup returned no rows customer_id=%s",
                customer_id,
            )
            return None

        matching_rows = self._filter_df_by_customer_id(customer_identity_df, customer_id)

        if matching_rows.empty:
            logger.warning(
                "Customer identity was not found after filtering customer_id=%s available_columns=%s",
                customer_id,
                list(customer_identity_df.columns),
            )
            return None

        self._validate_required_columns(
            matching_rows,
            required_columns=REQUIRED_IDENTITY_COLUMNS,
            source="customer identity match",
        )
        row = matching_rows.iloc[0]
        return CustomerIdentity(
            customer_id=str(row["customer_id"]),
            personal_id=str(row["personal_id"]),
            personal_type=str(row["personal_type"]),
            customer_name=str(row.get("customer_name", "")),
            first_last_name=str(row.get("first_last_name", "")),
        )

    def _read_df(self, csv_path: Path) -> DataFrame:
        if not csv_path.exists():
            raise DataSourceError(
                "Customer identity CSV file was not found.",
                details={"path": str(csv_path)},
            )

        customer_identity_df = self._normalize_df(pd.read_csv(csv_path, dtype=str))
        self._validate_required_columns(
            customer_identity_df,
            required_columns=REQUIRED_IDENTITY_COLUMNS,
            source="customer identity CSV",
        )
        return customer_identity_df

    def _read_postgres_df(self, customer_id: str | None = None) -> DataFrame:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise DataSourceError(
                "PostgreSQL customer identity source requires psycopg.",
                details={"dependency": "psycopg[binary]"},
            ) from error

        query = f"SELECT * FROM {self._quoted_identifier(self.settings.postgres_table)}"
        params: tuple[str, str] | tuple[()] = ()
        if customer_id is not None:
            query = (
                f"{query} "
                "WHERE customer_id = %s "
                "OR NULLIF(LTRIM(customer_id, '0'), '') = NULLIF(LTRIM(%s, '0'), '')"
            )
            params = (customer_id.strip(), customer_id.strip())
        connection_settings: dict[str, Any] = {
            "host": self.settings.DB_HOST,
            "port": self.settings.postgres_port,
            "connect_timeout": self.settings.postgres_connect_timeout,
            "dbname": self.settings.DB_NAME,
            "user": self.settings.DB_USER,
            "password": self.settings.DB_PASS,
            "row_factory": dict_row,
        }

        logger.info(
            "Executing customer identity PostgreSQL query table=%s customer_id=%s sql=%s params_count=%s",
            self.settings.postgres_table,
            customer_id,
            query,
            len(params),
        )
        start = time.perf_counter()
        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    column_names = [
                        column.name
                        for column in (cursor.description or [])
                    ]
        except psycopg.Error as error:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "Customer identity PostgreSQL read failed table=%s customer_id=%s elapsed_ms=%s error=%s",
                self.settings.postgres_table,
                customer_id,
                elapsed_ms,
                error,
            )
            schedule_trace_event(
                event_type="postgres",
                operation="read_customer_identity",
                outcome="error",
                elapsed_ms=elapsed_ms,
                target=self.settings.postgres_table,
                customer_id=customer_id,
                request_summary={"params_count": len(params)},
                error_type=type(error).__name__,
                error_message=str(error),
                tags=["postgres", "identity"],
            )
            raise DataSourceError(
                "Customer identity PostgreSQL table could not be read.",
                details={
                    "host": self.settings.DB_HOST,
                    "database": self.settings.DB_NAME,
                    "table": self.settings.postgres_table,
                    "error": str(error),
                },
            ) from error

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Customer identity PostgreSQL read OK table=%s customer_id=%s elapsed_ms=%s rows=%s columns=%s",
            self.settings.postgres_table,
            customer_id,
            elapsed_ms,
            len(rows),
            len(column_names),
        )
        schedule_trace_event(
            event_type="postgres",
            operation="read_customer_identity",
            outcome="ok",
            elapsed_ms=elapsed_ms,
            target=self.settings.postgres_table,
            customer_id=customer_id,
            request_summary={"params_count": len(params)},
            response_summary={"rows": len(rows), "columns": column_names},
            tags=["postgres", "identity"],
        )
        if _e2e_debug_enabled():
            # E2E DEBUG: filas COMPLETAS tal cual vienen de Postgres (sin máscara).
            schedule_trace_event(
                event_type="debug",
                operation="read_customer_identity_full",
                outcome="debug",
                elapsed_ms=elapsed_ms,
                target=self.settings.postgres_table,
                customer_id=customer_id,
                request_summary={"query": query, "params": list(params)},
                response_summary={
                    "rows": len(rows),
                    "columns": column_names,
                    "rows_full": [dict(row) for row in rows],
                },
                tags=["debug", "e2e", "postgres"],
            )

        if not rows:
            logger.warning(
                "Customer identity PostgreSQL query returned no rows table=%s customer_id=%s columns=%s",
                self.settings.postgres_table,
                customer_id,
                column_names,
            )
            return pd.DataFrame(columns=column_names or EMPTY_IDENTITY_COLUMNS)

        customer_identity_df = self._normalize_df(pd.DataFrame(rows))
        self._log_df_snapshot(
            customer_identity_df,
            source="postgres",
            customer_id=customer_id,
        )
        self._validate_required_columns(
            customer_identity_df,
            required_columns=REQUIRED_IDENTITY_COLUMNS,
            source="customer identity PostgreSQL result",
        )
        return customer_identity_df

    def _filter_df_by_customer_id(
        self,
        customer_identity_df: DataFrame,
        customer_id: str,
    ) -> DataFrame:
        self._validate_required_columns(
            customer_identity_df,
            required_columns=("customer_id",),
            source="customer identity filter input",
        )
        customer_id_values = customer_identity_df["customer_id"].astype(str).str.strip()
        normalized_customer_id = self._normalize_customer_id(customer_id)

        matching_rows = customer_identity_df[
            (customer_id_values == customer_id.strip())
            | (customer_id_values.map(self._normalize_customer_id) == normalized_customer_id)
        ]
        logger.info(
            "Filtered customer identity rows customer_id=%s input_rows=%s matched_rows=%s",
            customer_id,
            len(customer_identity_df),
            len(matching_rows),
        )
        return matching_rows

    def _normalize_df(self, customer_identity_df: DataFrame) -> DataFrame:
        customer_identity_df.columns = [
            column.strip() for column in customer_identity_df.columns
        ]

        return customer_identity_df.fillna("").map(
            lambda value: value.strip() if isinstance(value, str) else value
        )

    def _quoted_identifier(self, identifier: str) -> str:
        parts = [part.strip() for part in identifier.split(".") if part.strip()]
        if not parts:
            raise DataSourceError(
                "PostgreSQL customer identity table was not configured.",
            )

        quoted_parts = []
        for part in parts:
            escaped_part = part.replace('"', '""')
            quoted_parts.append(f'"{escaped_part}"')

        return ".".join(quoted_parts)

    def _normalize_customer_id(self, customer_id: str) -> str:
        normalized_customer_id = customer_id.strip().lstrip("0")
        return normalized_customer_id or "0"

    def _log_df_snapshot(
        self,
        customer_identity_df: DataFrame,
        *,
        source: str,
        customer_id: str | None,
    ) -> None:
        logger.info(
            "Customer identity DataFrame source=%s customer_id=%s rows=%s columns=%s",
            source,
            customer_id,
            len(customer_identity_df),
            list(customer_identity_df.columns),
        )

    def _validate_required_columns(
        self,
        customer_identity_df: DataFrame,
        *,
        required_columns: tuple[str, ...],
        source: str,
    ) -> None:
        missing_columns = [
            column
            for column in required_columns
            if column not in customer_identity_df.columns
        ]
        if not missing_columns:
            return

        logger.error(
            "Customer identity data source returned an invalid schema source=%s missing_columns=%s available_columns=%s",
            source,
            missing_columns,
            list(customer_identity_df.columns),
        )
        raise DataSourceError(
            "Customer identity data source returned an invalid schema.",
            details={
                "source": source,
                "missing_columns": missing_columns,
                "available_columns": list(customer_identity_df.columns),
            },
        )

    def _read_postgres_projection_df(
        self,
        *,
        table_name: str,
        columns: tuple[str, ...],
    ) -> DataFrame:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise DataSourceError(
                "PostgreSQL source requires psycopg.",
                details={"dependency": "psycopg[binary]"},
            ) from error

        query = (
            f"SELECT {', '.join(columns)} "
            f"FROM {self._quoted_identifier(table_name)}"
        )
        connection_settings: dict[str, Any] = {
            "host": self.settings.DB_HOST,
            "port": self.settings.postgres_port,
            "connect_timeout": self.settings.postgres_connect_timeout,
            "dbname": self.settings.DB_NAME,
            "user": self.settings.DB_USER,
            "password": self.settings.DB_PASS,
            "row_factory": dict_row,
        }

        logger.info(
            "Executing PostgreSQL projection query table=%s sql=%s",
            table_name,
            query,
        )
        start = time.perf_counter()
        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    column_names = [column.name for column in (cursor.description or [])]
        except psycopg.Error as error:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "PostgreSQL projection read failed table=%s elapsed_ms=%s error=%s",
                table_name,
                elapsed_ms,
                error,
            )
            raise DataSourceError(
                "PostgreSQL table could not be read.",
                details={
                    "host": self.settings.DB_HOST,
                    "database": self.settings.DB_NAME,
                    "table": table_name,
                    "error": str(error),
                },
            ) from error

        if not rows:
            logger.warning(
                "PostgreSQL projection query returned no rows table=%s columns=%s",
                table_name,
                column_names,
            )
            return pd.DataFrame(columns=column_names or list(columns))

        return self._normalize_df(pd.DataFrame(rows))

    @log_execution
    def read_embargo_enriched_data(self) -> DataFrame:
        """
        Read the pre-joined embargo data from BGDT_SALIDA_JOIN.

        This table is built and refreshed by the co_pqrs_back_load_seizures_data
        loader (BGDTDEM x BGDTEMB inner join on DEM_NUMEMBAR = EMB_NUMEMBAR),
        so this repository only needs to project the final columns:
        contract_id, emb_juzgado, emb_imp_total, emb_nro_ofic, emb_fecha_ofic,
        dem_estado, dem_timest_umo.
        """
        if self.settings.source not in {"postgres", "postgresql", "db"}:
            logger.warning("Embargo enriched data only available in PostgreSQL mode")
            return pd.DataFrame()

        try:
            resultado = self._read_postgres_projection_df(
                table_name=self.settings.postgres_table_join,
                columns=(
                    "contract_id",
                    "emb_juzgado",
                    "emb_imp_total",
                    "emb_nro_ofic",
                    "emb_fecha_ofic",
                    "dem_estado",
                    "dem_timest_umo",
                ),
            )
            logger.info("Embargo enriched data: %d rows read from join table", len(resultado))
            return resultado

        except Exception:
            logger.exception("Failed to read embargo enriched data")
            return pd.DataFrame()

    @log_execution
    def read_embargo_join_by_contract_id(self, *, contract_id: str) -> list[dict[str, str]]:
        """
        Read embargo fields from BGDT_SALIDA_JOIN for one contract_id.

        Returns a list of dicts with keys:
        emb_juzgado, emb_nro_ofic, emb_fecha_ofic, emb_imp_total, dem_estado, dem_timest_umo
        Empty list when not found or non-postgres source.
        """
        if self.settings.source not in {"postgres", "postgresql", "db"}:
            logger.warning("Embargo lookup by contract_id only available in PostgreSQL mode")
            return []

        normalized_contract_id = str(contract_id or "").strip()
        if not normalized_contract_id:
            return []

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise DataSourceError(
                "PostgreSQL source requires psycopg.",
                details={"dependency": "psycopg[binary]"},
            ) from error

        query = (
            "SELECT emb_juzgado, emb_nro_ofic, emb_fecha_ofic, emb_imp_total, dem_estado, dem_timest_umo "
            f"FROM {self._quoted_identifier(self.settings.postgres_table_join)} "
            "WHERE contract_id::text = %s "
            "ORDER BY dem_timest_umo DESC NULLS LAST "
        )

        connection_settings: dict[str, Any] = {
            "host": self.settings.DB_HOST,
            "port": self.settings.postgres_port,
            "connect_timeout": self.settings.postgres_connect_timeout,
            "dbname": self.settings.DB_NAME,
            "user": self.settings.DB_USER,
            "password": self.settings.DB_PASS,
            "row_factory": dict_row,
        }

        logger.info(
            "Executing embargo lookup table=%s contract_id=%s",
            self.settings.postgres_table_join,
            normalized_contract_id,
        )

        start = time.perf_counter()
        try:
            with psycopg.connect(**connection_settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, (normalized_contract_id,))
                    rows = cursor.fetchall()
        except psycopg.Error as error:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "Embargo lookup failed table=%s contract_id=%s elapsed_ms=%s error=%s",
                self.settings.postgres_table_join,
                normalized_contract_id,
                elapsed_ms,
                error,
            )
            raise DataSourceError(
                "PostgreSQL embargo lookup could not be read.",
                details={
                    "host": self.settings.DB_HOST,
                    "database": self.settings.DB_NAME,
                    "table": self.settings.postgres_table_join,
                    "contract_id": normalized_contract_id,
                    "error": str(error),
                },
            ) from error

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        if not rows:
            logger.info(
                "Embargo lookup returned no row table=%s contract_id=%s elapsed_ms=%s",
                self.settings.postgres_table_join,
                normalized_contract_id,
                elapsed_ms,
            )
            return []

        # Normalize nulls and strip whitespace
        def _as_text(value: Any) -> str:
            if value is None:
                return ""
            return str(value).strip()

        results = []
        for row in rows:
            results.append({
                "emb_juzgado": _as_text(row.get("emb_juzgado")),
                "emb_nro_ofic": _as_text(row.get("emb_nro_ofic")),
                "emb_fecha_ofic": _as_text(row.get("emb_fecha_ofic")),
                "emb_imp_total": _as_text(row.get("emb_imp_total")),
                "dem_estado": _as_text(row.get("dem_estado")),
                "dem_timest_umo": _as_text(row.get("dem_timest_umo")),
            })

        logger.info(
            "Embargo lookup OK table=%s contract_id=%s elapsed_ms=%s",
            self.settings.postgres_table_join,
            normalized_contract_id,
            elapsed_ms,
        )
        return results
