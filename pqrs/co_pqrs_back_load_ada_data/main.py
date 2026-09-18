from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq
from dotenv import load_dotenv


LOGGER = logging.getLogger("load_ada_data")

# Columns that must always keep a btree index for fast point-lookups.
INDEX_COLUMNS: tuple[str, ...] = ("customer_id", "personal_id")

# Expression that mirrors the OR/LTRIM predicate used by the identity lookup
# (customer_identity_repository._read_postgres_df). Indexing this expression lets
# that query use a Bitmap Index Scan instead of a full sequential scan.
CUSTOMER_ID_NORM_EXPR = "NULLIF(LTRIM(customer_id, '0'), '')"

# Column definitions for the target table.
TABLE_COLUMNS_DDL = """
    key_id TEXT,
    contract_id TEXT,
    commercial_product_id TEXT,
    commercial_subproduct_id TEXT,
    contract_register_date DATE,
    account_status_type TEXT,
    account_status_type_desc TEXT,
    blocking_type TEXT,
    blocking_type_desc TEXT,
    account_freeze_type TEXT,
    contract_status_date DATE,
    contract_status_type TEXT,
    contract_status_type_desc TEXT,
    card_bin_number TEXT,
    card_bin_subtype_type TEXT,
    contract_end_date DATE,
    card_type TEXT,
    card_type_desc TEXT,
    account_id TEXT,
    card_brand TEXT,
    participant_type TEXT,
    participation_order_number TEXT,
    card_status_type TEXT,
    card_status_date DATE,
    last_four_pan_id TEXT,
    last_ten_pan_id TEXT,
    card_block_type TEXT,
    card_end_reason_type TEXT,
    card_active_flag BOOLEAN,
    origin_flag TEXT,
    customer_id TEXT,
    personal_id TEXT,
    personal_type TEXT,
    personal_verif_digit_type TEXT,
    customer_name TEXT,
    first_last_name TEXT,
    second_last_name TEXT,
    customer_mail TEXT,
    customer_address TEXT,
    personal_type_desc TEXT,
    commercial_product_desc TEXT,
    commercial_subproduct_desc TEXT,
    off_loaded_porfolio_date DATE,
    portfolio_buyer_company_id TEXT,
    buyer_name TEXT,
    off_loaded_portfolio_flag BOOLEAN,
    written_off_date DATE,
    written_off_end_date DATE,
    written_off_flag BOOLEAN,
    default_days_number TEXT,
    default_date DATE,
    default_end_date DATE,
    default_flag BOOLEAN,
    default_status_pay BOOLEAN,
    restructured_flag BOOLEAN,
    date_consult_risk_ctral DATE,
    flag_consult_risk_ctral BOOLEAN,
    adelanto_nomina_flag BOOLEAN,
    card_flag BOOLEAN,
    seizure_flag BOOLEAN,
    product_desc TEXT,
    audit_date TIMESTAMP
"""

# Accepted memory setting format, e.g. "1GB", "512MB", "256 MB".
_MEM_RE = re.compile(r"^\d+\s*(kB|MB|GB|TB)?$", re.IGNORECASE)


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    process_path: Path
    folder_prefix: str
    target_table: str
    parquet_batch_size: int
    unlogged: bool
    work_mem: str
    maintenance_work_mem: str
    max_parallel_maintenance_workers: int


@dataclass(frozen=True)
class JobSummary:
    processed_at: str
    folder_expected: str
    folder_found: bool
    parts_found: int
    parts_loaded: int
    total_rows_loaded: int
    status: str


def configure_logging() -> None:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def validate_mem(name: str, value: str) -> str:
    value = value.strip()
    if not _MEM_RE.match(value):
        raise ValueError(f"{name} must be a Postgres memory value (e.g. 512MB, 1GB), got: {value!r}")
    return value


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        db_host=required_env("DB_HOST"),
        db_port=parse_int_env("DB_PORT", default=5432),
        db_name=required_env("DB_NAME"),
        db_user=required_env("DB_USER"),
        db_password=required_env("DB_PASS"),
        process_path=Path(os.getenv("ADA_DATA_PATH") or os.getenv("RUTA_PROCESO", "/mnt/ada_data")),
        folder_prefix=os.getenv("ADA_FOLDER_PREFIX", "pqrs_ada_data_"),
        target_table=os.getenv("TARGET_TABLE", "ada_info_detail"),
        parquet_batch_size=parse_int_env("PARQUET_BATCH_SIZE", default=100_000),
        unlogged=parse_bool_env("DB_UNLOGGED", default=True),
        work_mem=validate_mem("WORK_MEM", os.getenv("WORK_MEM", "256MB")),
        maintenance_work_mem=validate_mem(
            "MAINTENANCE_WORK_MEM", os.getenv("MAINTENANCE_WORK_MEM", "1GB")
        ),
        max_parallel_maintenance_workers=max(
            0, parse_int_env("MAX_PARALLEL_MAINTENANCE_WORKERS", default=4)
        ),
    )


