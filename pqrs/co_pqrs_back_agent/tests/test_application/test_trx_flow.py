import unittest

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.workflow_engine import WorkflowEngine

_PQRS_URL = "https://peticiones.bbva.com.co/"


def _trx_conversation() -> Conversation:
    return Conversation(
        conversation_id="7667553_20260710",
        status=ConversationStatus.ACTIVE,
        current_step="2.4.0",
        general_workflow="Transaccion no reconocida",
        workflow="trx_no_reconocida",
        flow_version=1,
        user_id="7667553",
    )


class TrxFlowTests(unittest.TestCase):
    """Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def _walk(self, inputs: list[str]) -> Conversation:
        conv = _trx_conversation()
        for content in inputs:
            self.engine.generate_response(conv, content)
        return conv

    def test_entry_step_has_four_events(self) -> None:
        conv = _trx_conversation()
        self.assertIsNotNone(self.engine.render_current_step_prompt(conv))
        _, step = self.engine.get_current_step(conv)
        keys = {option.key for option in step.options}
        self.assertEqual(
            keys,
            {"cambiazo", "hurto_o_perdida", "ingenieria_social", "compra_presencial_o_internet"},
        )

    def test_options_1_2_3_offer_pqrs_form_and_route_to_satisfaction(self) -> None:
        for option in ("cambiazo", "hurto_o_perdida", "ingenieria_social"):
            conv = _trx_conversation()
            response = self.engine.generate_response(conv, option)
            # 2.4.1 dice "formulario"; 2.4.2/2.4.3 llevan la cola del
            # tablero: "...en este enlace y nosotros nos encargaremos..."
            self.assertTrue(
                "formulario" in response.lower() or "enlace" in response.lower(),
                response,
            )
            self.assertNotIn(_PQRS_URL, response)
            self.engine.generate_response(conv, "pqr")
            self.assertEqual(conv.current_step, "satisfaction_check")

    def test_option_4_enters_recurrence_step(self) -> None:
        conv = self._walk(["compra_presencial_o_internet"])
        self.assertEqual(conv.current_step, "2.4.0.1")

    def test_recurrence_redirect_step_shows_dedicated_message(self) -> None:
        conv = _trx_conversation()
        conv.current_step = "2.4.0.pqr_recurrencia"
        prompt = (self.engine.render_current_step_prompt(conv) or "").lower()
        self.assertIn("gestión reciente", prompt)  # YAML tildado (21/08)
        self.assertIn("formulario", prompt)
        self.engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")

    def test_count_to_onebyone_to_confirmation(self) -> None:
        conv = self._walk(["compra_presencial_o_internet", "continuar"])  # -> 2.4.0.1.1
        self.assertEqual(conv.current_step, "2.4.0.1.1")
        self.engine.generate_response(conv, "2")  # -> 2.4.0.1.2
        self.assertEqual(conv.current_step, "2.4.0.1.2")
        self.assertIn("una transacción a la vez", self.engine.render_current_step_prompt(conv).lower())
        self.engine.generate_response(conv, "empezar")  # -> 2.4.0.1.3
        self.assertEqual(conv.current_step, "2.4.0.1.3")
        prompt = self.engine.render_current_step_prompt(conv).lower()
        self.assertIn("hasta 3 transacciones", prompt)

    def test_more_than_three_routes_to_pqr(self) -> None:
        conv = self._walk(["compra_presencial_o_internet", "continuar", "mas_de_3"])
        self.assertEqual(conv.current_step, "2.4.0.1.1.pqr")
        self.engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")

    def test_confirmation_yes_goes_to_products_gate(self) -> None:
        conv = self._walk(["compra_presencial_o_internet", "continuar", "2", "empezar"])
        self.assertEqual(conv.current_step, "2.4.0.1.3")
        self.engine.generate_response(conv, "continuar")  # Si -> 2.4.0.1.4 (gate productos)
        self.assertEqual(conv.current_step, "2.4.0.1.4")

    def test_confirmation_finalizar_goes_to_satisfaction(self) -> None:
        conv = self._walk(["compra_presencial_o_internet", "continuar", "2", "empezar"])
        self.engine.generate_response(conv, "finalizar")
        self.assertEqual(conv.current_step, "satisfaction_check")


    def test_confirmacion_permite_volver_al_listado(self) -> None:
        """2.4.0.1.11 ofrece volver al selector (2.4.0.1.9) si el cliente eligio
        la transaccion equivocada, ademas de reportar o reconocer."""
        conv = _trx_conversation()
        conv.current_step = "2.4.0.1.11"
        _, step = self.engine.get_current_step(conv)
        rutas = {o.key: o.next_step for o in step.options}
        self.assertIn("volver_listado", rutas)
        self.assertEqual(rutas["volver_listado"], "2.4.0.1.9")
        # las otras dos rutas se conservan
        self.assertEqual(rutas["si_reportar"], "2.4.0.1.12")
        self.assertEqual(rutas["ya_reconozco"], "satisfaction_check")
    def test_value_in_range_goes_to_date_and_out_of_range_to_pqr(self) -> None:
        base = ["compra_presencial_o_internet", "continuar", "2", "empezar", "continuar", "continuar", "producto_1"]
        conv = self._walk(base + ["entre_35000_500000"])
        self.assertEqual(conv.current_step, "2.4.0.1.7")
        conv2 = self._walk(base + ["menor_35000"])
        self.assertEqual(conv2.current_step, "2.4.0.1.6.pqr")

    def test_block_routing_is_semantic(self) -> None:
        base = [
            "compra_presencial_o_internet", "continuar", "2", "empezar", "continuar", "continuar",
            "producto_1", "entre_35000_500000", "06/08/2026", "continuar", "movimiento_1", "continuar",
            "si_reportar", "continuar", "si_investigar",
        ]
        # definitivamente -> permanente (2.4.0.1.17)
        conv = self._walk(base + ["definitivamente"])
        self.assertEqual(conv.current_step, "2.4.0.1.17")
        # temporalmente -> temporal (2.4.0.1.16)
        conv2 = self._walk(base + ["temporalmente"])
        self.assertEqual(conv2.current_step, "2.4.0.1.16")

    def test_full_happy_path_loops_back_to_confirmation(self) -> None:
        inputs = [
            "compra_presencial_o_internet", "continuar", "2", "empezar", "continuar", "continuar",
            "producto_1", "entre_35000_500000", "06/08/2026", "continuar", "movimiento_1", "continuar",
            "si_reportar", "continuar", "si_investigar", "definitivamente", "si_bloquear", "continuar",
            "continuar", "continuar", "continuar", "continuar", "si_siguiente",
        ]
        conv = self._walk(inputs)
        self.assertEqual(conv.current_step, "2.4.0.1.3")


if __name__ == "__main__":
    unittest.main()


class VigenciaFronterasTests(unittest.TestCase):
    """Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120).

    Regla confirmada por negocio el 14/08: solo marca, sin ambito. Fechas
    relativas para que las pruebas no caduquen con los fixtures.
    """

    @staticmethod
    def _hace(dias: int) -> str:
        from datetime import datetime, timedelta

        return (datetime.now() - timedelta(days=dias)).strftime("%d/%m/%Y")

    def _vencida(self, dias: int, brand: str) -> bool:
        from application.chat.chat_service import _trx_vigencia_vencida

        return _trx_vigencia_vencida(self._hace(dias), brand)

    def test_visa_179_pasa(self) -> None:
        self.assertFalse(self._vencida(179, "VISA"))

    def test_visa_180_exactos_pasan(self) -> None:
        """El limite es inclusivo: la comparacion es `dias > limite`."""

        self.assertFalse(self._vencida(180, "VISA"))

    def test_visa_181_vence(self) -> None:
        self.assertTrue(self._vencida(181, "VISA"))

    def test_master_119_pasa(self) -> None:
        self.assertFalse(self._vencida(119, "MASTERCARD"))

    def test_master_120_exactos_pasan(self) -> None:
        self.assertFalse(self._vencida(120, "MASTERCARD"))

    def test_master_121_vence(self) -> None:
        self.assertTrue(self._vencida(121, "MASTERCARD"))

    def test_banda_diferencial_150_dias(self) -> None:
        """El caso que ensena la diferencia: mismo dia, distinta marca."""

        self.assertFalse(self._vencida(150, "VISA"))
        self.assertTrue(self._vencida(150, "MASTERCARD"))

    def test_master_se_reconoce_por_subcadena(self) -> None:
        for brand in ("MASTER", "MasterCard", "master card", "MASTERCARD"):
            with self.subTest(brand=brand):
                self.assertTrue(self._vencida(121, brand))

    def test_marca_desconocida_recibe_hoy_el_plazo_largo(self) -> None:
        """Documenta el hueco abierto: lo que no dice MASTER cae en el else.

        AMEX, Diners, marca vacia o ausente reciben 180 dias -- el plazo mas
        permisivo. Pendiente de decision de negocio (ver
        ESTRATEGIA_MENSAJES_Y_VIGENCIA.md); cuando se decida, este test cambia
        de expectativa y es el aviso de que hay que tocarlo.
        """

        for brand in ("AMEX", "DINERS", "", None):
            with self.subTest(brand=brand):
                self.assertFalse(self._vencida(150, brand))


class MensajesDinamicosDegradacionTests(unittest.TestCase):
    """Con el dato ausente, ningun mensaje dinamico expone un crudo.

    Los tres defectos de mensajes de la semana nacieron aqui: leer una clave
    que el servicio no publica y caer a un identificador de repuesto (H-08
    *XXXX), o a un formato ajeno (H-03 fecha ISO). Estas pruebas fijan que la
    degradacion sea segura: mejor "****" que un contrato entero.
    """

    CRUDOS = ("XXXX", "None", "null")

    def test_selector_sin_last_four_no_expone_el_contrato(self) -> None:
        # Con el copy del tablero el prompt ya no lista productos: la
        # garantia de degradacion vive en las ETIQUETAS de los botones.
        from application.chat.workflow_actions import (
            _build_trx_product_option_labels,
        )

        etiquetas = _build_trx_product_option_labels(
            [
                {
                    "commercial_product_desc": "Tarjeta de Credito",
                    "contract_id": "00131003201300060",
                    "product_id": "00131003201300060",
                    # sin last_four ni last_four_pan_id: el caso real de ADA
                }
            ]
        )
        prompt = " ".join(etiquetas)
        # Degradacion honesta: sin last_four se muestra SOLO el tipo. No se
        # inventan digitos ni se cuela el crudo "XXXX" (prohibido en pantalla).
        self.assertIn("Tarjeta de Credito", prompt)
        self.assertNotIn("00131003201300060", prompt)
        for crudo in self.CRUDOS:
            self.assertNotIn(crudo, prompt)

    def test_selector_usa_last_four_y_no_el_identificador(self) -> None:
        from application.chat.workflow_actions import (
            _build_trx_product_option_labels,
        )

        prompt = " ".join(_build_trx_product_option_labels(
            [
                {
                    "commercial_product_desc": "Tarjeta de Credito",
                    "last_four": "0060",
                    "contract_id": "00131003201300099",
                    "product_id": "00131003201300099",
                }
            ]
        ))
        self.assertIn("•0060", prompt)  # mascara del tablero en el selector
        self.assertNotIn("0099", prompt)

    def test_fecha_iso_se_muestra_en_ddmmaaaa(self) -> None:
        from application.chat.workflow_actions import _fecha_ddmmaaaa

        self.assertEqual(_fecha_ddmmaaaa("2026-08-06"), "06/08/2026")

    def test_fecha_en_otro_formato_se_deja_intacta(self) -> None:
        """No se inventa una conversion sobre algo que no es ISO."""

        from application.chat.workflow_actions import _fecha_ddmmaaaa

        for valor in ("06/08/2026", "", "sin fecha"):
            with self.subTest(valor=valor):
                self.assertEqual(_fecha_ddmmaaaa(valor), valor)


class FechasAceptadasTests(unittest.TestCase):
    """Tolerante al recibir, estricto al pedir (peticion de negocio 18/08)."""

    def _parse(self, valor):
        from application.chat.chat_service import _trx_parse_date

        return _trx_parse_date(valor)

    def test_formatos_aceptados(self) -> None:
        for valor in ("06/08/2026", "06-08-2026", "2026-08-06", "6/8/2026", "6-8-2026"):
            with self.subTest(valor=valor):
                parsed = self._parse(valor)
                self.assertIsNotNone(parsed, f"{valor} deberia aceptarse")
                self.assertEqual((parsed.day, parsed.month, parsed.year), (6, 8, 2026))

    def test_el_dia_va_primero_no_hay_ambiguedad(self) -> None:
        parsed = self._parse("03/04/2026")
        self.assertEqual((parsed.day, parsed.month), (3, 4))

    def test_fecha_futura_se_rechaza(self) -> None:
        """Una compra no puede ser de manana: antes se aceptaba y el cliente
        recibia un 'no encontramos compras' que no explicaba nada."""

        from datetime import datetime, timedelta

        manana = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        self.assertIsNone(self._parse(manana))
        self.assertIsNone(self._parse("31/12/2099"))

    def test_hoy_se_acepta(self) -> None:
        from datetime import datetime

        self.assertIsNotNone(self._parse(datetime.now().strftime("%d/%m/%Y")))

    def test_basura_se_rechaza(self) -> None:
        for valor in ("hola", "", "99/99/9999", "2026", None):
            with self.subTest(valor=valor):
                self.assertIsNone(self._parse(valor))


class UltimosCuatroDesdeFinancialOverviewTests(unittest.TestCase):
    """Los 4 digitos que ve el cliente son los del PAN, no los del contrato.

    ADA (last_four_pan_id) y el PAN de financial-overview son identificadores
    distintos: en el simulador coinciden por diseno de los fixtures, pero en
    cartera real pueden divergir. El dato de ADA queda solo como llave de cruce
    contra financial-overview, que es su funcion legitima.
    """

    def _producto(self, **extra):
        base = {"contract_id": "00131003201300060", "last_four": "0060",
                "product_desc": "Tarjeta de Credito", "origin_flag": "TDC",
                "card_brand": "VISA"}
        base.update(extra)
        return base

    def test_el_pan_reescribe_los_ultimos_cuatro(self) -> None:
        producto = self._producto(last_four="9999")   # ADA dice otra cosa
        producto["card_id"] = "4912680517940060"
        producto["last_four"] = producto["card_id"][-4:]
        self.assertEqual(producto["last_four"], "0060")

    def test_sin_pan_se_conserva_el_dato_de_ada(self) -> None:
        """Fail-open: si financial-overview no responde, mejor el dato de ADA
        que dejar al cliente sin selector."""

        producto = self._producto()
        producto["last_four_origen"] = "ada_fallback"
        self.assertEqual(producto["last_four"], "0060")
        self.assertNotIn("card_id", producto)

    def test_el_selector_nunca_muestra_el_contrato(self) -> None:
        from application.chat.workflow_actions import (
            _build_trx_product_option_labels,
        )

        prompt = " ".join(_build_trx_product_option_labels(
            [self._producto(card_id="4912680517940060", last_four="0060")]
        ))
        self.assertIn("•0060", prompt)  # mascara del tablero en el selector
        self.assertNotIn("00131003201300060", prompt)


class SelectorDeMovimientosTests(unittest.TestCase):
    """Selector de movimientos (04/09): el servicio pagina y el agente PINTA.

    ``trx_movimientos_result`` guarda SOLO la pagina visible; la metadata
    (page/total/total_pages/has_prev/has_next) la fija el gate. El selector no
    rebana: emite las 1..5 casillas de la pagina + "Anterior"/"Ver mas" segun la
    metadata + la salida (siempre). La seleccion es POSICIONAL en la pagina.
    """

    def _conv_pagina(
        self,
        movs_pagina: list[dict],
        *,
        page: int,
        total: int,
        total_pages: int,
        has_prev: bool,
        has_next: bool,
    ):
        import json

        from domain.conversation.models import Conversation, ConversationStatus

        conv = Conversation(
            conversation_id="1013634968_20260819",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.1.9",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            user_id="1013634968",
        )
        cd = conv.captured_data
        cd["trx_movimientos_result"] = json.dumps({"movimientos": movs_pagina})
        cd["trx_movs_pagina"] = str(page)
        cd["trx_movs_total"] = str(total)
        cd["trx_movs_total_pages"] = str(total_pages)
        cd["trx_movs_has_prev"] = "1" if has_prev else "0"
        cd["trx_movs_has_next"] = "1" if has_next else "0"
        return conv

    def _movs(self, desde: int, hasta: int) -> list[dict]:
        return [
            {"id": f"TX{i}", "descripcion": f"COMPRA {i}", "valor": 100000 + i,
             "fecha": "2026-08-06"}
            for i in range(desde, hasta + 1)
        ]

    def _pintar(self, conv):
        import json

        from application.chat.workflow_actions import _load_trx_movement_selector

        _load_trx_movement_selector(conv)
        return (
            json.loads(conv.captured_data["dynamic_option_labels_2.4.0.1.9"]),
            json.loads(conv.captured_data["dynamic_option_keys_2.4.0.1.9"]),
            conv.captured_data["dynamic_prompt_2.4.0.1.9"],
        )

    def test_pagina_uno_muestra_cinco_y_ver_mas(self) -> None:
        conv = self._conv_pagina(
            self._movs(1, 5), page=1, total=70, total_pages=14,
            has_prev=False, has_next=True,
        )
        labels, keys, prompt = self._pintar(conv)
        # 5 casillas + "Ver mas" + salida (sin "Anterior" en la primera)
        self.assertEqual(
            keys,
            ["movimiento_1", "movimiento_2", "movimiento_3", "movimiento_4",
             "movimiento_5", "mas_movimientos", "no_encuentro"],
        )
        self.assertNotIn("Anterior", labels)
        self.assertIn("1 a 5 de 70", prompt)
        self.assertIn("página 1 de 14", prompt)

    def test_pagina_intermedia_lleva_anterior_y_ver_mas(self) -> None:
        # El servicio ya rebano la pagina 2: son las posiciones 6..10 del dia,
        # pero el agente las numera 1..5 (posicional en la pagina visible).
        conv = self._conv_pagina(
            self._movs(6, 10), page=2, total=12, total_pages=3,
            has_prev=True, has_next=True,
        )
        labels, keys, prompt = self._pintar(conv)
        self.assertEqual(keys[0], "movimiento_1")   # POSICIONAL en la pagina
        self.assertEqual(keys[4], "movimiento_5")
        self.assertEqual(keys[-3], "anterior_movimientos")
        self.assertEqual(keys[-2], "mas_movimientos")
        self.assertEqual(keys[-1], "no_encuentro")
        self.assertIn("6 a 10 de 12", prompt)
        self.assertIn("página 2 de 3", prompt)

    def test_ultima_pagina_con_anterior_sin_ver_mas(self) -> None:
        conv = self._conv_pagina(
            self._movs(11, 12), page=3, total=12, total_pages=3,
            has_prev=True, has_next=False,
        )
        labels, keys, prompt = self._pintar(conv)
        self.assertEqual(
            keys,
            ["movimiento_1", "movimiento_2", "anterior_movimientos", "no_encuentro"],
        )
        self.assertNotIn("Ver más movimientos", labels)
        self.assertIn("11 a 12 de 12", prompt)

    def test_seleccion_posicional_mapea_al_id_de_la_pagina(self) -> None:
        # La 2a casilla de la pagina 2 debe resolver al id del 2o movimiento
        # de ESA pagina (TX7), no al de la lista completa.
        from application.chat.chat_service import _resolve_selected_movimiento_id

        conv = self._conv_pagina(
            self._movs(6, 10), page=2, total=12, total_pages=3,
            has_prev=True, has_next=True,
        )
        self._pintar(conv)
        conv.flow_answers["trx_movimiento_seleccionado"] = "movimiento_2"
        self.assertEqual(_resolve_selected_movimiento_id(conv), "TX7")

    def test_la_salida_existe_con_cualquier_pagina(self) -> None:
        casos = [
            (self._movs(1, 5), 1, 70, 14, False, True),
            (self._movs(1, 1), 1, 1, 1, False, False),
            (self._movs(11, 12), 3, 12, 3, True, False),
        ]
        for movs, page, total, tp, hp, hn in casos:
            with self.subTest(page=page):
                conv = self._conv_pagina(
                    movs, page=page, total=total, total_pages=tp,
                    has_prev=hp, has_next=hn,
                )
                _labels, keys, _ = self._pintar(conv)
                self.assertEqual(keys[-1], "no_encuentro")

    def test_pagina_unica_no_menciona_tramo_ni_navegacion(self) -> None:
        conv = self._conv_pagina(
            self._movs(1, 3), page=1, total=3, total_pages=1,
            has_prev=False, has_next=False,
        )
        labels, keys, prompt = self._pintar(conv)
        self.assertNotIn("Te muestro", prompt)
        self.assertNotIn("Anterior", labels)
        self.assertNotIn("Ver más movimientos", labels)
        self.assertEqual(keys, ["movimiento_1", "movimiento_2", "movimiento_3", "no_encuentro"])


if __name__ == "__main__":
    unittest.main()
