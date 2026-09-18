from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from commons.object_store import ObjectStore
from maintenance.control_table_export import (
    RECORD_TYPE_CLIENT,
    RECORD_TYPE_DAILY_SESSIONS,
    RECORD_TYPE_WORKFLOW_MONTH,
    export_control_table,
    flatten_control_record,
)

from helpers import make_settings


BUCKET = "pqr-conversations-history"


def _control_doc() -> dict:
    return {
        "client_id": "03966512",
        "total_interactions": 12,
        "last_flow_id": "Riesgo",
        "last_flow_label": "Centrales de riesgo",
        "last_interaction_at": "2026-06-18T21:39:00+00:00",
        "last_session_at": "2026-06-18T21:30:00+00:00",
        "updated_at": "2026-06-18T21:39:00+00:00",
        "expires_at": "2026-09-18T21:39:00+00:00",
        "monthly": {
            "2026-06": {
                "total_interactions": 5,
                "last_interaction_at": "2026-06-18T21:39:00+00:00",
                "workflows": {
                    "Riesgo": {
                        "count": 3,
                        "label": "Centrales de riesgo",
                        "last_interaction_at": "2026-06-18T21:39:00+00:00",
                        "data": {"secret_commercial": "PII blob"},
                    },
                    "Solicitud": {"count": 2, "label": "Solicitud"},
                },
            }
        },
        "daily_sessions": {
            "20260618": {"count": 2, "last_session_at": "2026-06-18T21:30:00+00:00"},
        },
    }


# ---- flatten_control_record ----------------------------------------------------


def test_flatten_produces_three_record_types() -> None:
    records = flatten_control_record(_control_doc())

    by_type: dict[str, list[dict]] = {}
    for record in records:
        by_type.setdefault(record["record_type"], []).append(record)

    assert len(by_type[RECORD_TYPE_CLIENT]) == 1
    assert len(by_type[RECORD_TYPE_WORKFLOW_MONTH]) == 2
    assert len(by_type[RECORD_TYPE_DAILY_SESSIONS]) == 1


def test_flatten_client_summary_fields() -> None:
    client_record = next(
        r for r in flatten_control_record(_control_doc()) if r["record_type"] == RECORD_TYPE_CLIENT
    )
    assert client_record["client_id"] == "03966512"
    assert client_record["total_interactions"] == 12
    assert client_record["last_flow_id"] == "Riesgo"
    assert client_record["last_session_at"] == "2026-06-18T21:30:00+00:00"


def test_flatten_workflow_month_records_and_excludes_data() -> None:
    records = flatten_control_record(_control_doc())
    wf_records = [r for r in records if r["record_type"] == RECORD_TYPE_WORKFLOW_MONTH]

    riesgo = next(r for r in wf_records if r["workflow"] == "Riesgo")
    assert riesgo["period"] == "2026-06"
    assert riesgo["count"] == 3
    assert riesgo["label"] == "Centrales de riesgo"
    # The PII blob must never be emitted.
    assert "data" not in riesgo
    assert "secret_commercial" not in str(records)


def test_flatten_daily_sessions_record() -> None:
    records = flatten_control_record(_control_doc())
    day = next(r for r in records if r["record_type"] == RECORD_TYPE_DAILY_SESSIONS)
    assert day["day"] == "20260618"
    assert day["sessions"] == 2


def test_flatten_uses_document_id_when_client_id_missing() -> None:
    doc = {"total_interactions": 1}
    records = flatten_control_record(doc, document_id="abc")
    assert records[0]["client_id"] == "abc"


def test_flatten_empty_returns_nothing_without_id() -> None:
    assert flatten_control_record({}) == []
    assert flatten_control_record("not a dict") == []  # type: ignore[arg-type]


# ---- export_control_table ------------------------------------------------------


@pytest.fixture
def s3_client() -> Iterator[object]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_export_writes_ndjson_snapshot(s3_client: object) -> None:
    settings = make_settings(minio_enabled=True, minio_bucket=BUCKET)
    store = ObjectStore(settings, client=s3_client)
    hits = [{"_id": "03966512", "_source": _control_doc()}]
    now = datetime(2026, 6, 18, 21, 45, 0, tzinfo=UTC)

    summary = export_control_table(None, settings, now, store=store, hits=hits)

    assert summary.clients_scanned == 1
    assert summary.records_written == 4  # 1 client + 2 workflow_month + 1 daily
    assert summary.object_key == "control-table/dt=2026-06-18/control-table_20260618T214500Z.json"

    body = s3_client.get_object(Bucket=BUCKET, Key=summary.object_key)["Body"].read().decode()
    lines = [line for line in body.split("\n") if line]
    assert len(lines) == 4


def test_export_skips_when_minio_disabled() -> None:
    settings = make_settings(minio_enabled=False)
    summary = export_control_table(None, settings, datetime.now(UTC), hits=[])
    assert summary.skipped is True
    assert summary.object_key is None


def test_export_no_records(s3_client: object) -> None:
    settings = make_settings(minio_enabled=True, minio_bucket=BUCKET)
    store = ObjectStore(settings, client=s3_client)
    summary = export_control_table(None, settings, datetime.now(UTC), store=store, hits=[])
    assert summary.records_written == 0
    assert summary.object_key is None
