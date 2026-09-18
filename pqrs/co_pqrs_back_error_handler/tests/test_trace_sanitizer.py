"""La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor."""

from __future__ import annotations

import json
import unittest

from domain.trace_event.models import TraceEventCommand
from domain.trace_event.sanitizer import REDACTED, mask_text, sanitize_trace_event, sanitize_value

PAN = "4912684136504818"


class MaskTextTests(unittest.TestCase):
    def test_pan_keeps_last_four_with_or_without_separators(self) -> None:
        self.assertEqual(mask_text(f"tarjeta {PAN}"), "tarjeta ************4818")
        self.assertEqual(mask_text("4912 6841 3650 4818"), "************4818")
        self.assertEqual(mask_text("4912-6841-3650-4818"), "************4818")

    def test_pan_inside_url_and_json_text(self) -> None:
        url = f"https://aso/cards/v2/operations?cardId={PAN}&operationDate=20260828"
        self.assertNotIn(PAN, mask_text(url))
        self.assertIn("4818", mask_text(url))
        text = json.dumps({"contracts": [{"formats": [{"number": PAN}]}]})
        self.assertNotIn(PAN, mask_text(text))

    def test_identifiers_that_are_not_cards_are_kept(self) -> None:
        # Cedulas, ids de conversacion y montos no se tocan.
        self.assertEqual(mask_text("cliente 1013634960 conv 7667553_20260905 monto 145000"),
                         "cliente 1013634960 conv 7667553_20260905 monto 145000")
        self.assertEqual(mask_text("contrato 00130766000200022384"), "contrato 00130766000200022384")

    def test_emails_are_hidden(self) -> None:
        self.assertEqual(mask_text("correo pablo.jarava@bbva.com"), "correo ***@***")


class SanitizeValueTests(unittest.TestCase):
    def test_secret_keys_are_redacted_whatever_the_casing(self) -> None:
        payload = {
            "headers": {"Authorization": "Bearer abc", "tsec": "xyz", "X-Api-Key": "k"},
            "tsec_completo": "eyJ...",
            "authentication": {"authenticationData": [{"authenticationData": ["Clave123"]}]},
            "body_full": {"anything": PAN},
            "password": "p", "PASSWD": "p", "api_key": "k", "client_secret": "s",
        }
        out = sanitize_value(payload)
        self.assertEqual(out["headers"], {"Authorization": REDACTED, "tsec": REDACTED, "X-Api-Key": REDACTED})
        self.assertEqual(out["tsec_completo"], REDACTED)
        self.assertEqual(out["authentication"]["authenticationData"], REDACTED)
        self.assertEqual(out["body_full"], REDACTED)
        for k in ("password", "PASSWD", "api_key", "client_secret"):
            self.assertEqual(out[k], REDACTED)

    def test_holder_names_become_initials(self) -> None:
        out = sanitize_value({"holderName": "Fabian Andres Figueroa", "customer_name": "Pablo Jarava"})
        self.assertEqual(out["holderName"], "F*** A*** F***")
        self.assertEqual(out["customer_name"], "P*** J***")

    def test_pan_nested_in_lists_and_strings(self) -> None:
        out = sanitize_value({"data": [{"contracts": [{"id": PAN, "formats": [{"number": PAN}]}]}], "msg": f"error {PAN}"})
        self.assertNotIn(PAN, json.dumps(out))
        self.assertIn("4818", json.dumps(out))

    def test_non_string_leaves_are_untouched(self) -> None:
        self.assertEqual(sanitize_value({"n": 4912684136504818, "f": 1.5, "b": True, "x": None}),
                         {"n": 4912684136504818, "f": 1.5, "b": True, "x": None})


class SanitizeTraceEventTests(unittest.TestCase):
    def test_top_level_identifiers_survive_but_payloads_are_cleaned(self) -> None:
        command = TraceEventCommand(
            event_type="aso", operation="tsec", outcome="ok", component="co_pqrs_back_trx_noreconocida",
            conversation_id="1013634960_20260909", customer_id="1013634960",
            target=f"https://aso/cards/v2/operations?cardId={PAN}",
            request_summary={"body_enviado": {"authentication": {"authenticationData": [{"authenticationData": ["Secreta1"]}]}},
                             "tsec_completo": "eyJhbGciOi..."},
            response_summary={"body_full": {"data": [{"contracts": [{"id": PAN, "holderName": "Fabian Figueroa"}]}]},
                              "body_masked": "ok"},
            error_message=f"ASO rechazo la tarjeta {PAN} de fabian@bbva.com",
        )
        out = sanitize_trace_event(command.model_dump(mode="python"))
        dumped = json.dumps(out, default=str)
        self.assertEqual(out["conversation_id"], "1013634960_20260909")
        self.assertEqual(out["customer_id"], "1013634960")
        self.assertNotIn(PAN, dumped)
        self.assertNotIn("Secreta1", dumped)
        self.assertNotIn("eyJhbGciOi", dumped)
        self.assertNotIn("fabian@bbva.com", dumped)
        self.assertEqual(out["response_summary"]["body_full"], REDACTED)
        self.assertIn("************4818", out["target"])
        # Y el resultado sigue siendo un comando valido.
        TraceEventCommand.model_validate(out)


if __name__ == "__main__":
    unittest.main()
