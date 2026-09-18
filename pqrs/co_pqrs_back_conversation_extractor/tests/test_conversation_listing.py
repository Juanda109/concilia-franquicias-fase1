"""Tests para listado de conversaciones desde MinIO."""

import pytest
from unittest.mock import MagicMock


def test_parse_minio_path_valid(sample_minio_path):
    """Test parseo de ruta MinIO válida."""
    from main import parse_minio_path
    import logging
    
    logger = logging.getLogger(__name__)
    
    result = parse_minio_path(sample_minio_path, logger)
    
    assert result["customer_id"] == "09690295"
    assert result["date_str"] == "20260728"
    assert result["year"] == "2026"
    assert result["month"] == "07"
    assert result["day"] == "28"


def test_parse_minio_path_invalid_format():
    """Test parseo de ruta MinIO con formato inválido."""
    from main import parse_minio_path
    import logging
    
    logger = logging.getLogger(__name__)
    
    with pytest.raises(ValueError):
        parse_minio_path("invalid/path", logger)


def test_parse_minio_path_invalid_date():
    """Test parseo de ruta MinIO con fecha inválida."""
    from main import parse_minio_path
    import logging
    
    logger = logging.getLogger(__name__)
    
    with pytest.raises(ValueError):
        parse_minio_path("conversation/12345678_abcdefgh/2026/07/28/file.json", logger)


def test_build_archive_object_id_uses_filename_without_extension():
    """Test ID único derivado del nombre del objeto exportado."""
    from main import build_archive_object_id

    key = "conversations/09690295_20260730/2026/07/30/09690295_20260730_20260730T211758Z.json"

    result = build_archive_object_id(key)

    assert result == "09690295_20260730_20260730T211758Z"


def test_load_existing_conversation_ids_no_file(temp_output_folder):
    """Test cargar conversation_ids cuando no existe archivo."""
    from main import load_existing_conversation_ids
    from pathlib import Path
    import logging
    
    logger = logging.getLogger(__name__)
    excel_path = temp_output_folder / "conversaciones_20260728.xlsx"
    
    result = load_existing_conversation_ids(excel_path, logger)
    
    assert result == set()


def test_load_existing_conversation_ids_from_file(temp_output_folder):
    """Test cargar conversation_ids desde archivo existente."""
    from main import load_existing_conversation_ids
    from pathlib import Path
    import pandas as pd
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Crear Excel con datos
    excel_path = temp_output_folder / "conversaciones_20260728.xlsx"
    data = {
        "FECHA": ["2026-07-28"],
        "CLIENTE": ["09690295"],
        "FEEDBACK": ["positive"],
        "CONVERSACION": ["agent: Hola"],
        "timestamp": ["2026-07-28T15:30:45Z"],
        "_CONV_ID": ["09690295_20260728"],
    }
    df = pd.DataFrame(data)
    df.to_excel(excel_path, index=False, engine="openpyxl")
    
    result = load_existing_conversation_ids(excel_path, logger)
    
    assert "09690295_20260728" in result
    assert len(result) == 1
