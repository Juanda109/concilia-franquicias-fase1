import pytest
from datetime import date
from application.chat.workflow_actions import (
    _add_months_to_date,
    _calculate_permanencia_end,
    _build_mora_negative_report_message,
    _extract_current_mora_profile,
    _extract_latest_mora_profile,
    _cross_validate_mora,
    _find_obligation_by_key_id,
    _load_selected_product_central_risk,
)
from domain.conversation.models import Conversation, ConversationStatus
import json

# Mock para la función que extrae el nivel máximo del vector si es necesaria en el test
# Si _get_max_mora_level está en el mismo archivo, el test lo usará naturalmente.

# Mock para la función que extrae el nivel máximo del vector si es necesaria en el test
# Si _get_max_mora_level está en el mismo archivo, el test lo usará naturalmente.

# Mock para la función que extrae el nivel máximo del vector si es necesaria en el test
# Si _get_max_mora_level está en el mismo archivo, el test lo usará naturalmente.

def test_add_months_to_date_positive():
    base_date = date(2026, 7, 21)
    new_date = _add_months_to_date(base_date, 4)
    assert new_date == date(2026, 11, 21)

def test_add_months_to_date_negative():
    base_date = date(2026, 7, 21)
    new_date = _add_months_to_date(base_date, -4)
    assert new_date == date(2026, 3, 21)

def test_add_months_to_date_leap_year():
    base_date = date(2024, 2, 29)
    new_date = _add_months_to_date(base_date, 12)
    assert new_date == date(2025, 2, 28)

def test_calculate_permanencia_end_short_mora():
    mora_months = 10
    payment_date_str = "2024-01-15T00:00:00Z"
    end_date = _calculate_permanencia_end(mora_months, payment_date_str)
    assert end_date == date(2025, 9, 15)

def test_calculate_permanencia_end_long_mora_capped():
    mora_months = 30
    payment_date_str = "2024-01-15"
    end_date = _calculate_permanencia_end(mora_months, payment_date_str)
    assert end_date == date(2028, 1, 15)

def test_calculate_permanencia_end_invalid_date():
    assert _calculate_permanencia_end(10, None) is None
    assert _calculate_permanencia_end(10, "invalid-date") is None

def test_build_mora_negative_report_message_max_level_5_capped(mocker):
    # Simulando que el vector devuelve un nivel 5
    mocker.patch('application.chat.workflow_actions._get_max_mora_level', return_value=5)
    
    product = {
        "product_type": "Tarjeta de Credito",
        "product_id": "1234567890",
        "default_months_number": "30"
    }
    obligation = {
        "classificationStatus": {"id": "MORA"},
        "paymentDate": "2024-01-15"
    }
    
    result = _build_mora_negative_report_message(product, obligation, [])

    assert result["id_msg"] == 20
    assert result["product_type"] == "Tarjeta de Credito"
    assert result["last_four"] == "7890"
    assert result["motivo"] == "mora en el pago de la obligacion"
    assert result["permanencia_desc"] == "4 años"

def test_build_mora_negative_report_message_max_level_4_no_castigo(mocker):
    # Simulando que el vector devuelve un nivel 4
    mocker.patch('application.chat.workflow_actions._get_max_mora_level', return_value=4)

    product = {
        "product_type": "Credito",
        "product_id": "1111",
        "default_months_number": "3"
    }
    obligation = {
        "classificationStatus": {"id": "MORA"}
    }
    
    result = _build_mora_negative_report_message(product, obligation, [])

    assert result["id_msg"] == 4
    assert result["product_type"] == "Credito"
    assert result["last_four"] == "1111"
    assert result["motivo"] == "mora en el pago de la obligacion"
    assert "permanencia_desc" not in result


def test_render_structured_message_aliases_for_id_4(monkeypatch):
    from application.chat.workflow_actions import _render_centrales_structured_message

    payload = {
        "id_msg": 4,
        "product_type": "CARTERA",
        "last_four": "0200",
        "motivo": "mora en tu obligacion",
    }

    text, _option = _render_centrales_structured_message(payload)
    assert "0200" in text
    assert "CARTERA" in text
    assert "pago pendiente" in text.lower()


