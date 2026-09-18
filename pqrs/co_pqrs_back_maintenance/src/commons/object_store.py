"""MinIO (S3-compatible) object storage client used to persist exports durably.

MinIO speaks the S3 protocol, so this uses the boto3 ``s3`` client pointed at the
MinIO ``endpoint_url``. There is no real AWS S3 involved. Path-style addressing is
used because MinIO does not support virtual-host-style buckets by default.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from classes.models import Settings
from commons.logging_utils import get_logger


logger = get_logger(__name__)


class ObjectStore:
    """Write JSON / NDJSON objects to a MinIO bucket, idempotently."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        if not settings.minio_bucket:
            raise ValueError("MINIO_BUCKET must be configured to use the object store")

        self._bucket = settings.minio_bucket
        self._client = client or self._build_client(settings)

    @staticmethod
    def _build_client(settings: Settings) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.minio_addressing_style},
            ),
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def object_exists(self, key: str) -> bool:
        """Return True if an object already exists at the given key."""

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def write_json(self, key: str, payload: dict[str, Any], *, overwrite: bool = False) -> bool:
        """Write a JSON object to the bucket.

        Idempotent by default: if an object already exists at ``key`` it is not
        re-uploaded. Returns True when an object was written, False when skipped.
        """

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
        """Write newline-delimited JSON (one record per line) to the bucket.

        Idempotent by default like :meth:`write_json`.
        """

        if not overwrite and self.object_exists(key):
            logger.info("NDJSON object already exists, skipping upload key=%s", key)
            return False

        lines = [json.dumps(record, ensure_ascii=False) for record in records]
        body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        self._put(key, body, content_type="application/x-ndjson")
        logger.info("Wrote NDJSON object key=%s records=%s bytes=%s", key, len(lines), len(body))
        return True

    def _put(self, key: str, body: bytes, *, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
