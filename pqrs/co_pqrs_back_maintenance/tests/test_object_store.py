from __future__ import annotations

import json
from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from commons.object_store import ObjectStore

from helpers import make_settings


BUCKET = "pqr-conversations-history"


@pytest.fixture
def s3_client() -> Iterator[object]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def _read(client: object, key: str) -> str:
    response = client.get_object(Bucket=BUCKET, Key=key)
    return response["Body"].read().decode("utf-8")


def test_write_json_uploads_object(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)

    written = store.write_json("conversations/a/2026/06/18/a.json", {"hello": "world"})

    assert written is True
    assert json.loads(_read(s3_client, "conversations/a/2026/06/18/a.json")) == {"hello": "world"}


def test_write_json_is_idempotent(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)
    key = "conversations/a/2026/06/18/a.json"

    first = store.write_json(key, {"v": 1})
    second = store.write_json(key, {"v": 2})

    assert first is True
    assert second is False
    # Original content preserved because second upload was skipped.
    assert json.loads(_read(s3_client, key)) == {"v": 1}


def test_write_json_overwrite_forces_upload(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)
    key = "conversations/a/2026/06/18/a.json"

    store.write_json(key, {"v": 1})
    store.write_json(key, {"v": 2}, overwrite=True)

    assert json.loads(_read(s3_client, key)) == {"v": 2}


def test_write_ndjson_writes_one_record_per_line(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)
    records = [{"id": 1}, {"id": 2}, {"id": 3}]

    written = store.write_ndjson("summaries/dt=2026-06-18/a.json", records)

    assert written is True
    body = _read(s3_client, "summaries/dt=2026-06-18/a.json")
    lines = [line for line in body.split("\n") if line]
    assert [json.loads(line) for line in lines] == records


def test_write_ndjson_empty_records(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)

    written = store.write_ndjson("summaries/dt=2026-06-18/empty.json", [])

    assert written is True
    assert _read(s3_client, "summaries/dt=2026-06-18/empty.json") == ""


def test_object_exists(s3_client: object) -> None:
    store = ObjectStore(make_settings(minio_bucket=BUCKET), client=s3_client)

    assert store.object_exists("missing/key.json") is False
    store.write_json("present/key.json", {"a": 1})
    assert store.object_exists("present/key.json") is True


def test_requires_bucket() -> None:
    with pytest.raises(ValueError):
        ObjectStore(make_settings(minio_bucket=None), client=object())