def test_extract_latest_mora_profile_uses_most_recent_block():
    vector = [
        "N", "N", "1", "2", "N", "N", "1", "2", "3", "4", "5", "6", "6", "N"
    ]
    profile = _extract_latest_mora_profile(vector)

    assert profile["mora_months"] == 7
    assert profile["max_level"] == 6
    assert profile["start_index"] == 6
    assert profile["end_index"] == 12


def test_extract_latest_mora_profile_ignores_restructured_only_symbols():
    vector = ["N", "N", "R", "R", "N"]
    profile = _extract_latest_mora_profile(vector)

    assert profile["mora_months"] == 0
    assert profile["max_level"] == 0


def test_extract_current_mora_profile_requires_trailing_delinquency_block():
    profile = _extract_current_mora_profile(["N", "1", "2", "N"])

    assert profile["mora_months"] == 0
    assert profile["max_level"] == 0


def test_cross_validate_mora_requires_real_delinquency_symbols():
    product = {"product_group": "activo", "default_flag": True}

    assert _cross_validate_mora(product, ["N", "-", "R", "N"]) is False
    assert _cross_validate_mora(product, ["N", "1", "2", "N"]) is True


def test_selected_product_skips_id_msg_dispatch_for_activo_mora_and_renders_permanencia(
    monkeypatch,
):
    conversation = Conversation(
        conversation_id="conv_gap001",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4340-TDC-00001234",
                        "state_dict": {"activo_mora": 210},
                        "hallazgos": [
                            {
                                "tipo": "activo_mora",
                                "valor": "mora",
                                "id_msg": 4,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    monkeypatch.setattr(
        "application.chat.workflow_actions._enrich_product_with_commercial_info",
        lambda _conversation, _selected_product: None,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "tiempo de permanencia" in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )


def test_selected_product_generic_id_msg_with_obligation_vector_gt_120_uses_permanencia(
    monkeypatch,
):
    obligation = {
        "number": 100200,
        "classificationStatus": {"id": "MORA"},
        "paymentDate": "2023-07-14T00:00:00.0-0500",
        "behaviorLiabilities": [
            {
                "behaviorType": "TWENTY_FOUR_MONTHS",
                "description": "- - - - - - - - - - - - - - - N N N 1 2 3 4 5 6",
            }
        ],
    }

    conversation = Conversation(
        conversation_id="conv_gap001_prod",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4350-CAB-000100200",
                        "state_dict": {"activo_mora": 180},
                        "hallazgos": [
                            {
                                "tipo": "producto",
                                "valor": "mora",
                                "id_msg": 4,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    def _fake_enrich(conv, _selected_product):
        conv.captured_data["centrales_riesgo_obligacion_json"] = json.dumps(
            obligation, ensure_ascii=False
        )

    monkeypatch.setattr(
        "application.chat.workflow_actions._enrich_product_with_commercial_info",
        _fake_enrich,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "tiempo de permanencia" in message
    assert "no genera un castigo" not in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )


def test_selected_product_generic_id_msg_without_obligation_uses_id_4_for_le_120(
    monkeypatch,
):
    conversation = Conversation(
        conversation_id="conv_gap001_no_json_le120",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4350-CAB-000100200",
                        "state_dict": {"activo_mora": 90},
                        "hallazgos": [
                            {
                                "tipo": "producto",
                                "valor": "mora",
                                "id_msg": 4,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    monkeypatch.setattr(
        "application.chat.workflow_actions._enrich_product_with_commercial_info",
        lambda _conversation, _selected_product: None,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "no genera un castigo" in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )


def test_selected_product_uses_back_data_vector_for_gt_120_without_obligation(
    monkeypatch,
):
    conversation = Conversation(
        conversation_id="conv_gap001_no_json_gt120",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4350-CAB-000100200",
                        "state_dict": {
                            "activo_mora": {
                                "behavior_vector": [
                                    "-", "-", "-", "-", "-", "-", "-", "-",
                                    "-", "-", "-", "-", "-", "-", "-", "N",
                                    "N", "N", "1", "2", "3", "4", "5", "6"
                                ],
                                "mora_months": 6,
                                "dias_mora": 180,
                            }
                        },
                        "hallazgos": [
                            {
                                "tipo": "activo_mora",
                                "valor": {
                                    "behavior_vector": [
                                        "-", "-", "-", "-", "-", "-", "-", "-",
                                        "-", "-", "-", "-", "-", "-", "-", "N",
                                        "N", "N", "1", "2", "3", "4", "5", "6"
                                    ],
                                    "mora_months": 6,
                                    "dias_mora": 180,
                                },
                                "id_msg": 20,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    monkeypatch.setattr(
        "application.chat.workflow_actions._enrich_product_with_commercial_info",
        lambda _conversation, _selected_product: None,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "tiempo de permanencia" in message
    assert "no genera un castigo" not in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )


def test_selected_product_vector_with_trailing_c_routes_to_permanencia(
    monkeypatch,
):
    vector = [
        "N", "N", "N", "N", "N", "N", "1", "2", "3", "4", "5", "6",
        "6", "6", "6", "6", "6", "6", "6", "6", "6", "C", "C", "C",
    ]

    conversation = Conversation(
        conversation_id="conv_gap001_vector_ccc",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4350-CAB-000998466",
                        "state_dict": {
                            "activo_mora": {
                                "behavior_vector": vector,
                                "mora_months": 18,
                                "dias_mora": 540,
                                "max_level": 7,
                            }
                        },
                        "hallazgos": [
                            {
                                "tipo": "activo_mora",
                                "valor": {
                                    "behavior_vector": vector,
                                    "mora_months": 18,
                                    "dias_mora": 540,
                                    "max_level": 7,
                                },
                                "id_msg": 20,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    monkeypatch.setattr(
        "application.chat.workflow_actions._enrich_product_with_commercial_info",
        lambda _conversation, _selected_product: None,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "tiempo de permanencia" in message
    assert "no genera un castigo" not in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )


def test_find_obligation_by_key_id_matches_composite_product_id():
    obligations = [
        {"number": 999999},
        {"number": 100200, "classificationStatus": {"id": "MORA"}},
    ]

    result = _find_obligation_by_key_id(obligations, "4350-CAB-000100200")
    assert result is not None
    assert int(result["number"]) == 100200


def test_selected_product_with_composite_product_id_enriches_obligation_and_uses_permanencia(
    monkeypatch,
):
    obligations = [
        {
            "number": 100200,
            "classificationStatus": {"id": "MORA"},
            "paymentDate": "2023-07-14T00:00:00.0-0500",
            "behaviorLiabilities": [
                {
                    "behaviorType": "TWENTY_FOUR_MONTHS",
                    "description": "- - - - - - - - - - - - - - - N N N 1 2 3 4 5 6",
                }
            ],
            "productType": {"name": "CARTERA BANCARIA"},
        }
    ]

    conversation = Conversation(
        conversation_id="conv_gap001_prod_composite",
        status=ConversationStatus.ACTIVE,
        current_step="1.4.1.3.1",
        general_workflow="PQRs",
        workflow="centrales_de_riesgo",
        flow_version=1,
        flow_answers={"producto_centrales_de_riesgo": "producto_1"},
        captured_data={
            "centrales_riesgo_back_data_map": json.dumps(
                [
                    {
                        "product_id": "4350-CAB-000100200",
                        "state_dict": {"activo_mora": 180},
                        "hallazgos": [
                            {
                                "tipo": "producto",
                                "valor": "mora",
                                "id_msg": 4,
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            )
        },
        user_id="000000000001",
    )

    monkeypatch.setattr(
        "application.chat.workflow_actions._load_commercial_info_obligations",
        lambda _conversation: obligations,
    )

    _load_selected_product_central_risk(conversation)

    message = conversation.captured_data.get("dynamic_prompt_1.4.1.3.1", "")
    assert "tiempo de permanencia" in message
    assert "no genera un castigo" not in message
    assert conversation.captured_data.get("centrales_riesgo_escenario") == (
        "reporte_negativo_mora_activo"
    )
