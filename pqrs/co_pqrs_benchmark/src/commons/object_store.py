"""MinIO (S3-compatible) object storage client used to persist exports durably.

MinIO speaks the S3 protocol, so this uses the boto3 ``s3`` client pointed at the
MinIO ``endpoint_url``. There is no real AWS S3 involved. Path-style addressing is
used because MinIO does not support virtual-host-style buckets by default.
"""

from __future__ import annotations

import os
import json
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.classes.models import Settings
from src.commons.logging_utils import get_logger


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

    def exists(self, key: str) -> bool:
        """Return True if an object already exists at the given key."""

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    # Alias retrocompatible (el nombre canónico es `exists`).
    def object_exists(self, key: str) -> bool:
        return self.exists(key)

    def read_json(self, key: str) -> Any:
        """Read a JSON file directly from MinIO into Python memory."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            data = json.loads(content)
            print(f"File {key} successfully loaded into memory from MinIO.")
            return data
        except Exception as e:
            print(f"Error loading {key} from MinIO: {e}")
            return None

    def upload_file(self, file_path: str, key: str, *, content_type: str = "application/json") -> bool:
        """Uploads a local physical file to the MinIO bucket."""
        if not os.path.exists(file_path):
            print(f"The file {file_path} does not exist; skipping upload to MinIO.")
            return False

        try:
            with open(file_path, "rb") as f:
                self._put(key, f.read(), content_type=content_type)
            print(f"File successfully exported to MinIO at path: {key}")
            return True
        except Exception as e:
            print(f"Error uploading to MinIO: {e}")
            return False

    def write_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str = "application/json",
    ) -> bool:
        """Escribe bytes en memoria directamente al bucket (sin archivo local).

        Lo usa el benchmark para subir el NDJSON de salida generado en memoria.
        """

        try:
            self._put(key, data, content_type=content_type)
            print(f"Object successfully written to MinIO at path: {key}")
            return True
        except Exception as e:  # noqa: BLE001 - se reporta y se propaga como False
            print(f"Error writing {key} to MinIO: {e}")
            raise

    def _put(self, key: str, body: bytes, *, content_type: str) -> None:
        """Internal method to place the object in the bucket."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )