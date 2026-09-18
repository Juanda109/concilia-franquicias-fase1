"""El volcado de depuracion del ASO en back_data sale enmascarado (KYNS IT 3)."""

import json

from infrastructure.persistence import commercial_info_client as cic

PAN = "4912684136504818"


def test_mask_text_hides_pan_and_emails_but_keeps_ids():
    text = json.dumps({"contracts": [{"id": PAN, "formats": [{"number": "4912 6841 3650 4818"}]}],
                       "email": "cliente@bbva.com", "customer": "1013634960"})
    out = cic._mask_text(text)
    assert PAN not in out and "4912 6841 3650 4818" not in out
    assert "4818" in out and "1013634960" in out and "cliente@bbva.com" not in out


def test_safe_headers_drop_credentials():
    class R:
        headers = {"content-type": "application/json", "tsec": "TOKEN", "set-cookie": "x", "date": "hoy"}
    assert cic._safe_headers(R()) == {"content-type": "application/json", "date": "hoy"}
    assert cic._safe_headers(None) == {}


def test_mask_text_keeps_bank_contract_numbers():
    for contract in ("1300019600000058", "001300019600000058"):
        assert cic._mask_text(f"contrato {contract}") == f"contrato {contract}"
