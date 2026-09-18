from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from settings.config import load_settings


REQUIRED_BASE_ENV = {
    "OPENSEARCH_HOSTS": "https://opensearch:9200",
    "OPENSEARCH_USERNAME": "admin",
    "OPENSEARCH_PASSWORD": "secret",
}

MINIO_KEYS = [
    "MINIO_ENABLED",
    "MINIO_ENDPOINT_URL",
    "MINIO_BUCKET",
    "MINIO_REGION",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_ADDRESSING_STYLE",
    "OPENSEARCH_CONTROL_INDEX",
    "CONTROL_INDEX",
]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # dotenv may load a local .env; make sure it does not interfere.
    monkeypatch.setattr("settings.config.load_dotenv", lambda *a, **k: None)
    for key in MINIO_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED_BASE_ENV.items():
        monkeypatch.setenv(key, value)
    yield


def test_minio_defaults_disabled(clean_env: None) -> None:
    settings = load_settings()

    assert settings.minio_enabled is False
    assert settings.minio_endpoint_url is None
    assert settings.minio_bucket is None
    assert settings.minio_region == "us-east-1"
    assert settings.minio_access_key is None
    assert settings.minio_secret_key is None
    assert settings.minio_addressing_style == "path"
    assert settings.control_index == "client-control-table"


def test_minio_enabled_full_config(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_ENABLED", "true")
    monkeypatch.setenv(
        "MINIO_ENDPOINT_URL",
        "http://minio.pqr-genai-dev.svc.cluster.local:9000",
    )
    monkeypatch.setenv("MINIO_BUCKET", "pqr-conversations-history")
    monkeypatch.setenv("MINIO_REGION", "us-east-1")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "admin")
    monkeypatch.setenv("MINIO_SECRET_KEY", "topsecret")

    settings = load_settings()

    assert settings.minio_enabled is True
    assert settings.minio_endpoint_url == "http://minio.pqr-genai-dev.svc.cluster.local:9000"
    assert settings.minio_bucket == "pqr-conversations-history"
    assert settings.minio_access_key == "admin"
    assert settings.minio_secret_key == "topsecret"
    assert settings.minio_addressing_style == "path"


def test_control_index_override(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_CONTROL_INDEX", "custom-control")
    settings = load_settings()
    assert settings.control_index == "custom-control"


def test_minio_enabled_blank_values_become_none(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINIO_ENABLED", "false")
    monkeypatch.setenv("MINIO_ENDPOINT_URL", "   ")
    monkeypatch.setenv("MINIO_BUCKET", "")

    settings = load_settings()

    assert settings.minio_enabled is False
    assert settings.minio_endpoint_url is None
    assert settings.minio_bucket is None
