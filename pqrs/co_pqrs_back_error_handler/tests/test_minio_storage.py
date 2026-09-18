"""Tests for the MinIO object-storage backend of the error handler."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone

import boto3
from moto import mock_aws

from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from domain.error_report.models import (
    ConversationSnapshot,
    ErrorAnalytics,
    ErrorReport,
    ErrorReportFailure,
    ErrorReportMetadata,
)
from infrastructure.core.config import MinioSettings, load_minio_settings
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
        addressing_style="path",
    )


def _sample_report() -> ErrorReport:
    generated_at = datetime(2026, 6, 19, 15, 0, 0, tzinfo=timezone.utc)
    message = Message(
        id="m1",
        role=MessageRole.ASSISTANT,
        content="respuesta",
        tokens=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        timing=MessageTiming(received_at=generated_at, responded_at=generated_at, total_duration_ms=100),
    )
    conversation = Conversation(
        conversation_id="03966512_20260619",
        status=ConversationStatus.ERROR,
        current_step="1.2",
        general_workflow="Guia rapida",
        workflow="Riesgo",
        user_id="03966512",
        messages=[message],
    )
    snapshot = ConversationSnapshot(
        conversation_id=conversation.conversation_id,
        found_in_opensearch=True,
        conversation=conversation,
        messages=[message],
    )
    analytics = ErrorAnalytics(
        conversation_found=True,
        conversation_reference_found=True,
        message_documents_found=True,
        message_document_count=1,
        parsed_message_count=1,
        invalid_message_count=0,
        conversation_status="Error",
        general_workflow="Guia rapida",
        workflow="Riesgo",
        current_step="1.2",
        message_count_by_role={"assistant": 1},
        total_input_tokens=10,
        total_output_tokens=5,
        total_tokens=15,
        has_tool_messages=False,
        failure_stage="assistant_response",
        normalized_error_fingerprint="timeouterror model response exceeded <num> seconds",
        normalized_error_hash="abc123",
        exact_error_hash="def456",
        report_generated_at=generated_at,
    )
    return ErrorReport(
        metadata=ErrorReportMetadata(report_id="03966512_20260619_T150000Z", generated_at=generated_at),
        failure=ErrorReportFailure(
            conversation_id=conversation.conversation_id,
            error_message="TimeoutError: model response exceeded 30 seconds",
            error_type="TimeoutError",
            error_source="co_pqrs_back_agent",
            reported_at=generated_at,
            trace_id="trace-1",
            tags=["llm", "timeout"],
        ),
        analytics=analytics,
        conversation_snapshot=snapshot,
    )


class MinioSettingsTests(unittest.TestCase):
    def test_defaults_disabled(self) -> None:
        for key in (
            "MINIO_ENABLED",
            "MINIO_ENDPOINT_URL",
            "MINIO_BUCKET",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
        ):
            os.environ.pop(key, None)
        settings = load_minio_settings()
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.region, "us-east-1")
        self.assertEqual(settings.addressing_style, "path")

    def test_enabled_from_env(self) -> None:
        os.environ["MINIO_ENABLED"] = "true"
        os.environ["MINIO_BUCKET"] = "audit-logs"
        os.environ["MINIO_ENDPOINT_URL"] = "http://minio.pqr-genai-dev.svc.cluster.local:9000"
        try:
            settings = load_minio_settings()
            self.assertTrue(settings.enabled)
            self.assertEqual(settings.bucket, "audit-logs")
        finally:
            for key in ("MINIO_ENABLED", "MINIO_BUCKET", "MINIO_ENDPOINT_URL"):
                os.environ.pop(key, None)


class ObjectStoreTests(unittest.TestCase):
    def test_write_json_and_idempotency(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)

            self.assertTrue(store.write_json("error-reports/dt=2026-06-19/r.json", {"a": 1}))
            self.assertFalse(store.write_json("error-reports/dt=2026-06-19/r.json", {"a": 2}))

            body = client.get_object(Bucket=BUCKET, Key="error-reports/dt=2026-06-19/r.json")["Body"].read()
            self.assertEqual(json.loads(body), {"a": 1})

    def test_requires_bucket(self) -> None:
        with self.assertRaises(ValueError):
            ObjectStore(MinioSettings(enabled=True, bucket=None), client=object())


class WriterMinioTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_report_to_minio(self) -> None:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=BUCKET)
            store = ObjectStore(_minio_settings(), client=client)
            writer = ErrorReportWriter(
                settings=None,
                minio_settings=_minio_settings(),
                object_store=store,
            )

            key_path = await writer.write_report(_sample_report())

            self.assertEqual(
                str(key_path),
                "error-reports/dt=2026-06-19/03966512_20260619_T150000Z.json",
            )
            raw = client.get_object(Bucket=BUCKET, Key=str(key_path))["Body"].read()
            self.assertEqual(json.loads(raw)["failure"]["error_type"], "TimeoutError")

            summary = client.get_object(
                Bucket=BUCKET,
                Key="error-summaries/dt=2026-06-19/03966512_20260619_T150000Z.json",
            )["Body"].read().decode().strip()
            record = json.loads(summary)
            self.assertEqual(record["workflow"], "Riesgo")
            self.assertEqual(record["normalized_error_hash"], "abc123")


if __name__ == "__main__":
    unittest.main()
