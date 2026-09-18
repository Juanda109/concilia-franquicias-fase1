"""Tests for the per-request full log sink (writer + service)."""

from __future__ import annotations

import unittest

import boto3
from moto import mock_aws

from application.request_log.request_log_service import record_request_log
from domain.request_log.models import RequestLogCommand
from infrastructure.core.config import MinioSettings
from infrastructure.filesystem.request_log_writer import RequestLogWriter
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


def _log_command() -> RequestLogCommand:
    return RequestLogCommand(
        component="co_pqrs_back_agent",
        conversation_id="03966512_20260715",
        customer_id="03966512",
        request_id="req-abc-123",
        segment="main",
        method="POST",
        path="/chat",
        status_code=200,
        elapsed_ms=852.4,
        line_count=3,
        truncated=False,
        log_text="INFO línea 1\nINFO línea 2\nWARNING línea 3\n",
    )


class RequestLogWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_request_log_to_minio_separate_prefix(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)
            writer = RequestLogWriter(
                settings=None,
                minio_settings=_minio_settings(),
                object_store=store,
            )

            _record, stored_path = await record_request_log(
                _log_command(), writer=writer
            )

            key = str(stored_path)
            # SEPARATE prefix from the structured traces (clients/).
            self.assertTrue(key.startswith("request-logs/customer=03966512/dt="))
            self.assertIn("conversation=03966512_20260715", key)
            self.assertIn("req-abc-123", key)
            self.assertTrue(key.endswith("_main.log"))

            body = client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()
            self.assertIn("INFO línea 1", body)
            self.assertIn("WARNING línea 3", body)

    async def test_customer_derived_from_conversation_when_missing(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)
            writer = RequestLogWriter(
                settings=None,
                minio_settings=_minio_settings(),
                object_store=store,
            )

            command = RequestLogCommand(
                component="co_pqrs_back_data",
                conversation_id="c1_20260716",
                customer_id=None,
                request_id="r2",
                segment="background",
                log_text="line\n",
                line_count=1,
            )
            _record, stored_path = await record_request_log(command, writer=writer)

            key = str(stored_path)
            self.assertTrue(key.startswith("request-logs/customer=c1/dt="))
            self.assertTrue(key.endswith("_background.log"))


if __name__ == "__main__":
    unittest.main()
