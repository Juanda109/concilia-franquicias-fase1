#!/usr/bin/env python3
"""
Co-PQRS Back Conversation Extractor

Extrae turnos de conversación desde OpenSearch (pqr-metrics-*)
filtrando event=conversation.turn y los exporta a Excel diario con
deduplicación por _id para soportar ejecuciones incrementales cada 30 min.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Iterator, Set, List, Any

import pandas as pd
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError as OSConnectionError


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


# ============================================================================
# SETTINGS
# ============================================================================

# UTC offset for America/Bogota (no DST)
_BOGOTA_OFFSET = timezone(timedelta(hours=-5))


@dataclass
class Settings:
    """Configuración desde variables de entorno."""

    opensearch_url: str
    opensearch_user: str
    opensearch_password: str
    opensearch_verify_certs: bool = False
    opensearch_index: str = "pqr-metrics-*"
    opensearch_batch_size: int = 500
    opensearch_scroll_keepalive: str = "2m"
    ruta_proceso: str = "/mnt/ada_data"
    looker_folder_name: str = "looker_conversation_pqrs"
    scan_lookback_days: int = 0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            opensearch_url=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
            opensearch_user=os.getenv("OPENSEARCH_USER", "admin"),
            opensearch_password=os.getenv("OPENSEARCH_PASSWORD", ""),
            opensearch_verify_certs=os.getenv(
                "OPENSEARCH_VERIFY_CERTS", "false"
            ).lower() == "true",
            opensearch_index=os.getenv("OPENSEARCH_INDEX", "pqr-metrics-*"),
            opensearch_batch_size=int(os.getenv("OPENSEARCH_BATCH_SIZE", "500")),
            opensearch_scroll_keepalive=os.getenv(
                "OPENSEARCH_SCROLL_KEEPALIVE", "2m"
            ),
            ruta_proceso=os.getenv("RUTA_PROCESO", "/mnt/ada_data"),
            looker_folder_name=os.getenv(
                "LOOKER_FOLDER_NAME", "looker_conversation_pqrs"
            ),
            scan_lookback_days=int(os.getenv("SCAN_LOOKBACK_DAYS", "0")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


# ============================================================================
# OPENSEARCH CLIENT
# ============================================================================

def create_opensearch_client(settings: Settings) -> OpenSearch:
    """Crea cliente OpenSearch con soporte SSL configurable."""
    from urllib.parse import urlparse

    parsed = urlparse(settings.opensearch_url)
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (9200 if not use_ssl else 443)

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=use_ssl,
        verify_certs=settings.opensearch_verify_certs,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
        http_compress=True,
        timeout=30,
    )


# ============================================================================
# VENTANA TEMPORAL
# ============================================================================

def day_utc_range(target_date: date) -> tuple[str, str]:
    """
    Devuelve el rango UTC equivalente a un día completo en hora Bogotá (UTC-5).
    Ej: 2026-08-05 Bogotá → [2026-08-05T05:00:00Z, 2026-08-06T05:00:00Z)
    """
    bogota_midnight = datetime(
        target_date.year, target_date.month, target_date.day,
        0, 0, 0, tzinfo=_BOGOTA_OFFSET,
    )
    gte = bogota_midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lt = (bogota_midnight + timedelta(days=1)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return gte, lt


def iter_dates(reference_date: date, scan_lookback_days: int) -> Iterator[date]:
    """Itera desde (reference_date - lookback) hasta reference_date inclusive."""
    start = reference_date - timedelta(days=max(0, scan_lookback_days))
    current = start
    while current <= reference_date:
        yield current
        current += timedelta(days=1)


# ============================================================================
# DEDUPLICACIÓN
# ============================================================================

def load_existing_ids(excel_path: Path, logger: logging.Logger) -> Set[str]:
    """Lee columna _id del Excel existente y devuelve el set de IDs ya guardados."""
    if not excel_path.exists():
        logger.info("Excel no existe aún: %s", excel_path)
        return set()
    try:
        df = pd.read_excel(excel_path, engine="openpyxl", usecols=["_id"])
        ids = set(df["_id"].dropna().astype(str).unique())
        logger.info("Cargados %d _id existentes de %s", len(ids), excel_path)
        return ids
    except Exception as exc:
        logger.warning("No se pudo leer _id del Excel existente (%s): %s", excel_path, exc)
        return set()


# ============================================================================
# QUERY DSL
# ============================================================================

def build_day_query(target_date: date) -> dict:
    """Construye la query DSL para un día completo en hora Bogotá."""
    gte, lt = day_utc_range(target_date)
    return {
        "bool": {
            "filter": [
                {"term": {"event": "conversation.turn"}},
                {"range": {"@timestamp": {"gte": gte, "lt": lt}}},
            ]
        }
    }


# ============================================================================
# SCROLL
# ============================================================================

def scroll_hits(
    client: OpenSearch,
    settings: Settings,
    query: dict,
    logger: logging.Logger,
) -> Iterator[dict[str, Any]]:
    """Itera sobre todos los hits usando scroll API."""
    response = client.search(
        index=settings.opensearch_index,
        body={"query": query, "sort": ["_doc"]},
        size=settings.opensearch_batch_size,
        scroll=settings.opensearch_scroll_keepalive,
    )
    scroll_id = response.get("_scroll_id")
    try:
        while True:
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break
            yield from hits
            if not scroll_id:
                break
            response = client.scroll(
                scroll_id=scroll_id,
                scroll=settings.opensearch_scroll_keepalive,
            )
            scroll_id = response.get("_scroll_id", scroll_id)
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass


# ============================================================================
# APLANADO DE DOCUMENTO
# ============================================================================

def flatten_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Extrae _id + todos los campos de _source en un dict plano."""
    row = {"_id": hit.get("_id", "")}
    row.update(hit.get("_source", {}))
    return row


