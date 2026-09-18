"""Debug completo de las llamadas ASO (peticion + respuesta).

Motivacion (2026-08-25): las trazas de MinIO no permitian saber si el `tsec` se
habia enviado, porque de la peticion solo se registraban los `params`. Se
concluia erroneamente que "el tsec no se consume" sobre un dato que nunca se
escribia.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest

from infrastructure.persistence import aso_client as ac


def _token(longitud_bruta: int = 1723) -> str:
    """Token base64 con la misma forma que el real (termina en '==')."""

    return base64.b64encode(b"x" * longitud_bruta).decode()


class TsecDebugTests(unittest.TestCase):
    def setUp(self):
        for flag in ("ASO_TRACE_TSEC_FULL", "ASO_TRACE_PASSWORD_FULL"):
            os.environ.pop(flag, None)

    def test_reports_when_the_token_was_not_sent(self):
        """Hoy una llamada sin tsec sale SIN autenticar y hay que verlo."""

        debug = ac._tsec_debug(None)
        self.assertFalse(debug["tsec_enviado"])
        self.assertIn("SIN autenticar", debug["tsec_motivo"])

    def test_fingerprint_lets_you_compare_tokens_without_exposing_them(self):
        tok = _token()
        debug = ac._tsec_debug(tok)
        self.assertTrue(debug["tsec_enviado"])
        self.assertEqual(debug["tsec_longitud"], len(tok))
        self.assertEqual(debug["tsec_sha256"], hashlib.sha256(tok.encode()).hexdigest())
        self.assertNotIn("tsec_completo", debug)

    def test_suffix_shows_the_base64_padding(self):
        """El '==' final era la sospecha: el sufijo permite verificarlo."""

        tok = _token()
        self.assertTrue(tok.endswith("=="))
        debug = ac._tsec_debug(tok)
        self.assertTrue(debug["tsec_sufijo"].endswith("=="))
        self.assertTrue(debug["tsec_termina_en_padding"])

    def test_full_value_never_appears_even_with_the_old_flag(self):
        """KYNS IT 3: el TSEC completo ya no sale a las trazas bajo ningun flag."""

        tok = _token()
        os.environ["ASO_TRACE_TSEC_FULL"] = "true"
        debug = ac._tsec_debug(tok)
        self.assertNotIn("tsec_completo", debug)
        self.assertNotIn(tok, json.dumps(debug))

    def test_same_token_produces_the_same_fingerprint(self):
        """Asi se comprueba que el ASO 2 recibio el token del grantingTicket."""

        tok = _token()
        self.assertEqual(
            ac._tsec_debug(tok)["tsec_sha256"], ac._tsec_debug(tok)["tsec_sha256"]
        )
        self.assertNotEqual(
            ac._tsec_debug(tok)["tsec_sha256"], ac._tsec_debug(_token(1724))["tsec_sha256"]
        )


class RequestDebugTests(unittest.TestCase):
    def setUp(self):
        for flag in ("ASO_TRACE_TSEC_FULL", "ASO_TRACE_PASSWORD_FULL"):
            os.environ.pop(flag, None)

    def test_get_records_method_url_params_and_headers(self):
        debug = ac._request_debug(
            method="GET",
            url="https://arqaso/financial-overview/v0/financial-overview",
            params={"customerId": "1010223694"},
            headers={"Accept": "application/json", "tsec": _token()},
        )
        self.assertEqual(debug["method"], "GET")
        self.assertIn("financial-overview", debug["url"])
        self.assertEqual(debug["params"], {"customerId": "1010223694"})
        self.assertTrue(debug["tsec_enviado"])

    def test_full_url_includes_the_query_string(self):
        """Para poder reproducir la llamada exacta con curl."""

        debug = ac._request_debug(
            method="GET", url="https://arqaso/cards/v2/operations",
            params={"cardId": "4912680517944979", "operationDate": "20260806"},
        )
        self.assertIn("cardId=4912680517944979", debug["url_completa"])
        self.assertIn("operationDate=20260806", debug["url_completa"])

    def test_tsec_is_not_left_inside_the_plain_headers(self):
        """Se extrae para tratarlo aparte, no se duplica en `headers`."""

        debug = ac._request_debug(
            method="GET", url="https://arqaso/x",
            headers={"Accept": "application/json", "tsec": _token()},
        )
        self.assertNotIn("tsec", debug["headers"])
        self.assertEqual(debug["headers"], {"Accept": "application/json"})

    def test_post_body_is_recorded(self):
        debug = ac._request_debug(
            method="POST", url="https://arqaso/cards/v1/cards/123/activations",
            headers={"tsec": _token()}, json_payload={"isActive": False},
        )
        self.assertEqual(debug["body_enviado"], {"isActive": False})
        self.assertTrue(debug["body_es_json"])


class PasswordMaskingTests(unittest.TestCase):
    """La contrasena del grantingTicket es una credencial PERMANENTE.

    Se enmascara aunque el resto del debug vaya completo: volcarla al bucket de
    trazas es un riesgo de otra magnitud que el del tsec, que es de sesion.
    """

    PAYLOAD = {
        "authentication": {
            "userID": "ZM12035",
            "consumerID": "12000035",
            "authenticationType": "04",
            "authenticationData": [
                {"idAuthenticationData": "password", "authenticationData": ["ClaveSecreta"]}
            ],
        },
        "backendUserRequest": {"userId": "", "accessCode": "", "dialogId": ""},
    }

    def setUp(self):
        os.environ.pop("ASO_TRACE_PASSWORD_FULL", None)

    def test_password_is_masked_by_default(self):
        limpio = ac._mask_password(self.PAYLOAD)
        valor = limpio["authentication"]["authenticationData"][0]["authenticationData"][0]
        self.assertNotIn("ClaveSecreta", str(valor))
        self.assertIn("oculto", str(valor))

    def test_the_rest_of_the_payload_survives(self):
        limpio = ac._mask_password(self.PAYLOAD)
        self.assertEqual(limpio["authentication"]["userID"], "ZM12035")
        self.assertEqual(limpio["authentication"]["consumerID"], "12000035")

    def test_original_payload_is_not_mutated(self):
        ac._mask_password(self.PAYLOAD)
        original = self.PAYLOAD["authentication"]["authenticationData"][0]["authenticationData"][0]
        self.assertEqual(original, "ClaveSecreta")

    def test_password_is_masked_even_with_the_old_full_flag(self):
        """KYNS IT 3: la contrasena del granting nunca viaja en claro a la traza."""

        os.environ["ASO_TRACE_PASSWORD_FULL"] = "true"
        limpio = ac._mask_password(self.PAYLOAD)
        valor = limpio["authentication"]["authenticationData"][0]["authenticationData"][0]
        self.assertNotEqual(valor, "ClaveSecreta")
        self.assertIn("oculto", valor)


class ChainIdTests(unittest.TestCase):
    """Correlaciona el grantingTicket con los ASO que usaron ese token."""

    def test_each_client_has_its_own_chain_id(self):
        uno, otro = ac.TrxAsoClient(), ac.TrxAsoClient()
        self.assertTrue(uno._chain_id)
        self.assertNotEqual(uno._chain_id, otro._chain_id)

    def test_chain_id_is_stable_within_a_client(self):
        cliente = ac.TrxAsoClient()
        self.assertEqual(cliente._chain_id, cliente._chain_id)


if __name__ == "__main__":
    unittest.main()
