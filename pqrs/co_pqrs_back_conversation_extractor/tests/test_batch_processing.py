"""Tests para procesamiento por lotes con deduplicación."""

import pytest
from unittest.mock import MagicMock, patch
import json
import logging
from datetime import date


def test_deduplication_skips_existing_ids():
    """Test deduplicación: omite conversation_ids existentes."""
    from main import process_conversations_batch, Settings
    
    logger = logging.getLogger(__name__)
    
    settings = Settings(
        minio_endpoint_url="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )
    
    # Set con IDs ya procesados
    existing_conv_ids = {"09690295_20260728"}
    
    # Mock S3 client que retorna conversación con ID duplicado
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = []
    
    result = process_conversations_batch(
        mock_client,
        settings,
        existing_conv_ids,
        logger
    )
    
    assert result["rows"] == []
    assert result["duplicates"] == 0  # No se encontró en este batch


def test_process_batch_reads_maintenance_export_prefix():
    """Test que procesa exports archivados bajo conversations/."""
    from main import process_conversations_batch, Settings

    logger = logging.getLogger(__name__)

    settings = Settings(
        minio_endpoint_url="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )

    payload = {
        "metadata": {
            "conversation_id": "09690295_20260728",
            "satisfaction_status": "positive",
            "closed_at": "2026-07-28T15:30:45Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
            }
        },
        "messages": [
            {
                "_source": {
                    "role": "agent",
                    "content": "Hola",
                },
                "timing": {
                    "responded_at": "2026-07-28T15:30:00Z",
                },
            }
        ],
    }

    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "conversations/09690295_20260728/2026/07/28/09690295_20260728_20260728T153045Z.json",
                }
            ]
        }
    ]
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=json.dumps(payload).encode("utf-8")))
    }

    result = process_conversations_batch(
        mock_client,
        settings,
        set(),
        date(2026, 7, 28),
        logger,
    )

    assert len(result["rows"]) == 1
    assert result["duplicates"] == 0
    assert result["errors"] == 0
    assert result["rows"][0]["CLIENTE"] == "09690295"


def test_process_batch_skips_old_conversations_outside_window():
    """Test que omite conversaciones fuera de la ventana reciente."""
    from main import process_conversations_batch, Settings

    logger = logging.getLogger(__name__)

    settings = Settings(
        minio_endpoint_url="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        scan_lookback_days=0,
        min_scan_date="20260730",
    )

    payload = {
        "metadata": {
            "conversation_id": "09690295_20260728",
            "satisfaction_status": "positive",
            "closed_at": "2026-07-28T15:30:45Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
            }
        },
        "messages": [
            {
                "_source": {
                    "role": "agent",
                    "content": "Hola",
                },
                "timing": {
                    "responded_at": "2026-07-28T15:30:00Z",
                },
            }
        ],
    }

    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "conversations/09690295_20260728/2026/07/28/09690295_20260728_20260728T153045Z.json",
                }
            ]
        }
    ]
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=json.dumps(payload).encode("utf-8")))
    }

    result = process_conversations_batch(
        mock_client,
        settings,
        set(),
        date(2026, 7, 30),
        logger,
    )

    assert result["rows"] == []
    assert result["duplicates"] == 0
    assert result["out_of_window"] == 1
    assert result["errors"] == 0


