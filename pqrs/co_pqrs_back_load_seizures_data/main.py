from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


LOGGER = logging.getLogger("load_seizures_data")


class NullByteRemovingReader:
    def __init__(self, wrapped: TextIO) -> None:
        self._wrapped = wrapped
        self.removed_null_bytes = 0

    def _clean(self, chunk: str) -> str:
        if not chunk:
            return chunk
        null_count = chunk.count("\x00")
        if null_count:
            self.removed_null_bytes += null_count
            return chunk.replace("\x00", "")
        return chunk

    def read(self, size: int = -1) -> str:
        return self._clean(self._wrapped.read(size))

    def readline(self, size: int = -1) -> str:
        return self._clean(self._wrapped.readline(size))

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    process_path: Path
    delimiter: str
    file_encoding: str
    file_encoding_fallbacks: tuple[str, ...]
    quote_char: str
    escape_char: str


@dataclass(frozen=True)
class FileProcessResult:
    file_name: str
    table_name: str
    loaded: bool
    rows_loaded: int
    detail: str


@dataclass(frozen=True)
class JobSummary:
    processed_at: str
    files_expected: int
    files_found: int
    files_loaded: int
    files_skipped: int


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


def load_settings() -> Settings:
    load_dotenv()
    fallback_raw = os.getenv("FILE_ENCODING_FALLBACKS", "latin-1,utf-8")
    fallback_encodings = tuple(
        part.strip() for part in fallback_raw.split(",") if part.strip()
    )
    return Settings(
        db_host=required_env("DB_HOST"),
        db_port=parse_int_env("DB_PORT", default=5432),
        db_name=required_env("DB_NAME"),
        db_user=required_env("DB_USER"),
        db_password=required_env("DB_PASS"),
        process_path=Path(os.getenv("RUTA_PROCESO", "/mnt/embargos")),
        delimiter=os.getenv("CSV_DELIMITER", ";"),
        file_encoding=os.getenv("FILE_ENCODING", "cp1252"),
        file_encoding_fallbacks=fallback_encodings,
        quote_char=os.getenv("CSV_QUOTE_CHAR", "\x01"),
        escape_char=os.getenv("CSV_ESCAPE_CHAR", "\x01"),
    )


def encoding_candidates(settings: Settings) -> tuple[str, ...]:
    candidates: list[str] = []
    seen: set[str] = set()
    for encoding in (settings.file_encoding, *settings.file_encoding_fallbacks):
        key = encoding.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(encoding)
    return tuple(candidates)


def build_today_mapping(now: datetime | None = None) -> dict[str, str]:
    reference = now or datetime.now()
    reference = reference - timedelta(days=1)
    date_token = reference.strftime("%y%m%d")
    return {
        f"DESCARGA_EMB.F{date_token}.TXT": "bgdtemb",
        f"DESCARGA_DEM.F{date_token}.TXT": "bgdtdem",
    }


