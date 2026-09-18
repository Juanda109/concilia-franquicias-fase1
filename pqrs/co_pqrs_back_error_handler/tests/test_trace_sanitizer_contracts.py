"""Regla de PAN del sanitizador: oculta tarjetas, no números de contrato del banco.

La primera versión ocultaba todo número de 16 dígitos y los de 13 a 19 que
pasaran Luhn, lo que se llevaba por delante los contratos (0013..., 1300...)
que el equipo usa para diagnosticar. Medido sobre los fixtures: 159 de 234.
"""

from domain.trace_event.sanitizer import is_pan, mask_text, sanitize_trace_event


def test_contract_numbers_survive_even_when_they_pass_luhn():
    for contract in ("1300019600000058", "001300019600000058", "00130766000200022384"):
        assert mask_text(contract) == contract
        assert not is_pan(contract)


def test_real_card_shapes_are_still_masked():
    for pan in ("4912684136504818", "4111111111111111", "5555555555554444", "378282246310005"):
        assert mask_text(pan).endswith(pan[-4:]) and pan not in mask_text(pan)
    assert "4912 6841 3650 4818" not in mask_text("tarjeta 4912 6841 3650 4818")


def test_trace_event_keeps_the_contract_and_hides_the_card():
    out = sanitize_trace_event({
        "conversation_id": "1013634960_20260911",
        "request_summary": {"contract_id": "001300019600000058", "pan": "4912684136504818"},
    })
    assert out["request_summary"]["contract_id"] == "001300019600000058"
    assert out["request_summary"]["pan"].endswith("4818") and "4912" not in out["request_summary"]["pan"]
