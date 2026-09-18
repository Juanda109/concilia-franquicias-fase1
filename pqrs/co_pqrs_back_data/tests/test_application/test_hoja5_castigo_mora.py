"""Matriz de comportamiento esperado (Hoja 5 - E2E CENTRALES DE RIESGO).

Valida, con el codigo real, que para el subflujo ACTIVO (castigo/mora) cada
combinacion de (vector 24m, default_flag, written_off_flag) produce el id_msg
esperado:

  - Mora <= 120 dias (<= 4 meses)          -> id_msg 4
  - Mora  > 120 dias  ( > 4 meses)          -> id_msg 20
  - Castigo (C en vector) + written_off     -> id_msg 20 (siempre)
  - Discrepancia centrales <-> flags BBVA   -> id_msg 99 (Formulario PQRS)
  - Sin reporte y sin flags                 -> id_msg 1
"""

import pandas as pd
import pytest

from application.customer.consultar_service import (
    build_data_from_customer_df_and_centrales,
    read_json_centrales,
)

# Columnas del origen postgres (ada_info_detail). Se rellenan con valores
# neutros y cada caso solo sobreescribe las flags relevantes.
_COLUMNS = [
    "key_id", "contract_id", "commercial_product_id", "commercial_subproduct_id",
    "contract_register_date", "account_status_type", "account_status_type_desc",
    "blocking_type", "blocking_type_desc", "account_freeze_type",
    "contract_status_date", "contract_status_type", "contract_status_type_desc",
    "card_bin_number", "card_bin_subtype_type", "contract_end_date",
    "participant_type", "participation_order_number", "card_status_type",
    "card_status_date", "last_four_pan_id", "origin_flag", "customer_id",
    "personal_id", "personal_type", "personal_verif_digit_type", "customer_name",
    "customer_mail", "personal_type_desc", "commercial_product_desc",
    "commercial_subproduct_desc", "off_loaded_porfolio_date",
    "portfolio_buyer_company_id", "buyer_name", "off_loaded_portfolio_flag",
    "written_off_date", "written_off_end_date", "written_off_flag",
    "default_days_number", "default_date", "default_end_date", "default_flag",
    "default_status_pay", "restructured_flag", "date_consult_risk_ctral",
    "flag_consult_risk_ctral", "adelanto_nomina_flag", "seizure_contract_id",
    "court_order_id", "court_order_entry_date", "seizure_issuing_court_name",
    "seizure_pay_date", "seizure_flag", "seizure_off_flag", "seizure_off_date",
    "seizure_off_desc", "product_desc", "audit_date", "first_last_name",
    "second_last_name",
]


def _make_df(default_flag: str, written_off_flag: str) -> pd.DataFrame:
    row = {c: "NULL" for c in _COLUMNS}
    row.update(
        {
            "key_id": "9999",
            "contract_id": "00130009005000009999",
            "customer_id": "TEST",
            "account_status_type_desc": "ACTIVO",
            "contract_status_type_desc": "ACTIVO",
            "origin_flag": "TDC",
            "commercial_product_desc": "TARJETA DE CREDITO",
            "off_loaded_portfolio_flag": "False",
            "written_off_flag": written_off_flag,
            "default_flag": default_flag,
            "default_days_number": "NULL",
            "default_date": "NULL",
            "restructured_flag": "False",
        }
    )
    return pd.DataFrame([row])


def _make_aso(vector: str) -> dict:
    return {
        "data": {
            "creditHistory": {
                "obligations": [
                    {
                        "number": "9999",
                        "financialInstitutionInformation": {"name": "BBVA"},
                        "classificationStatus": {"id": "MORA"},
                        "behaviorLiabilities": [
                            {
                                "behaviorType": "TWENTY_FOUR_MONTHS",
                                "description": vector,
                            }
                        ],
                    }
                ]
            }
        }
    }


# (vector, default_flag, written_off_flag, id_msg esperado)
_HOJA5_CASES = [
    ("N N N N 1 2 3", "True", "False", 4),
    ("N N N 1 2 3 4", "True", "False", 4),
    ("N N 1 2 3 4 5", "True", "False", 20),
    ("N 1 2 3 4 5 6", "True", "False", 20),
    ("N N N 1 2 3 N", "True", "False", 4),
    ("1 2 3 N N N N", "False", "False", 99),
    ("1 2 3 N N N N", "False", "True", 99),
    ("N N N 1 2 3 4", "False", "False", 99),
    ("1 2 3 4 5 6 C", "True", "True", 20),
    ("2 3 4 5 6 C C", "True", "True", 20),
    ("2 3 4 5 6 6 C", "True", "True", 20),
    ("5 6 C N N N N", "True", "True", 20),
    ("N N N N N N N", "True", "True", 99),
    ("N N N N N N N", "False", "False", 1),
]


@pytest.mark.parametrize("vector,default_flag,written_off_flag,expected", _HOJA5_CASES)
def test_hoja5_activo_castigo_mora_id_msg(vector, default_flag, written_off_flag, expected):
    centrales = read_json_centrales(_make_aso(vector))
    result = build_data_from_customer_df_and_centrales(
        customer_identity_df=_make_df(default_flag, written_off_flag),
        centrales_data=centrales,
        customer_id="TEST",
        embargo_repository=None,
    )
    id_msgs = [
        h.get("id_msg")
        for v in result["validaciones"]
        for h in v.get("hallazgos", [])
    ]
    # Un unico hallazgo por producto.
    assert len(id_msgs) == 1, f"vector={vector!r} produjo {id_msgs}"
    assert id_msgs[0] == expected, f"vector={vector!r} -> {id_msgs[0]} (esperado {expected})"