def create_tables_if_not_exist(
    connection: psycopg2.extensions.connection,
) -> None:
    """Create the BGDTEMB and BGDTDEM tables if they don't exist."""
    create_bgdtemb_sql = """
    CREATE TABLE IF NOT EXISTS BGDTEMB (
        EMB_NUMEMBAR VARCHAR(20),
        EMB_TIP_MOV VARCHAR(5),
        EMB_NUMCLIEN VARCHAR(20),
        EMB_CODIDENT VARCHAR(5),
        EMB_CLAIDENT VARCHAR(30),
        EMB_DIGIDENT VARCHAR(5),
        EMB_TIP_SUBJ VARCHAR(5),
        EMB_TIP_REG VARCHAR(5),
        EMB_TIP_JUR VARCHAR(5),
        EMB_EXPEDIENTE VARCHAR(60),
        EMB_CONCEP_EMB VARCHAR(150),
        EMB_NRO_OFIC VARCHAR(20),
        EMB_FECHA_OFIC DATE,
        EMB_JUZGADO VARCHAR(150),
        EMB_IND_ID_DEM VARCHAR(5),
        EMB_CODIDENT_DEM VARCHAR(20),
        EMB_CLAIDENTI_DEM VARCHAR(30),
        EMB_DIGIDENT_DEM VARCHAR(5),
        EMB_CONS_ID_DEM VARCHAR(20),
        EMB_CONS_BBVA VARCHAR(20),
        EMB_USUARIO VARCHAR(20),
        EMB_COD_FIRMA VARCHAR(20),
        EMB_CONS_ENTE VARCHAR(20),
        EMB_CENTRO_REG VARCHAR(10),
        EMB_FECHA_CREA DATE,
        EMB_ESTADO VARCHAR(5),
        EMB_PRIORIDAD VARCHAR(20),
        EMB_FECHA_PAGO DATE,
        EMB_IND_MONTOINDEF VARCHAR(5),
        EMB_IND_INEMB VARCHAR(5),
        EMB_IMP_TOTAL NUMERIC(18,2),
        EMB_IMP_COB_DIA NUMERIC(18,2),
        EMB_IMP_RETEN NUMERIC(18,2),
        EMB_IMP_COBRO NUMERIC(18,2),
        EMB_TIP_PAGO VARCHAR(5),
        EMB_IMP_PAGAR NUMERIC(18,2),
        EMB_IMP_SALDO_EMB NUMERIC(18,2),
        EMB_FECHA_ALT_OFIC DATE,
        EMB_USER_UMO VARCHAR(20),
        EMB_TIMEST_UMO VARCHAR(50),
        EMB_BANCO_GIRO VARCHAR(20),
        EMB_CUENTA_GIRO VARCHAR(50)
    )
    """

    create_bgdtdem_sql = """
    CREATE TABLE IF NOT EXISTS BGDTDEM (
        DEM_NUMEMBAR VARCHAR(20),
        DEM_CENTRO_ALTA VARCHAR(10),
        DEM_CUENTA VARCHAR(30),
        DEM_SALDO_INEMB NUMERIC(18,2),
        DEM_IMP_RETENIDO NUMERIC(18,2),
        DEM_IMP_COBRADO NUMERIC(18,2),
        DEM_IMP_COBRO_DIA NUMERIC(18,2),
        DEM_LINOP_REM NUMERIC(18,2),
        DEM_LINOP_CI NUMERIC(18,2),
        DEM_EXCE_VENTAN NUMERIC(18,2),
        DEM_LIMITE NUMERIC(18,2),
        DEM_TIP_BLOQUEO VARCHAR(5),
        DEM_ESTADO VARCHAR(5),
        DEM_IND_DESTINTE VARCHAR(5),
        DEM_IND_INSTRUCC VARCHAR(5),
        DEM_IND_CON_COBRO VARCHAR(5),
        DEM_USER_UMO VARCHAR(20),
        DEM_TIMEST_UMO VARCHAR(50)
    )
    """

    with connection.cursor() as cursor:
        cursor.execute(create_bgdtemb_sql)
        cursor.execute(create_bgdtdem_sql)
        connection.commit()
        LOGGER.info("Tables BGDTEMB and BGDTDEM created or already exist")


def create_indexes_if_not_exist(
    connection: psycopg2.extensions.connection,
) -> None:
    """Create performance indexes for high-volume BGDTEMB and BGDTDEM tables."""
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_bgdtemb_numembar ON BGDTEMB (EMB_NUMEMBAR)",
        "CREATE INDEX IF NOT EXISTS idx_bgdtdem_numembar_centro_cuenta ON BGDTDEM (DEM_NUMEMBAR, DEM_CENTRO_ALTA, DEM_CUENTA)",
    )

    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()

    LOGGER.info("Indexes for BGDTEMB and BGDTDEM configured")


