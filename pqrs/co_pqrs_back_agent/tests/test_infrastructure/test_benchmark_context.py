"""La cabecera del benchmark sale en todo turno de chat, aunque no haya ruteo.

Motivo: en la corrida adversarial y de grounding del 15/09, 21 casos quedaron
"sin resolver" porque en algun turno (pregunta de satisfaccion, transicion de
paso) la respuesta no llevo X-Benchmark-Data, y el benchmark no puede seguir
una conversacion de varios turnos sin ella.
"""

import unittest

from infrastructure.observability import benchmark_context as bc


class FinishCaptureTests(unittest.TestCase):
    def test_sin_token_no_hay_cabecera(self) -> None:
        self.assertIsNone(bc.finish_capture(None, complete_in_flow=True))

    def test_captura_abierta_sin_completar_no_emite(self) -> None:
        # Comportamiento anterior, conservado para rutas que no son POST /chat.
        token = bc.start_capture()
        self.assertIsNone(bc.finish_capture(token))

    def test_captura_abierta_se_completa_como_in_flow(self) -> None:
        token = bc.start_capture()
        data = bc.finish_capture(token, complete_in_flow=True)
        self.assertIsNotNone(data)
        self.assertEqual(data["routing_outcome"], "in_flow")
        self.assertEqual(data["routing_time_ms"], 0.0)
        self.assertEqual(data["workflow_result"], "")
        self.assertEqual(data["llm_token_input"], 0)
        self.assertNotIn("_t0", data)

    def test_captura_cerrada_por_ruteo_no_se_altera(self) -> None:
        token = bc.start_capture()

        class _Conv:
            workflow = "trx_no_reconocida"
            captured_data = {"routing_outcome": "guardrail_blocked"}
            current_step = "start"

        class _Usage:
            input_tokens = 12
            output_tokens = 3
            cached_input_tokens = 0

        bc.mark_routing_done(_Conv(), _Usage())
        data = bc.finish_capture(token, complete_in_flow=True)
        self.assertEqual(data["routing_outcome"], "guardrail_blocked")
        self.assertEqual(data["workflow_result"], "trx_no_reconocida")
        self.assertEqual(data["llm_token_input"], 12)
        self.assertGreaterEqual(data["routing_time_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
