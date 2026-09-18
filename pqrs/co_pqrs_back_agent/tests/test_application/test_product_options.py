"""Tests for dynamic product-option rendering and the no-products routing.

Covers the bounded fix for step 1.4.1.1:
  - the choice option list is truncated to the number of products found in ASO
  - when no products are found, the bot routes to the satisfaction check.
"""

import json
import sys
import types
import unittest

# Stub the optional `strands` dependency so importing the router/agent modules
# never fails in environments where it is not installed.
_fake_strands = types.ModuleType("strands")


class _FakeAgent:  # pragma: no cover - trivial stub
    def __init__(self, *args, **kwargs) -> None:
        pass


_fake_strands.Agent = _FakeAgent
sys.modules.setdefault("strands", _fake_strands)

from application.chat.workflow_actions import (
    _load_all_products_central_risk,
    _load_desembargo_products_centrales,
    _load_embargo_products_centrales,
    _override_product_prompt_from_back_data,
    _continue_centrales_product_result,
)
from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.models import WorkflowStepOption
from domain.workflow.workflow_engine import WorkflowEngine
from infrastructure.entrypoint.api.router.v0.chat_router import _build_choice_options


def _twenty_product_options() -> list[WorkflowStepOption]:
    return [
        WorkflowStepOption(
            key=f"producto_{i}",
            label=f"Producto {i}",
            next_step="1.4.1.1.1.1",
        )
        for i in range(1, 21)
    ]


class BuildChoiceOptionsTests(unittest.TestCase):
    def test_truncates_to_number_of_found_products(self) -> None:
        options = _build_choice_options(
            step_options=_twenty_product_options(),
            option_labels_override=["*1234", "*5678"],
        )

        self.assertEqual(len(options), 2)
        self.assertEqual([o.key for o in options], ["producto_1", "producto_2"])
        self.assertEqual([o.label for o in options], ["*1234", "*5678"])

    def test_single_found_product_returns_one_option(self) -> None:
        options = _build_choice_options(
            step_options=_twenty_product_options(),
            option_labels_override=["*9999"],
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].key, "producto_1")
        self.assertEqual(options[0].label, "*9999")

    def test_seven_found_products_returns_seven_options(self) -> None:
        labels = [f"*{1000 + i}" for i in range(7)]
        options = _build_choice_options(
            step_options=_twenty_product_options(),
            option_labels_override=labels,
        )

        self.assertEqual(len(options), 7)
        self.assertEqual(options[-1].key, "producto_7")

    def test_empty_override_returns_no_options(self) -> None:
        options = _build_choice_options(
            step_options=_twenty_product_options(),
            option_labels_override=[],
        )

        self.assertEqual(options, [])

    def test_no_override_keeps_all_static_options(self) -> None:
        options = _build_choice_options(
            step_options=_twenty_product_options(),
            option_labels_override=None,
        )

        self.assertEqual(len(options), 20)
        self.assertEqual(options[2].label, "Producto 3")


