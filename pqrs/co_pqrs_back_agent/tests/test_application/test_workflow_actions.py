import json
import unittest

from application.chat.workflow_actions import (
    _load_centrales_response,
    _load_notificacion_producto_seleccionado,
    _load_products_consulta_sin_permiso,
    _load_products_notificacion_centrales,
    _load_selected_trx_transactions,
    _load_trx_movement_confirmation,
    _load_trx_product_selector,
    _resolve_centrales_variables,
    execute_workflow_action,
)
from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.models import WorkflowStep


class WorkflowActionsTests(unittest.TestCase):
    def _build_conversation(self, back_data: dict[str, object]) -> Conversation:
        return Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.3",
            general_workflow="PQRs",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={
                "tipo_inconveniente_centrales_de_riesgo": (
                    "reporte_negativo_sin_notificacion"
                )
            },
            captured_data={
                "back_data_result": json.dumps(back_data, ensure_ascii=False)
            },
            user_id="7667553",
        )

    def _build_consulta_sin_permiso_conversation(
        self, back_data: dict[str, object]
    ) -> Conversation:
        return Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.2",
            general_workflow="PQRs",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={
                "tipo_inconveniente_centrales_de_riesgo": "consulta_sin_permiso"
            },
            captured_data={
                "back_data_result": json.dumps(back_data, ensure_ascii=False)
            },
            user_id="7667553",
        )

    def _build_producto_conversation(
        self, back_data: dict[str, object]
    ) -> Conversation:
        # FASE 2 (analisis del producto elegido): paso 1.4.1.3.1
        conversation = self._build_conversation(back_data)
        conversation.current_step = "1.4.1.3.1"
        return conversation

    def test_notificacion_fase1_sin_reporte_muestra_mensaje_generico(self) -> None:
        conversation = self._build_conversation(
            {
                "validaciones": [
                    {
                        "key_id": "0011",
                        "hallazgos": [
                            {"tipo": "producto", "valor": "Al dia", "id_msg": 1}
                        ],
                    }
                ]
            }
        )

        _load_products_notificacion_centrales(conversation)

        message = conversation.captured_data["dynamic_prompt_1.4.1.3"]
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertIn("Buenas noticias", message)
        self.assertIn("tus productos", message)

    def test_notificacion_fase1_con_reporte_lista_productos(self) -> None:
        conversation = self._build_conversation(
            {
                "validaciones": [
                    {
                        "key_id": "4310AHO0011",
                        "hallazgos": [
                            {"tipo": "activo_mora", "valor": "mora", "id_msg": 4}
                        ],
                    }
                ]
            }
        )

        _load_products_notificacion_centrales(conversation)

        self.assertEqual(conversation.current_step, "1.4.1.3.0")
        self.assertIn(
            "Selecciona el producto",
            conversation.captured_data["dynamic_prompt_1.4.1.3.0"],
        )

    def test_notificacion_producto_renders_msg16_without_optional_fields(
        self,
    ) -> None:
        conversation = self._build_producto_conversation(
            {"caso": "si extracto", "id_msg": 16}
        )

        _load_notificacion_producto_seleccionado(conversation)

        self.assertEqual(conversation.current_step, "1.4.1.3.2")
        message = conversation.captured_data["dynamic_prompt_1.4.1.3.2"]
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertIn("Comprendo tu inquietud.", message)
        self.assertIn(
            "Este documento te fue enviado a los canales de contacto "
            "registrados para tu producto.",
            message,
        )
        self.assertNotIn("{detalle_notificacion}", message)

    def test_notificacion_producto_replaces_optional_fields_when_present(self) -> None:
        conversation = self._build_producto_conversation(
            {
                "caso": "si extracto",
                "id_msg": 16,
                "fecha": "01/06/2026",
                "correo": "cli****@example.com",
            }
        )

        _load_notificacion_producto_seleccionado(conversation)

        message = conversation.captured_data["dynamic_prompt_1.4.1.3.2"]
        self.assertIn("01/06/2026", message)
        self.assertIn("cli****@example.com", message)
        self.assertNotIn("{detalle_notificacion}", message)

    def test_notificacion_producto_supports_nested_payload_shape(self) -> None:
        conversation = self._build_producto_conversation(
            {"data": {"caso": "no extracto", "id": 17}}
        )

        _load_notificacion_producto_seleccionado(conversation)

        message = conversation.captured_data["dynamic_prompt_1.4.1.3.1"]
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        # El formulario PQRS ahora va como botón (key=pqr), no como link inline.
        self.assertNotIn("https://peticiones.bbva.com.co/", message)
        self.assertIn("formulario", message.lower())
        self.assertIn("centrales_riesgo_form_option", conversation.captured_data)

    def test_notificacion_producto_rejects_unexpected_message_ids(self) -> None:
        conversation = self._build_producto_conversation({"id_msg": 14})

        _load_notificacion_producto_seleccionado(conversation)

        self.assertEqual(conversation.status, ConversationStatus.CLOSED)
        self.assertIn(
            "601 401 0000",
            conversation.captured_data["dynamic_prompt_1.4.1.3.1"],
        )

    def test_execute_workflow_action_dispatches_notification_handler(self) -> None:
        conversation = self._build_conversation(
            {
                "validaciones": [
                    {
                        "key_id": "4310AHO0011",
                        "hallazgos": [
                            {"tipo": "activo_mora", "valor": "mora", "id_msg": 4}
                        ],
                    }
                ]
            }
        )

        execute_workflow_action(
            conversation=conversation,
            step=WorkflowStep(
                question="Consultando el estado de tus productos en centrales de riesgo.",
                action="consultar_todos_productos_centrales_sin_notificacion",
                input_type="choice",
            ),
        )

        self.assertEqual(conversation.current_step, "1.4.1.3.0")
        self.assertIn(
            "Selecciona el producto",
            conversation.captured_data["dynamic_prompt_1.4.1.3.0"],
        )

    def test_consulta_sin_permiso_supports_flat_payload_with_id_msg_14(self) -> None:
        conversation = self._build_consulta_sin_permiso_conversation(
            {
                "fecha": "",
                "tipo": "963191",
                "bandera": "true",
                "id_msg": 14,
            }
        )

        _load_products_consulta_sin_permiso(conversation)

        message = conversation.captured_data["dynamic_prompt_1.4.1.2"]
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertIn("esa consulta ocurrió porque", message)
        self.assertIn("contrataste", message)
        self.assertIn("963191", message)
        self.assertNotIn("[tipo de producto]", message)
        self.assertIn("huella", message)
        self.assertNotIn("Formulario de PQRS", message)
        self.assertNotIn("{detalle_consulta_autorizada}", message)

    def test_consulta_sin_permiso_flat_payload_does_not_fallback_to_id_15(self) -> None:
        conversation = self._build_consulta_sin_permiso_conversation(
            {"fecha": "2026-06-01", "id_msg": 14}
        )

        execute_workflow_action(
            conversation=conversation,
            step=WorkflowStep(
                question="Revisando tu informacion en centrales de riesgo.",
                action="consultar_productos_consulta_sin_permiso",
                input_type="choice",
            ),
        )

        message = conversation.captured_data["dynamic_prompt_1.4.1.2"]
        self.assertIn("01/06/2026", message)
        self.assertNotIn("Formulario de PQRS", message)

    def test_id_msg_12_renders_valor_pago_without_placeholder(self) -> None:
        hallazgo = {
            "tipo": "embargada",
            "id_msg": 12,
            "valor": {
                "nombre_entidad": "JUZGADO 12 CIVIL",
                "numero_oficio": "OF-7788",
                "valor_pago": "2500000",
                "fecha_oficio": "2026-06-01",
            },
        }

        variables = _resolve_centrales_variables(
            12,
            hallazgo=hallazgo,
            entry={},
            key_id="4310AHO0011",
        )
        message, _ = _load_centrales_response("12", variables)

        self.assertIn("2500000", message)
        self.assertNotIn("{valor_pago}", message)

    def test_id_msg_11_renders_every_lifted_embargo(self) -> None:
        hallazgo = {
            "tipo": "Cuenta Desembargada",
            "id_msg": 11,
            "valor": [
                {
                    "nombre_entidad": "JUZGADO 12 CIVIL",
                    "numero_oficio": "OF-7788",
                    "valor_pago": "2500000",
                    "fecha_oficio": "2026-06-01",
                    "fecha_desembargo": "2026-07-15",
                    "status": "ACTIVO",
                },
                {
                    "nombre_entidad": "JUZGADO 15 CIVIL",
                    "numero_oficio": "OF-9900",
                    "valor_pago": "3000000",
                    "fecha_oficio": "2026-06-10",
                    "fecha_desembargo": "2026-07-20",
                    "status": "ACTIVO",
                },
            ],
        }

        variables = _resolve_centrales_variables(
            11,
            hallazgo=hallazgo,
            entry={},
            key_id="4310AHO0011",
        )
        message, _ = _load_centrales_response("11", variables)

        self.assertIn("JUZGADO 12 CIVIL", message)
        self.assertIn("JUZGADO 15 CIVIL", message)
        self.assertIn("15/07/2026", message)
        self.assertIn("20/07/2026", message)
        self.assertIn("OF-7788", message)
        self.assertIn("OF-9900", message)
        self.assertNotIn("{detalles_desembargos}", message)

    def test_trx_product_selector_builds_dynamic_options(self) -> None:
        conversation = Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            captured_data={
                "trx_products_result": json.dumps(
                    {
                        "status": "ok",
                        "data": {
                            "products": [
                                {
                                    "product_id": "4340-TDC-1234",
                                    "commercial_product_desc": "Tarjeta de Credito",
                                    "last_four_pan_id": "1234",
                                },
                                {
                                    "product_id": "4310-AHO-5678",
                                    "commercial_product_desc": "Cuenta de Ahorros",
                                    "last_four_pan_id": "5678",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            },
            user_id="7667553",
        )

        _load_trx_product_selector(conversation)

        self.assertIn(
            "Tarjeta de Credito *1234",
            conversation.captured_data["dynamic_option_labels_2.4.0.2"],
        )
        self.assertIn("dynamic_prompt_2.4.0.2", conversation.captured_data)

    def test_trx_movements_render_as_single_select_buttons(self) -> None:
        conversation = Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.3",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            captured_data={
                "trx_transactions_result": json.dumps(
                    {
                        "status": "ok",
                        "id_message": 204,
                        "data": {
                            "movimientos": [
                                {
                                    "description": "COMPRA FALABELLA",
                                    "amount": 120000.0,
                                    "movement_date": "2026-07-15",
                                },
                                {
                                    "description": "COMPRA MERCADOLIBRE",
                                    "amount": 89990.0,
                                    "movement_date": "2026-07-15",
                                },
                                {
                                    "description": "ABONO/REVERSO",
                                    "amount": 45000.0,
                                    "movement_date": "2026-07-15",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            },
            user_id="7667553",
        )

        _load_selected_trx_transactions(conversation)

        labels = json.loads(
            conversation.captured_data["dynamic_option_labels_2.4.0.3"]
        )
        # 3 movimientos como botones + el boton fijo "No encuentro...".
        self.assertEqual(len(labels), 4)
        self.assertIn("COMPRA FALABELLA", labels[0])
        self.assertIn("$120.000", labels[0])
        self.assertIn("No encuentro", labels[3])

    def test_trx_movement_confirmation_shows_selected_detail(self) -> None:
        conversation = Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.3.1",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            flow_answers={"trx_movimiento_seleccionado": "movimiento_2"},
            captured_data={
                "trx_movimientos_map": json.dumps(
                    [
                        {"description": "COMPRA FALABELLA", "amount": 120000.0, "movement_date": "2026-07-15"},
                        {"description": "COMPRA MERCADOLIBRE", "amount": 89990.0, "movement_date": "2026-07-15"},
                    ],
                    ensure_ascii=False,
                ),
            },
            user_id="7667553",
        )

        _load_trx_movement_confirmation(conversation)

        prompt = conversation.captured_data["dynamic_prompt_2.4.0.3.1"]
        self.assertIn("COMPRA MERCADOLIBRE", prompt)
        self.assertIn("$89.990", prompt)
        self.assertIn("2026-07-15", prompt)

    def test_trx_no_movements_offers_pqrs(self) -> None:
        conversation = Conversation(
            conversation_id="7667553_20260610",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.3",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            captured_data={
                "trx_transactions_result": json.dumps(
                    {"status": "not_found", "id_message": 203, "data": {"movimientos": []}},
                    ensure_ascii=False,
                ),
            },
            user_id="7667553",
        )

        _load_selected_trx_transactions(conversation)

        self.assertIn("centrales_riesgo_form_option", conversation.captured_data)
        self.assertIn(
            "formulario PQR",
            conversation.captured_data["dynamic_prompt_2.4.0.3"],
        )


if __name__ == "__main__":
    unittest.main()
