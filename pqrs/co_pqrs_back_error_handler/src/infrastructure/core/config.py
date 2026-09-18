"""Environment-backed application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field


class OpenSearchSettings(BaseModel):
    """OpenSearch connection parameters."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    endpoint: str
    user: str
    password: str
    verify_ssl: bool = False
    conversations_index: str = "conversations-reference"
    messages_index: str = "conversations-messages"
    timeout: float = Field(default=10.0, ge=1.0)


class ReportStorageSettings(BaseModel):
    """Filesystem output configuration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    output_dir: Path
    file_prefix: str = "error_report"


class MinioSettings(BaseModel):
    """MinIO (S3-compatible) object storage configuration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = False
    endpoint_url: str | None = None
    bucket: str | None = None
    region: str = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None
    addressing_style: str = "path"


def load_env_constants(
    env_path: str | Path = ".env",
    required_keys: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Merge optional `.env` variables with process environment variables."""

    resolved_env_path = _resolve_env_path(env_path)
    file_constants: dict[str, str] = {}

    if resolved_env_path is not None:
        file_constants = {
            key: value
            for key, value in dotenv_values(resolved_env_path).items()
            if value is not None
        }

    constants = {
        **file_constants,
        **{key: value for key, value in os.environ.items() if value is not None},
    }

    if required_keys:
        missing_keys = [key for key in required_keys if key not in constants]
        if missing_keys:
            missing_keys.sort()
            missing_text = ", ".join(missing_keys)
            raise ValueError(f"Missing required environment variables: {missing_text}")
        return {key: constants[key] for key in required_keys}

    return constants


def load_opensearch_settings(env_path: str | Path = ".env") -> OpenSearchSettings:
    """Load OpenSearch settings with sensible local defaults."""

    constants = load_env_constants(env_path)
    return OpenSearchSettings(
        endpoint=constants.get("OPENSEARCH_ENDPOINT", "https://localhost:9200"),
        user=constants.get("OPENSEARCH_USER", "admin"),
        password=constants.get("OPENSEARCH_PASSWORD", "admin"),
        verify_ssl=_parse_bool(constants.get("OPENSEARCH_VERIFY_SSL"), default=False),
        conversations_index=constants.get(
            "OPENSEARCH_CONVERSATIONS_INDEX",
            "conversations-reference",
        ),
        messages_index=constants.get(
            "OPENSEARCH_MESSAGES_INDEX",
            "conversations-messages",
        ),
        timeout=float(constants.get("OPENSEARCH_TIMEOUT", "10")),
    )


def load_report_storage_settings(
    env_path: str | Path = ".env",
) -> ReportStorageSettings:
    """Load the directory where JSON reports are exported."""

    constants = load_env_constants(env_path)
    output_dir = _resolve_project_path(
        constants.get("ERROR_REPORT_OUTPUT_DIR", "data/error_reports")
    )
    return ReportStorageSettings(
        output_dir=output_dir,
        file_prefix=constants.get("ERROR_REPORT_FILE_PREFIX", "error_report"),
    )


def load_minio_settings(env_path: str | Path = ".env") -> MinioSettings:
    """Load MinIO object-storage settings used to persist reports durably."""

    constants = load_env_constants(env_path)
    return MinioSettings(
        enabled=_parse_bool(constants.get("MINIO_ENABLED"), default=False),
        endpoint_url=(constants.get("MINIO_ENDPOINT_URL") or "").strip() or None,
        bucket=(constants.get("MINIO_BUCKET") or "").strip() or None,
        region=constants.get("MINIO_REGION", "us-east-1"),
        access_key=(constants.get("MINIO_ACCESS_KEY") or "").strip() or None,
        secret_key=(constants.get("MINIO_SECRET_KEY") or "").strip() or None,
        addressing_style=constants.get("MINIO_ADDRESSING_STYLE", "path"),
    )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def _resolve_env_path(env_path: str | Path) -> Path | None:
    path = Path(env_path).expanduser()
    if path.is_absolute() and path.exists():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    project_candidate = _project_root() / path
    if project_candidate.exists():
        return project_candidate

    return None


def _resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return (_project_root() / path).resolve()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]
