"""Ninguna credencial ni PAN en claro en lo que el cliente del ASO manda a las trazas.

Hallazgo KYNS IT 3 (31/08): las trazas en MinIO llevaban la contrasena del
granting, el TSEC completo y el financial-overview integro con el PAN y el
titular. Estos tests fijan que, con CUALQUIER combinacion de flags, eso ya no
sale del emisor.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from infrastructure.persistence import aso_client

PAN = "4912684136504818"
GRANTING_BODY = {
    "authentication": {
        "consumerID": "10000006",
        "authenticationType": "02",
        "userID": "0000123456",
        "authenticationData": [{"idAuthenticationData": "password", "authenticationData": ["SuperSecreta1"]}],
    }
}
FO_BODY = {"data": [{"contracts": [{"id": PAN, "formats": [{"number": PAN}], "holderName": "Fabian Figueroa"}]}]}


def _resp(payload):
    return SimpleNamespace(status_code=200, headers={"content-type": "application/json"},
                           json=lambda: payload, text=json.dumps(payload), content=b"x")


def test_granting_password_is_masked_even_with_the_old_full_flag():
    with patch.dict(os.environ, {"ASO_TRACE_PASSWORD_FULL": "true"}):
        masked = aso_client._mask_password(GRANTING_BODY)
    dumped = json.dumps(masked)
    assert "SuperSecreta1" not in dumped
    assert "oculto" in dumped
    # El resto del body se conserva para el diagnostico.
    assert masked["authentication"]["userID"] == "0000123456"


def test_tsec_never_leaves_the_emitter_even_with_the_old_full_flag():
    tsec = "eyJhbGciOiJIUzI1NiJ9." + "A" * 60 + "=="
    with patch.dict(os.environ, {"ASO_TRACE_TSEC_FULL": "true"}):
        debug = aso_client._tsec_debug(tsec)
    assert "tsec_completo" not in debug
    assert tsec not in json.dumps(debug)
    # La huella sigue permitiendo comparar dos tokens.
    assert debug["tsec_longitud"] == len(tsec) and debug["tsec_sha256"]


def test_request_debug_strips_tsec_header_and_masks_password():
    with patch.dict(os.environ, {"ASO_TRACE_TSEC_FULL": "true", "ASO_TRACE_PASSWORD_FULL": "true"}):
        debug = aso_client._request_debug(
            method="POST", url="https://aso/granting", params={}, headers={"tsec": "eyJ0b2tlbi1kZS1wcnVlYmEtbXV5LWxhcmdvLXBhcmEtcXVlLW5vLXF1ZXBhLWVuLWVsLXByZWZpam8=", "accept": "json"},
            json_payload=GRANTING_BODY,
        )
    dumped = json.dumps(debug)
    assert "bi1kZS1wcnVlYmEtbXV5" not in dumped and "SuperSecreta1" not in dumped
    assert "tsec_completo" not in dumped


def test_full_body_in_e2e_debug_is_masked():
    with patch.dict(os.environ, {"E2E_DEBUG_TRACE": "true", "ASO_TRACE_FULL_BODY": "true"}):
        debug = aso_client._response_debug(_resp(FO_BODY), payload=FO_BODY)
    dumped = json.dumps(debug)
    assert "body_full" not in debug
    assert PAN not in dumped
    assert "4818" in dumped  # los ultimos 4 si, para poder cruzar con el cliente