class NoProductsRoutingTests(unittest.TestCase):
    def _conversation(self) -> Conversation:
        return Conversation(
            conversation_id="03966512_20260619",
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.1",
            workflow="centrales_de_riesgo",
            user_id="03966512",
            messages=[],
        )

    def test_no_validaciones_routes_to_satisfaction_check(self) -> None:
        conversation = self._conversation()

        _override_product_prompt_from_back_data(
            conversation,
            '{"hallazgos": {"validaciones": []}}',
        )

        self.assertEqual(conversation.current_step, "satisfaction_check")
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertIn(
            "No encontramos productos",
            conversation.captured_data["satisfaction_context_message"],
        )
        # The satisfaction prompt was built for the shared step.
        self.assertIn(
            "dynamic_prompt_satisfaction_check",
            conversation.captured_data,
        )
        # No product selector labels were produced.
        self.assertNotIn("dynamic_option_labels_1.4.1.1", conversation.captured_data)

    def test_products_found_keeps_selector_step(self) -> None:
        conversation = self._conversation()

        # Forma REAL de produccion: back_data manda key_id (el numero de
        # obligacion con el que se cruza contra centrales) y contract_id.
        # Lo que se PINTA son los ultimos 4 del contrato.
        back_data = (
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "77001", "contract_id": "00130009005078159809",'
            ' "commercial_product_desc": "CUENTA DE AHORROS",'
            ' "hallazgos": [{"tipo": "estado", "valor": "ok"}]},'
            '{"key_id": "0005678", "hallazgos": [{"tipo": "estado", "valor": "ok"}]}'
            "]}}"
        )

        _override_product_prompt_from_back_data(conversation, back_data)

        self.assertEqual(conversation.current_step, "1.4.1.1")
        import json

        labels = json.loads(
            conversation.captured_data["dynamic_option_labels_1.4.1.1"]
        )
        self.assertEqual(len(labels), 2)
        # Contrato ...9809, NO el key_id 77001 (que daria *7001).
        self.assertEqual(labels[0], "CONTRATO CUENTA DE AHORROS *9809")
        # Sin contract_id se cae al key_id, que es mejor que un XXXX.
        self.assertEqual(labels[1], "CONTRATO Producto financiero *5678")

        prompt = conversation.captured_data["dynamic_prompt_1.4.1.1"]
        self.assertIn(
            "Las siguiente opciones tienen alguna novedad en centrales de riesgo ¿Cual quieres consultar?",
            prompt,
        )
        self.assertIn("- CONTRATO CUENTA DE AHORROS *9809", prompt)
        self.assertIn("- CONTRATO Producto financiero *5678", prompt)


