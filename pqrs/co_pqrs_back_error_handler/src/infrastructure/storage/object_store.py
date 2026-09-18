"""MinIO (S3-compatible) object storage client for durable error reports.

MinIO speaks the S3 protocol, so this uses the boto3 ``s3`` client pointed at
the MinIO ``endpoint_url`` with path-style addressing. No real AWS S3 is used.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from infrastructure.core.config import MinioSettings
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)


class ObjectStore:
    """Write JSON / NDJSON objects to a MinIO bucket, idempotently."""

    def __init__(self, settings: MinioSettings, *, client: Any | None = None) -> None:
        if not settings.bucket:
            raise ValueError("MINIO_BUCKET must be configured to use the object store")

        self._bucket = settings.bucket
        self._client = client or self._build_client(settings)

    @staticmethod
    def _build_client(settings: MinioSettings) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.addressing_style},
            ),
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def write_json(self, key: str, payload: dict[str, Any], *, overwrite: bool = False) -> bool:
        if not overwrite and self.object_exists(key):
            logger.info("Object already exists, skipping upload key=%s", key)
            return False

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._put(key, body, content_type="application/json")
        logger.info("Wrote JSON object key=%s bytes=%s", key, len(body))
        return True

    def write_ndjson(
        self,
        key: str,
        records: Iterable[dict[str, Any]],
        *,
        overwrite: bool = False,
    ) -> bool:
        if not overwrite and self.object_exists(key):
            logger.info("NDJSON object already exists, skipping upload key=%s", key)
            return False

        lines = [json.dumps(record, ensure_ascii=False) for record in records]
        body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        self._put(key, body, content_type="application/x-ndjson")
        logger.info("Wrote NDJSON object key=%s records=%s bytes=%s", key, len(lines), len(body))
        return True

    def write_text(
        self,
        key: str,
        text: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        overwrite: bool = True,
    ) -> bool:
        """Write a plain-text object (e.g. a per-request log capture)."""

        if not overwrite and self.object_exists(key):
            logger.info("Text object already exists, skipping upload key=%s", key)
            return False

        body = text.encode("utf-8")
        self._put(key, body, content_type=content_type)
        logger.info("Wrote text object key=%s bytes=%s", key, len(body))
        return True

    def _put(self, key: str, body: bytes, *, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
