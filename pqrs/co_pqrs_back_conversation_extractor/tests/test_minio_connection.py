"""Tests para conexión a MinIO."""

import pytest
from unittest.mock import patch, MagicMock


def test_create_minio_client_with_valid_credentials():
    """Test creación de cliente MinIO con credenciales válidas."""
    from main import create_minio_client, Settings
    
    settings = Settings(
        minio_endpoint_url="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )
    
    with patch("main.boto3.client") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        
        client = create_minio_client(settings)
        
        assert client is not None
        mock_boto3.assert_called_once()
        call_kwargs = mock_boto3.call_args[1]
        assert call_kwargs["endpoint_url"] == "http://localhost:9000"
        assert call_kwargs["aws_access_key_id"] == "minioadmin"


def test_settings_from_env_with_defaults(monkeypatch):
    """Test cargar Settings desde env con valores por defecto."""
    from main import Settings
    
    monkeypatch.delenv("MINIO_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    
    settings = Settings.from_env()
    
    assert settings.minio_endpoint_url == "http://localhost:9000"
    assert settings.minio_access_key == "minioadmin"
    assert settings.minio_bucket == "pqr-conversations-history"


def test_settings_from_env_with_custom_values(monkeypatch):
    """Test cargar Settings desde env con valores personalizados."""
    from main import Settings
    
    monkeypatch.setenv("MINIO_ENDPOINT_URL", "http://minio.prod:9000")
    monkeypatch.setenv("MINIO_BUCKET", "custom-bucket")
    
    settings = Settings.from_env()
    
    assert settings.minio_endpoint_url == "http://minio.prod:9000"
    assert settings.minio_bucket == "custom-bucket"