# ============================================================================
# GUARDADO / APPEND EXCEL
# ============================================================================

def validate_and_create_output_folder(settings: Settings, logger: logging.Logger) -> Path:
    output_folder = Path(settings.ruta_proceso) / settings.looker_folder_name
    try:
        output_folder.mkdir(parents=True, exist_ok=True)
        logger.info("Carpeta destino validada: %s", output_folder)
        return output_folder
    except Exception as exc:
        logger.error("Error creando carpeta %s: %s", output_folder, exc)
        raise


def save_or_append_excel(
    excel_path: Path,
    rows: List[dict[str, Any]],
    logger: logging.Logger,
) -> None:
    """Append de filas nuevas al Excel del día; crea el fichero si no existe."""
    if not rows:
        logger.info("Sin filas nuevas para guardar en %s", excel_path)
        return

    df_new = pd.DataFrame(rows)

    if excel_path.exists():
        df_existing = pd.read_excel(excel_path, engine="openpyxl")
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        logger.info(
            "Append a %s: %d existentes + %d nuevas = %d total",
            excel_path, len(df_existing), len(df_new), len(df_combined),
        )
    else:
        df_combined = df_new
        logger.info("Creando %s con %d filas", excel_path, len(df_new))

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_combined.to_excel(writer, index=False, sheet_name="conversaciones")

    logger.info("Excel guardado: %s", excel_path)


# ============================================================================
# ORQUESTACIÓN PRINCIPAL
# ============================================================================

def main() -> int:
    load_dotenv()
    settings = Settings.from_env()
    logger = setup_logging(settings.log_level)

    logger.info("=" * 70)
    logger.info("Iniciando Co-PQRS Back Conversation Extractor")
    logger.info("=" * 70)
    logger.info("OpenSearch URL:  %s", settings.opensearch_url)
    logger.info("Índice:          %s", settings.opensearch_index)
    logger.info("Output Folder:   %s", settings.ruta_proceso)
    logger.info("Lookback days:   %d", settings.scan_lookback_days)

    try:
        output_folder = validate_and_create_output_folder(settings, logger)

        logger.info("Conectando a OpenSearch...")
        client = create_opensearch_client(settings)
        client.info()  # falla rápido si la conexión no está disponible

        reference_date = datetime.now(_BOGOTA_OFFSET).date()
        total_new = 0
        total_skipped = 0
        total_errors = 0

        for target_date in iter_dates(reference_date, settings.scan_lookback_days):
            date_str = target_date.strftime("%Y%m%d")
            excel_path = output_folder / f"conversaciones_{date_str}.xlsx"

            logger.info("-" * 50)
            logger.info("Procesando fecha: %s", target_date.isoformat())

            existing_ids = load_existing_ids(excel_path, logger)
            query = build_day_query(target_date)

            rows: List[dict[str, Any]] = []
            errors = 0

            try:
                for hit in scroll_hits(client, settings, query, logger):
                    doc_id = hit.get("_id", "")
                    if doc_id in existing_ids:
                        total_skipped += 1
                        continue
                    rows.append(flatten_hit(hit))
                    existing_ids.add(doc_id)
            except OSConnectionError as exc:
                logger.error("Error de conexión con OpenSearch: %s", exc)
                errors += 1
            except Exception as exc:
                logger.error("Error durante scroll para %s: %s", target_date, exc)
                errors += 1

            save_or_append_excel(excel_path, rows, logger)
            total_new += len(rows)
            total_errors += errors

        logger.info("=" * 70)
        logger.info("RESUMEN DE EJECUCIÓN")
        logger.info("=" * 70)
        logger.info("Registros nuevos escritos:  %d", total_new)
        logger.info("Duplicados omitidos:        %d", total_skipped)
        logger.info("Errores:                    %d", total_errors)
        logger.info("=" * 70)

        return 0

    except Exception as exc:
        logger.error("Error fatal: %s", exc, exc_info=True)
        return 1


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    raise SystemExit(main())