def test_process_batch_keeps_multiple_same_day_conversations_for_customer():
    """Test que conserva múltiples conversaciones del mismo cliente en el mismo día."""
    from main import process_conversations_batch, Settings

    logger = logging.getLogger(__name__)

    settings = Settings(
        minio_endpoint_url="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )

    first_payload = {
        "metadata": {
            "conversation_id": "09690295_20260730",
            "satisfaction_status": "positive",
            "closed_at": "2026-07-30T20:10:04Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
            }
        },
        "messages": [
            {
                "_source": {
                    "role": "agent",
                    "content": "Primera conversación",
                },
                "timing": {
                    "responded_at": "2026-07-30T20:10:04Z",
                },
            }
        ],
    }

    second_payload = {
        "metadata": {
            "conversation_id": "09690295_20260730",
            "satisfaction_status": "neutral",
            "closed_at": "2026-07-30T21:17:58Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
            }
        },
        "messages": [
            {
                "_source": {
                    "role": "agent",
                    "content": "Segunda conversación",
                },
                "timing": {
                    "responded_at": "2026-07-30T21:17:58Z",
                },
            }
        ],
    }

    payload_by_key = {
        "conversations/09690295_20260730/2026/07/30/09690295_20260730_20260730T201004Z.json": first_payload,
        "conversations/09690295_20260730/2026/07/30/09690295_20260730_20260730T211758Z.json": second_payload,
    }

    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": key}
                for key in payload_by_key
            ]
        }
    ]

    def get_object_side_effect(*, Bucket, Key):
        payload = payload_by_key[Key]
        return {
            "Body": MagicMock(
                read=MagicMock(return_value=json.dumps(payload).encode("utf-8"))
            )
        }

    mock_client.get_object.side_effect = get_object_side_effect

    result = process_conversations_batch(
        mock_client,
        settings,
        set(),
        date(2026, 7, 30),
        logger,
    )

    assert len(result["rows"]) == 2
    assert result["duplicates"] == 0
    assert result["errors"] == 0
    assert {
        row["_CONV_ID"] for row in result["rows"]
    } == {
        "09690295_20260730_20260730T201004Z",
        "09690295_20260730_20260730T211758Z",
    }


def test_save_or_append_excel_creates_new_file(temp_output_folder):
    """Test guardar Excel: crea archivo nuevo."""
    from main import save_or_append_excel
    
    logger = logging.getLogger(__name__)
    
    rows = [
        {
            "FECHA": "2026-07-28",
            "CLIENTE": "09690295",
            "FEEDBACK": "positive",
            "CONVERSACION": "agent: Hola",
            "timestamp": "2026-07-28T15:30:45Z",
            "_CONV_ID": "09690295_20260728",
        }
    ]
    
    save_or_append_excel(
        temp_output_folder,
        "20260728",
        rows,
        logger
    )
    
    excel_path = temp_output_folder / "conversaciones_20260728.xlsx"
    assert excel_path.exists()


def test_save_or_append_excel_appends_to_existing(temp_output_folder):
    """Test guardar Excel: agrega a archivo existente."""
    from main import save_or_append_excel
    import pandas as pd
    
    logger = logging.getLogger(__name__)
    
    # Crear Excel inicial
    excel_path = temp_output_folder / "conversaciones_20260728.xlsx"
    initial_data = {
        "FECHA": ["2026-07-28"],
        "CLIENTE": ["12345678"],
        "FEEDBACK": ["neutral"],
        "CONVERSACION": ["initial"],
        "timestamp": ["2026-07-28T10:00:00Z"],
        "_CONV_ID": ["12345678_20260728"],
    }
    df = pd.DataFrame(initial_data)
    df.to_excel(excel_path, index=False, engine="openpyxl")
    
    # Agregar nuevas filas
    new_rows = [
        {
            "FECHA": "2026-07-28",
            "CLIENTE": "09690295",
            "FEEDBACK": "positive",
            "CONVERSACION": "agent: Hola",
            "timestamp": "2026-07-28T15:30:45Z",
            "_CONV_ID": "09690295_20260728",
        }
    ]
    
    save_or_append_excel(
        temp_output_folder,
        "20260728",
        new_rows,
        logger
    )
    
    # Verificar que tiene ambas filas
    df_result = pd.read_excel(excel_path, engine="openpyxl")
    assert len(df_result) == 2
    assert "12345678" in df_result["CLIENTE"].values
    assert "09690295" in df_result["CLIENTE"].values


def test_save_or_append_excel_empty_rows(temp_output_folder):
    """Test guardar Excel con lista vacía de filas."""
    from main import save_or_append_excel
    
    logger = logging.getLogger(__name__)
    
    save_or_append_excel(
        temp_output_folder,
        "20260728",
        [],
        logger
    )
    
    excel_path = temp_output_folder / "conversaciones_20260728.xlsx"
    assert not excel_path.exists()