def refresh_join_output_table(
    connection: psycopg2.extensions.connection,
) -> int:
    """Create and refresh a new output table from BGDTDEM x BGDTEMB."""
    create_output_sql = """
    CREATE TABLE IF NOT EXISTS BGDT_SALIDA_JOIN (
        CONTRACT_ID VARCHAR(50),
        EMB_JUZGADO VARCHAR(150),
        EMB_IMP_TOTAL NUMERIC(18,2),
        EMB_NRO_OFIC VARCHAR(20),
        EMB_FECHA_OFIC DATE,
        DEM_ESTADO VARCHAR(5),
        DEM_TIMEST_UMO VARCHAR(50)
    )
    """

    with connection.cursor() as cursor:
        cursor.execute(create_output_sql)
        cursor.execute("TRUNCATE TABLE BGDT_SALIDA_JOIN")
        cursor.execute(
            """
            INSERT INTO BGDT_SALIDA_JOIN (
                CONTRACT_ID,
                EMB_JUZGADO,
                EMB_IMP_TOTAL,
                EMB_NRO_OFIC,
                EMB_FECHA_OFIC,
                DEM_ESTADO,
                DEM_TIMEST_UMO
            )
            SELECT
                '0013' || TRIM(d.DEM_CENTRO_ALTA) || '00' || TRIM(d.DEM_CUENTA),
                e.EMB_JUZGADO,
                (e.EMB_IMP_TOTAL / 100) as EMB_IMP_TOTAL,
                e.EMB_NRO_OFIC,
                e.EMB_FECHA_OFIC,
                d.DEM_ESTADO,
                d.DEM_TIMEST_UMO
            FROM BGDTDEM d
            INNER JOIN BGDTEMB e
                ON e.EMB_NUMEMBAR = d.DEM_NUMEMBAR
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bgdt_salida_contract_id ON BGDT_SALIDA_JOIN (CONTRACT_ID)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bgdt_salida_dem_estado ON BGDT_SALIDA_JOIN (DEM_ESTADO)"
        )
        cursor.execute("SELECT COUNT(*) FROM BGDT_SALIDA_JOIN")
        output_rows = int(cursor.fetchone()[0])
        connection.commit()

    LOGGER.info("Join output refreshed table=BGDT_SALIDA_JOIN rows=%s", output_rows)
    return output_rows


def create_tables_if_not_exist(
    connection: psycopg2.extensions.connection,
) -> None:
    """Create the BGDTEMB and BGDTDEM tables if they don't exist."""
    create_bgdtemb_sql = """
    CREATE TABLE IF NOT EXISTS BGDTEMB (
        EMB_NUMEMBAR VARCHAR(20),
        EMB_TIP_MOV VARCHAR(5),
        EMB_NUMCLIEN VARCHAR(20),
        EMB_CODIDENT VARCHAR(5),
        EMB_CLAIDENT VARCHAR(30),
        EMB_DIGIDENT VARCHAR(5),
        EMB_TIP_SUBJ VARCHAR(5),
        EMB_TIP_REG VARCHAR(5),
        EMB_TIP_JUR VARCHAR(5),
        EMB_EXPEDIENTE VARCHAR(60),
        EMB_CONCEP_EMB VARCHAR(150),
        EMB_NRO_OFIC VARCHAR(20),
        EMB_FECHA_OFIC DATE,
        EMB_JUZGADO VARCHAR(150),
        EMB_IND_ID_DEM VARCHAR(5),
        EMB_CODIDENT_DEM VARCHAR(20),
        EMB_CLAIDENTI_DEM VARCHAR(30),
        EMB_DIGIDENT_DEM VARCHAR(5),
        EMB_CONS_ID_DEM VARCHAR(20),
        EMB_CONS_BBVA VARCHAR(20),
        EMB_USUARIO VARCHAR(20),
        EMB_COD_FIRMA VARCHAR(20),
        EMB_CONS_ENTE VARCHAR(20),
        EMB_CENTRO_REG VARCHAR(10),
        EMB_FECHA_CREA DATE,
        EMB_ESTADO VARCHAR(5),
        EMB_PRIORIDAD VARCHAR(20),
        EMB_FECHA_PAGO DATE,
        EMB_IND_MONTOINDEF VARCHAR(5),
        EMB_IND_INEMB VARCHAR(5),
        EMB_IMP_TOTAL NUMERIC(18,2),
        EMB_IMP_COB_DIA NUMERIC(18,2),
        EMB_IMP_RETEN NUMERIC(18,2),
        EMB_IMP_COBRO NUMERIC(18,2),
        EMB_TIP_PAGO VARCHAR(5),
        EMB_IMP_PAGAR NUMERIC(18,2),
        EMB_IMP_SALDO_EMB NUMERIC(18,2),
        EMB_FECHA_ALT_OFIC DATE,
        EMB_USER_UMO VARCHAR(20),
        EMB_TIMEST_UMO VARCHAR(50),
        EMB_BANCO_GIRO VARCHAR(20),
        EMB_CUENTA_GIRO VARCHAR(50)
    )
    """

    create_bgdtdem_sql = """
    CREATE TABLE IF NOT EXISTS BGDTDEM (
        DEM_NUMEMBAR VARCHAR(20),
        DEM_CENTRO_ALTA VARCHAR(10),
        DEM_CUENTA VARCHAR(30),
        DEM_SALDO_INEMB NUMERIC(18,2),
        DEM_IMP_RETENIDO NUMERIC(18,2),
        DEM_IMP_COBRADO NUMERIC(18,2),
        DEM_IMP_COBRO_DIA NUMERIC(18,2),
        DEM_LINOP_REM NUMERIC(18,2),
        DEM_LINOP_CI NUMERIC(18,2),
        DEM_EXCE_VENTAN NUMERIC(18,2),
        DEM_LIMITE NUMERIC(18,2),
        DEM_TIP_BLOQUEO VARCHAR(5),
        DEM_ESTADO VARCHAR(5),
        DEM_IND_DESTINTE VARCHAR(5),
        DEM_IND_INSTRUCC VARCHAR(5),
        DEM_IND_CON_COBRO VARCHAR(5),
        DEM_USER_UMO VARCHAR(20),
        DEM_TIMEST_UMO VARCHAR(50)
    )
    """

    with connection.cursor() as cursor:
        cursor.execute(create_bgdtemb_sql)
        cursor.execute(create_bgdtdem_sql)
        connection.commit()
        LOGGER.info("Tables BGDTEMB and BGDTDEM created or already exist")


def process_file(
    connection: psycopg2.extensions.connection,
    settings: Settings,
    source_path: Path,
    table_name: str,
) -> FileProcessResult:
    if not source_path.exists():
        return FileProcessResult(
            file_name=source_path.name,
            table_name=table_name,
            loaded=False,
            rows_loaded=0,
            detail="file_not_found",
        )

    with connection.cursor() as cursor:
        try:
            cursor.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(sql.Identifier(table_name))
            )

            copy_query = sql.SQL(
                "COPY {} FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER {}, QUOTE {}, ESCAPE {})"
            )
            query = copy_query.format(
                sql.Identifier(table_name),
                sql.Literal(settings.delimiter),
                sql.Literal(settings.quote_char),
                sql.Literal(settings.escape_char),
            )

            last_error: Exception | None = None
            loaded_with_encoding = False
            for index, encoding in enumerate(encoding_candidates(settings), start=1):
                try:
                    with source_path.open("r", encoding=encoding, newline="") as source_file:
                        cleaned_reader = NullByteRemovingReader(source_file)
                        cursor.copy_expert(query.as_string(connection), cleaned_reader)

                    if cleaned_reader.removed_null_bytes:
                        LOGGER.warning(
                            "Removed null bytes before COPY file=%s table=%s removed=%s",
                            source_path.name,
                            table_name,
                            cleaned_reader.removed_null_bytes,
                        )

                    if index > 1:
                        LOGGER.warning(
                            "Loaded file with fallback encoding file=%s table=%s encoding=%s",
                            source_path.name,
                            table_name,
                            encoding,
                        )
                    loaded_with_encoding = True
                    break
                except Exception as exc:
                    if "UnicodeDecodeError" not in str(exc) and not isinstance(exc, UnicodeDecodeError):
                        raise
                    last_error = exc
                    connection.rollback()
                    with connection.cursor() as retry_cursor:
                        retry_cursor.execute(
                            sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
                                sql.Identifier(table_name)
                            )
                        )
                    LOGGER.warning(
                        "Decode error during COPY file=%s table=%s encoding=%s detail=%s",
                        source_path.name,
                        table_name,
                        encoding,
                        exc,
                    )
                    continue

            if not loaded_with_encoding and last_error is not None:
                raise last_error

            cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
            row_count = int(cursor.fetchone()[0])

            connection.commit()
            return FileProcessResult(
                file_name=source_path.name,
                table_name=table_name,
                loaded=True,
                rows_loaded=row_count,
                detail="loaded",
            )
        except Exception as exc:
            connection.rollback()
            return FileProcessResult(
                file_name=source_path.name,
                table_name=table_name,
                loaded=False,
                rows_loaded=0,
                detail=f"failed:{exc}",
            )


