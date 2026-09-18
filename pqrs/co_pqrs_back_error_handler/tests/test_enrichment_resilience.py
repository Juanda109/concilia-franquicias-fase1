"""Resilience test: a report is still written when OpenSearch enrichment fails."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock

import boto3
from moto import mock_aws

from application.error_report.error_report_service import generate_error_report
from domain.error_report.models import ErrorReportCommand
from infrastructure.core.config import MinioSettings
from infrastructure.filesystem.error_report_writer import ErrorReportWriter
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
    )


class EnrichmentFailureResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_written_to_minio_when_opensearch_down(self) -> None:
        # Store whose enrichment raises (simulating OpenSearch being unreachable).
        store = AsyncMock()
        store.load_conversation_snapshot.side_effect = ConnectionError("opensearch down")

        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            object_store = ObjectStore(_minio_settings(), client=client)
            writer = ErrorReportWriter(
                minio_settings=_minio_settings(),
                object_store=object_store,
            )

            command = ErrorReportCommand(
                conversation_id="03966512_20260619",
                error_message="HTTP 500 on POST /chat",
                error_type="HTTP500",
                error_source="co_pqrs_back_agent",
            )

            stored = await generate_error_report(command, store=store, writer=writer)

            # The report was still produced and persisted, despite enrichment failing.
            self.assertFalse(stored.report.analytics.conversation_found)
            self.assertTrue(
                any("snapshot_load_failed" in w for w in stored.report.conversation_snapshot.warnings)
            )

            key = str(stored.exported_file_path)
            raw = client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            self.assertEqual(json.loads(raw)["failure"]["error_type"], "HTTP500")

    async def test_report_without_conversation_id_for_non_conversation_service(self) -> None:
        # back_data-style error: no conversation_id, only a component. The store
        # must NOT be queried, and the report is still written.
        store = AsyncMock()

        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            object_store = ObjectStore(_minio_settings(), client=client)
            writer = ErrorReportWriter(
                minio_settings=_minio_settings(),
                object_store=object_store,
            )

            command = ErrorReportCommand(
                conversation_id=None,
                component="co_pqrs_back_data",
                error_message="psycopg.OperationalError: connection refused",
                error_type="OperationalError",
                error_source="co_pqrs_back_data",
            )

            stored = await generate_error_report(command, store=store, writer=writer)

            store.load_conversation_snapshot.assert_not_called()
            self.assertFalse(stored.report.analytics.conversation_found)
            self.assertEqual(stored.report.failure.component, "co_pqrs_back_data")
            key = str(stored.exported_file_path)
            raw = client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            self.assertEqual(json.loads(raw)["failure"]["component"], "co_pqrs_back_data")


if __name__ == "__main__":
    unittest.main()
