"""Tests for the E2E trace-event sink (writer + service)."""

from __future__ import annotations

import json
import unittest

import boto3
from moto import mock_aws

from application.trace_event.trace_event_service import record_trace_event
from domain.trace_event.models import TraceEventCommand
from infrastructure.core.config import MinioSettings
from infrastructure.filesystem.trace_event_writer import TraceEventWriter
from infrastructure.storage.object_store import ObjectStore

BUCKET = "audit-logs"


def _minio_settings() -> MinioSettings:
    return MinioSettings(
        enabled=True,
        endpoint_url="http://minio:9000",
        bucket=BUCKET,
        region="us-east-1",
        access_key="admin",
        secret_key="secret",
        addressing_style="path",
    )


def _aso_ok_command() -> TraceEventCommand:
    return TraceEventCommand(
        event_type="aso",
        operation="commercial_info_overview",
        outcome="ok",
        component="co_pqrs_back_data",
        conversation_id="03966512_20260715",
        customer_id="03966512",
        target="https://aso/overview",
        status_code=200,
        elapsed_ms=142.5,
        request_summary={"document_type": "C.C", "document_number": "****3414"},
        response_summary={"bytes": 2048, "keys": ["data"]},
        tags=["aso", "trace"],
    )


class TraceEventWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_aso_ok_to_minio(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)
            writer = TraceEventWriter(
                settings=None,
                minio_settings=_minio_settings(),
                object_store=store,
            )

            record, stored_path = await record_trace_event(
                _aso_ok_command(), writer=writer
            )

            key = str(stored_path)
            self.assertTrue(key.startswith("clients/customer=03966512/dt="))
            self.assertIn("conversation=03966512_20260715", key)
            raw = client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            payload = json.loads(raw)
            self.assertEqual(payload["event"]["status_code"], 200)
            self.assertEqual(payload["event"]["operation"], "commercial_info_overview")
            self.assertEqual(payload["event"]["outcome"], "ok")
            # Secrets must never appear in what we persist.
            self.assertNotIn("tsec", raw.decode().lower())
            self.assertNotIn("password", raw.decode().lower())

            # Flattened summary is written for analytics.
            partition = record.metadata.recorded_at.strftime("%Y-%m-%d")
            summary_key = (
                f"trace-summaries/dt={partition}/"
                f"{record.metadata.trace_event_id}.json"
            )
            summary = (
                client.get_object(Bucket=BUCKET, Key=summary_key)["Body"]
                .read()
                .decode()
                .strip()
            )
            summary_record = json.loads(summary)
            self.assertEqual(summary_record["event_type"], "aso")
            self.assertEqual(summary_record["status_code"], 200)

    async def test_write_error_event_to_minio(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)
            writer = TraceEventWriter(
                settings=None,
                minio_settings=_minio_settings(),
                object_store=store,
            )

            command = TraceEventCommand(
                event_type="postgres",
                operation="read_customer_identity",
                outcome="error",
                component="co_pqrs_back_data",
                conversation_id="c1",
                target="ada_info_detail",
                elapsed_ms=5.0,
                error_type="DataSourceError",
                error_message="connection refused",
            )
            _record, stored_path = await record_trace_event(command, writer=writer)

            raw = client.get_object(Bucket=BUCKET, Key=str(stored_path))["Body"].read()
            payload = json.loads(raw)
            self.assertEqual(payload["event"]["outcome"], "error")
            self.assertEqual(payload["event"]["error_type"], "DataSourceError")
            # customer_id derived from conversation_id (c1) -> clients/customer=c1/...
            self.assertTrue(str(stored_path).startswith("clients/customer=c1/dt="))


if __name__ == "__main__":
    unittest.main()