def run_job() -> JobSummary:
    settings = load_settings()
    files_by_table = build_today_mapping()
    process_date = datetime.now().isoformat()

    LOGGER.info("Starting load job process_path=%s files_expected=%s", settings.process_path, len(files_by_table))

    if not settings.process_path.exists():
        raise FileNotFoundError(f"Process path is not accessible: {settings.process_path}")

    found = 0
    loaded = 0
    skipped = 0

    with psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    ) as connection:
        # Create tables if they don't exist
        create_tables_if_not_exist(connection)
        create_indexes_if_not_exist(connection)

        for file_name, table_name in files_by_table.items():
            source_path = settings.process_path / file_name
            result = process_file(connection, settings, source_path, table_name)

            if source_path.exists():
                found += 1

            if result.loaded:
                loaded += 1
            else:
                skipped += 1

            LOGGER.info(
                "File result file=%s table=%s loaded=%s rows=%s detail=%s",
                result.file_name,
                result.table_name,
                result.loaded,
                result.rows_loaded,
                result.detail,
            )

        refresh_join_output_table(connection)

    summary = JobSummary(
        processed_at=process_date,
        files_expected=len(files_by_table),
        files_found=found,
        files_loaded=loaded,
        files_skipped=skipped,
    )

    LOGGER.info(
        "Load job finished processed_at=%s expected=%s found=%s loaded=%s skipped=%s",
        summary.processed_at,
        summary.files_expected,
        summary.files_found,
        summary.files_loaded,
        summary.files_skipped,
    )
    return summary


def _report_job_failure(error: BaseException) -> None:
    """Best-effort audit push to the error-handler service. Never raises.

    Gated by ERROR_HANDLER_SERVICE_URL; no-op when unset.
    """

    import json
    import traceback
    import urllib.request

    base_url = (os.getenv("ERROR_HANDLER_SERVICE_URL") or "").strip().rstrip("/")
    if not base_url:
        return

    component = "co_pqrs_back_load_seizures_data"
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
        _report_job_failure(error)
        raise


if __name__ == "__main__":
    main()