class CentralesSubflowSelectionTests(unittest.TestCase):
    def _conversation(self, back_data: str, current_step: str) -> Conversation:
        return Conversation(
            conversation_id="03966512_20260914",
            status=ConversationStatus.ACTIVE,
            current_step=current_step,
            workflow="centrales_de_riesgo",
            user_id="03966512",
            captured_data={"back_data_result": back_data},
        )

    def test_selector_exposes_separate_embargo_and_sold_portfolio_options(self) -> None:
        steps = WorkflowEngine().catalog.flows["centrales_de_riesgo"].steps
        step = steps["1.4.1"]

        self.assertFalse(step.smart_route)
        self.assertEqual(
            [option.key for option in step.options],
            [
                "reporte_no_reconocido_o_incorrecto",
                "embargo_o_desembargo",
                "cartera_vendida_o_cedida",
                "consulta_sin_permiso",
                "reporte_negativo_sin_notificacion",
            ],
        )
        offer = steps["1.4.1.1.embargo.ofrecer_desembargos"]
        self.assertEqual(
            [(option.key, option.next_step) for option in offer.options],
            [
                ("si_consultar_desembargos", "1.4.1.1.embargo.desembargos"),
                ("no_consultar_desembargos", "satisfaction_check"),
            ],
        )

    def test_embargo_subflow_only_lists_embargo_products(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "1111", "hallazgos": ['
            '{"id_msg": 19}, {"id_msg": 12}'
            ']},'
            '{"key_id": "2222", "hallazgos": [{"id_msg": 19}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_all_products_central_risk(
            conversation,
            allowed_id_messages=frozenset({10, 11, 12}),
            no_results_step="1.4.1.0.embargo.sin_resultados",
        )

        self.assertEqual(conversation.current_step, "1.4.1.1")
        self.assertEqual(
            conversation.captured_data["dynamic_option_labels_1.4.1.1"],
            '["CONTRATO Producto financiero *1111"]',
        )
        selected_products = json.loads(
            conversation.captured_data["centrales_riesgo_back_data_map"]
        )
        self.assertEqual(
            [hallazgo["id_msg"] for hallazgo in selected_products[0]["hallazgos"]],
            [12],
        )

    def test_sold_portfolio_subflow_ends_when_no_product_matches(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "1111", "hallazgos": [{"id_msg": 12}]}'
            ']}}',
            "1.4.1.0.cartera_vendida",
        )

        _load_all_products_central_risk(
            conversation,
            allowed_id_messages=frozenset({3, 19}),
            no_results_step="1.4.1.0.cartera_vendida.sin_resultados",
        )

        self.assertEqual(
            conversation.current_step,
            "1.4.1.0.cartera_vendida.sin_resultados",
        )
        self.assertEqual(conversation.status, ConversationStatus.CLOSED)

    def test_embargo_is_shown_before_optional_desembargo_review(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "1111", "hallazgos": [{"id_msg": 12}]},'
            '{"key_id": "2222", "hallazgos": [{"id_msg": 11}]}'
            ']}}',
            "1.4.1.0.embargo",
        )
        conversation.flow_answers["tipo_inconveniente_centrales_de_riesgo"] = (
            "embargo_o_desembargo"
        )

        _load_embargo_products_centrales(conversation)

        selected_products = json.loads(
            conversation.captured_data["centrales_riesgo_back_data_map"]
        )
        stored_desembargos = json.loads(
            conversation.captured_data["centrales_embargo_desembargos_map"]
        )
        self.assertEqual(selected_products[0]["hallazgos"][0]["id_msg"], 12)
        self.assertEqual(stored_desembargos[0]["hallazgos"][0]["id_msg"], 11)
        self.assertEqual(conversation.current_step, "1.4.1.1")

        _continue_centrales_product_result(conversation)

        self.assertEqual(
            conversation.current_step,
            "1.4.1.1.embargo.ofrecer_desembargos",
        )

    def test_only_desembargos_offers_optional_review_then_lists_them(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "2222", "hallazgos": [{"id_msg": 11}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_embargo_products_centrales(conversation)

        self.assertEqual(
            conversation.current_step,
            "1.4.1.0.embargo.sin_embargos",
        )
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)

        _load_desembargo_products_centrales(conversation)

        selected_products = json.loads(
            conversation.captured_data["centrales_riesgo_back_data_map"]
        )
        self.assertEqual(selected_products[0]["hallazgos"][0]["id_msg"], 11)
        self.assertEqual(conversation.current_step, "1.4.1.1")

    def test_sin_embargos_lists_product_state_and_continues_normally(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "3333", "contract_id": "000000001234", '
            '"commercial_product_desc": "Cuenta de Ahorros", '
            '"origin_flag": "PASIVE", '
            '"hallazgos": [{"id_msg": 1}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_embargo_products_centrales(conversation)

        self.assertEqual(
            conversation.current_step,
            "1.4.1.0.embargo.sin_embargos.sin_desembargos",
        )
        message = conversation.captured_data[
            "dynamic_prompt_1.4.1.0.embargo.sin_embargos.sin_desembargos"
        ]
        self.assertIn("no presentan embargo vigente", message)
        self.assertIn("Cuenta de Ahorros terminado en 1234", message)
        self.assertNotIn("ACTIVA", message)
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)

    def test_sin_embargos_with_desembargos_shows_message_before_offer(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "3333", "contract_id": "000000001234", '
            '"commercial_product_desc": "Cuenta de Ahorros", '
            '"origin_flag": "PASIVE", '
            '"hallazgos": [{"id_msg": 1}]},'
            '{"key_id": "2222", "hallazgos": [{"id_msg": 11}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_embargo_products_centrales(conversation)

        self.assertEqual(conversation.current_step, "1.4.1.0.embargo.sin_embargos")
        message = conversation.captured_data[
            "dynamic_prompt_1.4.1.0.embargo.sin_embargos"
        ]
        self.assertIn("Cuenta de Ahorros terminado en 1234", message)
        self.assertNotIn("ACTIVA", message)
        self.assertIn("¿Te gustaría consultarlos?", message)

    def test_no_embargos_or_desembargos_closes_with_specific_terminal_step(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "3333", "hallazgos": [{"id_msg": 3}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_embargo_products_centrales(conversation)

        self.assertEqual(conversation.current_step, "1.4.1.0.embargo.sin_resultados")
        self.assertEqual(conversation.status, ConversationStatus.CLOSED)

    def test_active_product_with_id_msg_1_is_not_a_no_embargo_result(self) -> None:
        conversation = self._conversation(
            '{"hallazgos": {"validaciones": ['
            '{"key_id": "3333", "origin_flag": "ACTIVE", '
            '"hallazgos": [{"id_msg": 1, "tipo": "Cuenta de Ahorros"}]}'
            ']}}',
            "1.4.1.0.embargo",
        )

        _load_embargo_products_centrales(conversation)

        self.assertEqual(conversation.current_step, "1.4.1.0.embargo.sin_resultados")
        self.assertNotIn(
            "dynamic_prompt_1.4.1.0.embargo.sin_embargos.sin_desembargos",
            conversation.captured_data,
        )


class Last4ContratoTests(unittest.TestCase):
    """Guarda de los 4 digitos que ve el cliente.

    El fallo original: se mostraban los ultimos 4 del key_id, que es el numero
    de OBLIGACION usado para cruzar contra centrales, no un dato de cara al
    cliente. Para el contrato 00130009005078159809 el key_id es 77001, asi que
    el cliente leia *7001 cuando su tarjeta termina en 9809.

    Sobrevivio tres meses y un rediseno del formato (23/07/2026) porque nada lo
    vigilaba. De ahi esta guarda.
    """

    def test_prefiere_el_contrato_sobre_el_key_id(self) -> None:
        from application.chat.workflow_actions import _last4_contrato

        real = {"key_id": "77001", "contract_id": "00130009005078159809"}
        self.assertEqual(_last4_contrato(real), "9809")
        self.assertNotEqual(
            _last4_contrato(real),
            "7001",
            "regresion: se volvio a mostrar el key_id en lugar del contrato",
        )

    def test_cae_al_key_id_cuando_no_hay_contrato(self) -> None:
        from application.chat.workflow_actions import _last4_contrato

        # El origen 'mock' no trae la columna contract_id.
        self.assertEqual(_last4_contrato({"product_id": "80301"}), "0301")
        self.assertEqual(_last4_contrato({"key_id": "385431"}), "5431")
        self.assertEqual(
            _last4_contrato({"contract_id": "", "product_id": "48654"}), "8654"
        )
        self.assertEqual(_last4_contrato({}), "XXXX")

    def test_ningun_punto_de_centrales_corta_el_key_id(self) -> None:
        """Ningun sitio de centrales debe volver a cortar product_id/key_id.

        Se revisa el fuente porque el fallo no estaba en una funcion sino
        repetido en diez sitios, y basta que uno se quede atras para que el
        cliente vea un numero en la lista y otro en el mensaje.
        """
        import re
        from pathlib import Path

        import application.chat.workflow_actions as modulo

        lineas = Path(modulo.__file__).read_text(encoding="utf-8").split("\n")
        culpables = []
        for indice, linea in enumerate(lineas):
            if not re.search(r"product_id.{0,4}\[-4:\]|_last4\(key_id\)", linea):
                continue
            funcion = next(
                (lineas[j] for j in range(indice, 0, -1) if lineas[j].startswith("def ")),
                "",
            )
            if "_last4" in funcion:  # los ayudantes mismos
                continue
            culpables.append(f"linea {indice + 1}: {linea.strip()}")

        self.assertEqual(
            culpables,
            [],
            "usa _last4_contrato() en lugar de cortar product_id/key_id:\n"
            + "\n".join(culpables),
        )


if __name__ == "__main__":
    unittest.main()