def expected_folder_name(settings: Settings, now: datetime | None = None) -> str:
    reference = now or datetime.now()
    reference = reference - timedelta(days=1)
    return f"{settings.folder_prefix}{reference.strftime('%Y%m%d')}"


# --------------------------------------------------------------------------- #
# Pure SQL builders (unit-testable, no DB connection required)
# --------------------------------------------------------------------------- #
def quote_ident(name: str) -> str:
    """Safely double-quote a SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def index_name(table: str, column: str) -> str:
    return f"idx_{table}_{column}"


def build_create_table_sql(table: str, *, unlogged: bool, if_not_exists: bool) -> str:
    unlogged_kw = "UNLOGGED " if unlogged else ""
    exists_kw = "IF NOT EXISTS " if if_not_exists else ""
    return f"CREATE {unlogged_kw}TABLE {exists_kw}{quote_ident(table)} (\n{TABLE_COLUMNS_DDL}\n)"


def build_copy_sql(table: str, columns: tuple[str, ...]) -> str:
    cols = ", ".join(quote_ident(column) for column in columns)
    return (
        f"COPY {quote_ident(table)} ({cols}) FROM STDIN "
        "WITH (FORMAT csv, DELIMITER ',', QUOTE '\"', ESCAPE '\"', NULL '')"
    )


def build_create_index_sql(idx: str, table: str, column: str) -> str:
    return f"CREATE INDEX {quote_ident(idx)} ON {quote_ident(table)} ({quote_ident(column)})"


def build_create_expr_index_sql(idx: str, table: str, expression: str) -> str:
    """CREATE INDEX on an expression (functional index)."""
    return f"CREATE INDEX {quote_ident(idx)} ON {quote_ident(table)} (({expression}))"


def build_session_tuning_statements(settings: Settings) -> list[str]:
    return [
        "SET synchronous_commit = off",
        f"SET work_mem = '{settings.work_mem}'",
        f"SET maintenance_work_mem = '{settings.maintenance_work_mem}'",
        f"SET max_parallel_maintenance_workers = {int(settings.max_parallel_maintenance_workers)}",
        "SET statement_timeout = 0",
    ]


# --------------------------------------------------------------------------- #
# Parquet helpers
# --------------------------------------------------------------------------- #
def list_parquet_parts(folder_path: Path) -> list[Path]:
    return sorted(path for path in folder_path.rglob("*.parquet") if path.is_file())


def validate_and_get_columns(parts: list[Path]) -> tuple[str, ...]:
    """Read schema metadata from every part and ensure they all match."""
    expected: tuple[str, ...] | None = None
    for part in parts:
        columns = tuple(pq.ParquetFile(str(part)).schema_arrow.names)
        if not columns:
            continue
        if expected is None:
            expected = columns
        elif columns != expected:
            raise ValueError(
                "Parquet schema mismatch between parts: "
                f"expected={expected} actual={columns} file={part.name}"
            )
    if expected is None:
        raise ValueError("No parquet part exposed any column")
    return expected


def _connect(settings: Settings) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )


def _copy_part(cursor, copy_sql: str, part_path: Path, batch_size: int) -> int:
    """Stream a single parquet part to Postgres via COPY. Returns rows."""
    parquet_file = pq.ParquetFile(str(part_path))
    rows = 0
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        if batch.num_rows == 0:
            continue
        cleaned_arrays = []
        for col_name in batch.schema.names:
            col = batch.column(col_name)
            if pa.types.is_string(col.type) or pa.types.is_large_string(col.type):
                col = pc.replace_substring(col, "\x00", "")
            cleaned_arrays.append(col)
        cleaned_batch = pa.RecordBatch.from_arrays(cleaned_arrays, schema=batch.schema)

        sink = pa.BufferOutputStream()
        pa_csv.write_csv(
            cleaned_batch,
            sink,
            write_options=pa_csv.WriteOptions(include_header=False),
        )
        buffer = io.BytesIO(sink.getvalue().to_pybytes())
        cursor.copy_expert(copy_sql, buffer)
        rows += batch.num_rows
    return rows


def run_job() -> JobSummary:
    settings = load_settings()
    folder_name = expected_folder_name(settings)
    folder_path = settings.process_path / folder_name

    LOGGER.info(
        "Starting ADA load job process_path=%s folder_expected=%s table=%s unlogged=%s batch=%s",
        settings.process_path,
        folder_name,
        settings.target_table,
        settings.unlogged,
        settings.parquet_batch_size,
    )

    if not settings.process_path.exists():
        raise FileNotFoundError(f"Process path is not accessible: {settings.process_path}")

    if not folder_path.exists() or not folder_path.is_dir():
        LOGGER.warning("Expected ADA folder not found: %s", folder_path)
        return JobSummary(
            processed_at=datetime.now().isoformat(),
            folder_expected=folder_name,
            folder_found=False,
            parts_found=0,
            parts_loaded=0,
            total_rows_loaded=0,
            status="warning:folder_not_found",
        )

    parts = list_parquet_parts(folder_path)
    if not parts:
        LOGGER.warning("No parquet parts found in folder: %s", folder_path)
        return JobSummary(
            processed_at=datetime.now().isoformat(),
            folder_expected=folder_name,
            folder_found=True,
            parts_found=0,
            parts_loaded=0,
            total_rows_loaded=0,
            status="warning:no_parquet_parts",
        )

    columns = validate_and_get_columns(parts)
    target = settings.target_table
    total_rows = 0

    connection = _connect(settings)
    try:
        connection.autocommit = False
        # Session tuning persists across the transactions on this connection.
        with connection.cursor() as cursor:
            for statement in build_session_tuning_statements(settings):
                cursor.execute(statement)

        # Phase 1: rebuild an empty table. DROP+CREATE frees the OLD data files
        # immediately (1x disk footprint) and guarantees the table is UNLOGGED
        # (no WAL -> faster + far less disk). Committed before loading.
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {quote_ident(target)}")
            cursor.execute(
                build_create_table_sql(target, unlogged=settings.unlogged, if_not_exists=False)
            )
        connection.commit()
        LOGGER.info("Table %s recreated (unlogged=%s); old data freed", target, settings.unlogged)

        # Phase 2: sequential COPY of every part (low, bounded memory -> stable).
        copy_sql = build_copy_sql(target, columns)
        with connection.cursor() as cursor:
            for position, part_path in enumerate(parts, start=1):
                part_rows = _copy_part(cursor, copy_sql, part_path, settings.parquet_batch_size)
                total_rows += part_rows
                LOGGER.info(
                    "Parquet part loaded (%s/%s) file=%s rows=%s cumulative=%s table=%s",
                    position,
                    len(parts),
                    part_path.name,
                    part_rows,
                    total_rows,
                    target,
                )
        connection.commit()
        LOGGER.info("COPY finished total_rows=%s; building indexes...", total_rows)

        # Phase 3: indexes (Postgres-side parallel build) + ANALYZE.
        with connection.cursor() as cursor:
            for column in INDEX_COLUMNS:
                LOGGER.info("Creating index on %s.%s ...", target, column)
                cursor.execute(
                    build_create_index_sql(index_name(target, column), target, column)
                )
            # Expression index so the identity lookup (customer_id = %s OR
            # NULLIF(LTRIM(customer_id,'0'),'') = ...) uses a Bitmap Index Scan
            # instead of a full seq scan. Must match the predicate exactly.
            norm_idx = f"idx_{target}_customer_id_norm"
            LOGGER.info("Creating expression index %s (normalized customer_id) ...", norm_idx)
            cursor.execute(
                build_create_expr_index_sql(norm_idx, target, CUSTOMER_ID_NORM_EXPR)
            )
            LOGGER.info("Running ANALYZE on %s ...", target)
            cursor.execute(f"ANALYZE {quote_ident(target)}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    summary = JobSummary(
        processed_at=datetime.now().isoformat(),
        folder_expected=folder_name,
        folder_found=True,
        parts_found=len(parts),
        parts_loaded=len(parts),
        total_rows_loaded=total_rows,
        status="loaded",
    )
    LOGGER.info(
        "ADA load finished processed_at=%s folder=%s parts=%s rows=%s status=%s",
        summary.processed_at,
        summary.folder_expected,
        summary.parts_found,
        summary.total_rows_loaded,
        summary.status,
    )
    return summary


def _report_job_failure(error: BaseException) -> None:
    import json
    import traceback
    import urllib.request

    base_url = (os.getenv("ERROR_HANDLER_SERVICE_URL") or "").strip().rstrip("/")
    if not base_url:
        return

    component = "co_pqrs_back_load_ada_data"
    payload = {
        "conversation_id": None,
        "component": component,
        "error_message": str(error) or repr(error),
        "error_type": type(error).__name__,
        "error_source": component,
        "tags": ["loader", "auto-audit", "exception"],
        "agent_context": {"source": "run_job"},
        "extra_context": {
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        },
    }
    request = urllib.request.Request(
        f"{base_url}/v0/error-reports",
        data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0):
            pass
    except Exception:
        LOGGER.exception("Error report notification failed component=%s", component)


def main() -> None:
    configure_logging()
    try:
        run_job()
    except Exception as error:
        # Always print the real cause to stdout/pod logs (before best-effort audit).
        LOGGER.exception("ADA load job FAILED: %s", error)
        _report_job_failure(error)
        raise


if __name__ == "__main__":
    main()
