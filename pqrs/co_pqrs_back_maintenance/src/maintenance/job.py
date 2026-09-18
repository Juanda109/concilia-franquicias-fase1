from __future__ import annotations

from datetime import UTC, datetime

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from classes.models import MaintenanceSummary
from commons.logging_utils import configure_logging, get_logger, log_execution
from commons.error_audit import report_job_failure
from commons.opensearch_helpers import build_client, log_connection_help
from maintenance.control_table_export import export_control_table
from maintenance.services import close_stale_active_conversations, export_closed_conversations
from settings.config import load_settings


logger = get_logger(__name__)


@log_execution
def run_maintenance_job() -> MaintenanceSummary:
    configure_logging()

    settings = load_settings()
    now = datetime.now(UTC)
    client = build_client(settings)

    logger.info(
        "Starting maintenance job conversations_index=%s messages_index=%s status_field=%s active_value=%s closed_value=%s last_interaction_fields=%s output_dir=%s delete_conversations=%s delete_messages=%s",
        settings.conversations_index,
        settings.messages_index,
        settings.conversation_status_field,
        settings.active_status_value,
        settings.closed_status_value,
        ",".join(settings.last_interaction_fields),
        settings.output_dir.resolve(),
        settings.delete_exported_conversations,
        settings.delete_exported_messages,
    )

    try:
        export_summary = export_closed_conversations(client, settings, now)
        close_summary = close_stale_active_conversations(client, settings, now)
        control_snapshot = export_control_table(client, settings, now)
    except OpenSearchConnectionError as error:
        log_connection_help(settings)
        report_job_failure(settings, error, source="run_maintenance_job")
        raise
    except Exception as error:
        report_job_failure(settings, error, source="run_maintenance_job")
        raise

    logger.info(
        "Maintenance job finished closed_candidates=%s exported_closed=%s deleted_conversations=%s deleted_messages=%s marked_as_exported=%s active_candidates=%s status_changes_active_to_closed=%s skipped_missing_last_interaction=%s control_clients=%s control_records=%s",
        export_summary.candidates_found,
        export_summary.exported_conversations,
        export_summary.deleted_conversations,
        export_summary.deleted_messages,
        export_summary.marked_as_exported,
        close_summary.candidates_found,
        close_summary.closed_from_active,
        close_summary.skipped_missing_last_interaction,
        control_snapshot.clients_scanned,
        control_snapshot.records_written,
    )

    return MaintenanceSummary(
        export_summary=export_summary,
        close_summary=close_summary,
        control_snapshot=control_snapshot,
    )


def main() -> None:
    run_maintenance_job()
