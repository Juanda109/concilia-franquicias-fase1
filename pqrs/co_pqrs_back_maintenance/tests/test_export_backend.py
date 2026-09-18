from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

import maintenance.services as services
from commons.object_store import ObjectStore

from helpers import make_settings


BUCKET = "pqr-conversations-history"


def _payload(conversation_id: str = "03966512_20260618") -> dict:
    return {
        "metadata": {
            "conversation_id": conversation_id,
            "message_count": 2,
            "closed_at": "2026-06-18T21:40:00+00:00",
            "exported_at": "2026-06-18T21:45:00+00:00",
            "export_relative_path": f"conversations/{conversation_id}/2026/06/18/x.json",
        },
        "conversation": {
            "_source": {
                "conversation_id": conversation_id,
                "user_id": "03966512",
                "status": "Closed",
                "general_workflow": "Guia rapida",
                "workflow": "Riesgo",
                "current_step": "1.2",
                "satisfaction_status": "ENTERED",
                "satisfaction_result": True,
                "first_msg_date": "2026-06-18T21:30:00+00:00",
                "last_msg_date": "2026-06-18T21:39:00+00:00",
            }
        },
        "messages": [
            {
                "_source": {
                    "tokens": {"input_tokens": 120, "output_tokens": 85, "total_tokens": 205},
                    "timing": {"total_duration_ms": 2750},
                }
            },
            {
                "_source": {
                    "tokens": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    "timing": {"total_duration_ms": 500},
                }
            },
        ],
    }


# ---- build_conversation_summary -------------------------------------------------


def test_summary_flattens_key_fields() -> None:
    summary = services.build_conversation_summary(_payload())

    assert summary["conversation_id"] == "03966512_20260618"
    assert summary["user_id"] == "03966512"
    assert summary["workflow"] == "Riesgo"
    assert summary["general_workflow"] == "Guia rapida"
    assert summary["final_step"] == "1.2"
    assert summary["satisfaction_status"] == "ENTERED"
    assert summary["satisfaction_result"] is True
    assert summary["message_count"] == 2
    assert summary["total_tokens"] == 220
    assert summary["total_duration_ms"] == 3250


def test_summary_handles_no_messages_and_nulls() -> None:
    payload = _payload()
    payload["messages"] = []
    payload["metadata"].pop("message_count")
    payload["conversation"]["_source"]["satisfaction_result"] = None

    summary = services.build_conversation_summary(payload)

    assert summary["message_count"] == 0
    assert summary["total_tokens"] == 0
    assert summary["total_duration_ms"] == 0
    assert summary["satisfaction_result"] is None


def test_summary_key_is_partitioned_by_close_date() -> None:
    payload = _payload()
    summary = services.build_conversation_summary(payload)
    key = services.build_summary_key(summary, payload)
    assert key == "summaries/dt=2026-06-18/03966512_20260618.json"


# ---- write_export dispatcher ----------------------------------------------------


@pytest.fixture
def s3_client() -> Iterator[object]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_write_export_minio_writes_raw_and_summary(s3_client: object) -> None:
    settings = make_settings(minio_enabled=True, minio_bucket=BUCKET)
    store = ObjectStore(settings, client=s3_client)
    payload = _payload()
    relative_path = Path(payload["metadata"]["export_relative_path"])

    services.write_export(settings, relative_path, payload, store=store)

    raw = s3_client.get_object(Bucket=BUCKET, Key=relative_path.as_posix())
    assert json.loads(raw["Body"].read())["conversation"]["_source"]["workflow"] == "Riesgo"

    summary_obj = s3_client.get_object(
        Bucket=BUCKET, Key="summaries/dt=2026-06-18/03966512_20260618.json"
    )
    summary_line = summary_obj["Body"].read().decode("utf-8").strip()
    assert json.loads(summary_line)["total_tokens"] == 220


def test_write_export_filesystem_when_disabled(tmp_path: Path) -> None:
    settings = make_settings(minio_enabled=False, output_dir=tmp_path)
    payload = _payload()
    relative_path = Path(payload["metadata"]["export_relative_path"])

    services.write_export(settings, relative_path, payload)

    raw_file = tmp_path / relative_path
    assert raw_file.exists()
    summary_file = tmp_path / "summaries/dt=2026-06-18/03966512_20260618.json"
    assert summary_file.exists()
    assert json.loads(summary_file.read_text().strip())["user_id"] == "03966512"


def test_write_export_minio_idempotent(s3_client: object) -> None:
    settings = make_settings(minio_enabled=True, minio_bucket=BUCKET)
    store = ObjectStore(settings, client=s3_client)
    payload = _payload()
    relative_path = Path(payload["metadata"]["export_relative_path"])

    services.write_export(settings, relative_path, payload, store=store)
    # Second call must not raise and must not duplicate (idempotent skip).
    services.write_export(settings, relative_path, payload, store=store)

    listing = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="conversations/")
    assert listing["KeyCount"] == 1
