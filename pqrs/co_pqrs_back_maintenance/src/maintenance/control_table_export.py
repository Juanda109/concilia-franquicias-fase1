"""Snapshot the OpenSearch ``client-control-table`` index into NDJSON on MinIO.

The control table stores per-client interaction counters nested by month and by
day. This module flattens each document into analytics-friendly NDJSON records
of three types and uploads a dated snapshot to the object store.

Privacy: the ``monthly.*.workflows.*.data`` blob holds the customer's commercial
back-data (possible PII) and is NOT a metric, so it is always excluded.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from opensearchpy import OpenSearch

from classes.models import ControlTableSnapshotSummary, Settings
from commons.logging_utils import get_logger, log_execution
from commons.object_store import ObjectStore
from commons.opensearch_helpers import scroll_documents


logger = get_logger(__name__)


RECORD_TYPE_CLIENT = "client"
RECORD_TYPE_WORKFLOW_MONTH = "workflow_month"
RECORD_TYPE_DAILY_SESSIONS = "daily_sessions"


def flatten_control_record(source: dict[str, Any], *, document_id: str | None = None) -> list[dict[str, Any]]:
    """Flatten one control-table document into a list of NDJSON records.

    Produces, per client:
    - one ``client`` summary record,
    - one ``workflow_month`` record per (month, workflow),
    - one ``daily_sessions`` record per day.

    The opaque ``data`` blob under each workflow is never emitted.
    """

    if not isinstance(source, dict):
        return []

    client_id = source.get("client_id") or document_id
    if client_id is None:
        return []
    client_id = str(client_id)

    records: list[dict[str, Any]] = [
        {
            "record_type": RECORD_TYPE_CLIENT,
            "client_id": client_id,
            "total_interactions": _coerce_int(source.get("total_interactions")),
            "last_flow_id": source.get("last_flow_id"),
            "last_flow_label": source.get("last_flow_label"),
            "last_interaction_at": source.get("last_interaction_at"),
            "last_session_at": source.get("last_session_at"),
        }
    ]

    monthly = source.get("monthly")
    if isinstance(monthly, dict):
        for period, month_bucket in monthly.items():
            if not isinstance(month_bucket, dict):
                continue
            workflows = month_bucket.get("workflows")
            if not isinstance(workflows, dict):
                continue
            for workflow_id, workflow_bucket in workflows.items():
                if not isinstance(workflow_bucket, dict):
                    continue
                records.append(
                    {
                        "record_type": RECORD_TYPE_WORKFLOW_MONTH,
                        "client_id": client_id,
                        "period": str(period),
                        "workflow": str(workflow_id),
                        # Exclude the "data" blob on purpose (PII / not a metric).
                        "label": workflow_bucket.get("label"),
                        "count": _coerce_int(workflow_bucket.get("count")),
                        "last_interaction_at": workflow_bucket.get("last_interaction_at"),
                    }
                )

    daily_sessions = source.get("daily_sessions")
    if isinstance(daily_sessions, dict):
        for day, day_bucket in daily_sessions.items():
            if not isinstance(day_bucket, dict):
                continue
            records.append(
                {
                    "record_type": RECORD_TYPE_DAILY_SESSIONS,
                    "client_id": client_id,
                    "day": str(day),
                    "sessions": _coerce_int(day_bucket.get("count")),
                    "last_session_at": day_bucket.get("last_session_at"),
                }
            )

    return records


@log_execution
def export_control_table(
    client: OpenSearch,
    settings: Settings,
    now: datetime,
    *,
    store: ObjectStore | None = None,
    hits: Iterable[dict[str, Any]] | None = None,
) -> ControlTableSnapshotSummary:
    """Scroll the control-table index and write a dated NDJSON snapshot to MinIO."""

    if not settings.minio_enabled:
        logger.info("MinIO disabled; skipping client-control-table snapshot")
        return ControlTableSnapshotSummary(
            clients_scanned=0, records_written=0, object_key=None, skipped=True
        )

    if hits is None:
        hits = scroll_documents(
            client,
            settings,
            settings.control_index,
            {"match_all": {}},
        )

    all_records: list[dict[str, Any]] = []
    clients_scanned = 0
    for hit in hits:
        source = hit.get("_source", {})
        document_id = hit.get("_id")
        records = flatten_control_record(source, document_id=document_id)
        if records:
            clients_scanned += 1
            all_records.extend(records)

    if not all_records:
        logger.info("No client-control-table records to snapshot")
        return ControlTableSnapshotSummary(
            clients_scanned=0, records_written=0, object_key=None
        )

    partition = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    object_key = f"control-table/dt={partition}/control-table_{timestamp}.json"

    active_store = store or ObjectStore(settings)
    active_store.write_ndjson(object_key, all_records, overwrite=True)

    logger.info(
        "Wrote client-control-table snapshot clients=%s records=%s key=%s",
        clients_scanned,
        len(all_records),
        object_key,
    )
    return ControlTableSnapshotSummary(
        clients_scanned=clients_scanned,
        records_written=len(all_records),
        object_key=object_key,
    )


def _coerce_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0
