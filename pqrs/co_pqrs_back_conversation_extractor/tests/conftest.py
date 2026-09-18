"""Configuración y fixtures para tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_minio_client():
    """Mock cliente MinIO para tests."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_conversation_json():
    """Conversación JSON de ejemplo para tests."""
    return {
        "metadata": {
            "conversation_id": "09690295_20260728",
            "satisfaction_status": "positive",
            "closed_at": "2026-07-28T15:30:45Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
                "satisfaction_status": "ENTERED",
                "satisfaction_result": True,
            }
        },
        "messages": [
            {
                "_source": {
                    "role": "agent",
                    "content": "Hola, ¿cómo te puedo ayudar?",
                    "timing": {
                        "received_at": "2026-07-28T15:30:00Z",
                        "responded_at": "2026-07-28T15:30:10Z",
                    },
                },
            },
            {
                "_source": {
                    "role": "client",
                    "content": "Buenos días, necesito ayuda",
                    "timing": {
                        "received_at": "2026-07-28T15:29:30Z",
                        "responded_at": "2026-07-28T15:30:30Z",
                    },
                },
            }
        ]
    }


@pytest.fixture
def sample_conversation_with_null_values():
    """Conversación con valores NULL para tests."""
    return {
        "metadata": {
            "conversation_id": "12345678_20260728",
            "satisfaction_status": None,
            "closed_at": None,
        },
        "conversation": {
            "_source": {
                "user_id": None,
                "satisfaction_status": None,
                "satisfaction_result": None,
            }
        },
        "messages": []
    }


@pytest.fixture
def sample_minio_path():
    """Ruta MinIO de ejemplo."""
    return "conversation/09690295_20260728/2026/07/28/conv_123.json"


@pytest.fixture
def temp_output_folder(tmp_path):
    """Carpeta temporal para output."""
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    return output_folder
