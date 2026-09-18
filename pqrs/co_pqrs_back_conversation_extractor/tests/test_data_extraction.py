"""Tests para extracción y transformación de datos JSON."""

import json
import pytest
import logging


def test_parse_json_conversation_valid(sample_conversation_json):
    """Test parseo de conversación JSON válida."""
    from main import parse_json_conversation
    
    logger = logging.getLogger(__name__)
    json_str = json.dumps(sample_conversation_json)
    
    result = parse_json_conversation(
        json_str,
        "09690295_20260728",
        "09690295",
        "20260728",
        logger
    )
    
    assert result is not None
    assert result["FECHA"] == "2026-07-28"
    assert result["CLIENTE"] == "09690295"
    assert result["FEEDBACK"] == "positive"
    assert result["_CONV_ID"] == "09690295_20260728"
    assert result["CONVERSACION"].splitlines()[0] == "client: Buenos días, necesito ayuda"


def test_parse_json_conversation_feedback_from_conversation_source():
    """Test feedback derivado de satisfaction_result cuando metadata no lo trae."""
    from main import parse_json_conversation

    logger = logging.getLogger(__name__)
    payload = {
        "metadata": {
            "conversation_id": "09690295_20260728",
            "closed_at": "2026-07-28T15:30:45Z",
        },
        "conversation": {
            "_source": {
                "user_id": "09690295",
                "satisfaction_status": "ENTERED",
                "satisfaction_result": True,
            }
        },
        "messages": [],
    }

    result = parse_json_conversation(
        json.dumps(payload),
        "09690295_20260728_20260728T153045Z",
        "09690295",
        "20260728",
        logger,
    )

    assert result is not None
    assert result["FEEDBACK"] == "positive"


def test_parse_json_conversation_with_null_values(
    sample_conversation_with_null_values
):
    """Test parseo de conversación con valores NULL."""
    from main import parse_json_conversation
    
    logger = logging.getLogger(__name__)
    json_str = json.dumps(sample_conversation_with_null_values)
    
    result = parse_json_conversation(
        json_str,
        "12345678_20260728",
        "12345678",
        "20260728",
        logger
    )
    
    assert result is not None
    assert result["CLIENTE"] == "SIN_DATO"
    assert result["FEEDBACK"] == "SIN_DATO"
    assert result["CONVERSACION"] == "SKIP"
    assert result["timestamp"] == "SIN_DATO"


def test_parse_json_conversation_invalid_json():
    """Test parseo de JSON inválido."""
    from main import parse_json_conversation
    
    logger = logging.getLogger(__name__)
    
    result = parse_json_conversation(
        "invalid json",
        "12345678_20260728",
        "12345678",
        "20260728",
        logger
    )
    
    assert result is None


def test_process_messages_valid():
    """Test procesamiento de mensajes válidos."""
    from main import process_messages
    
    logger = logging.getLogger(__name__)
    
    messages = [
        {
            "_source": {
                "role": "agent",
                "content": "Hola",
                "timing": {
                    "received_at": "2026-07-28T15:30:30Z",
                    "responded_at": "2026-07-28T15:31:00Z",
                },
            },
        },
        {
            "_source": {
                "role": "client",
                "content": "Buenos días",
                "timing": {
                    "received_at": "2026-07-28T15:30:00Z",
                    "responded_at": "2026-07-28T15:30:30Z",
                },
            },
        }
    ]
    
    result = process_messages(messages, logger)
    
    assert result.splitlines() == [
        "client: Buenos días",
        "agent: Hola",
    ]


def test_process_messages_empty():
    """Test procesamiento de array de mensajes vacío."""
    from main import process_messages
    
    logger = logging.getLogger(__name__)
    
    result = process_messages([], logger)
    
    assert result == "SKIP"


def test_process_messages_invalid_format():
    """Test procesamiento de mensajes con formato inválido."""
    from main import process_messages
    
    logger = logging.getLogger(__name__)
    
    messages = [
        {
            "_source": {},
            "timing": {}
        }
    ]
    
    result = process_messages(messages, logger)
    
    assert result == "SKIP"
