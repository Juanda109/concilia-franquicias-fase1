import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from domain.conversation.models import Conversation, ConversationStatus
from domain.workflow.workflow_engine import WorkflowEngine
from application.chat import chat_service as cs

# Estos tests ejercitan el FLUJO REAL de TXNR, que en produccion nace CERRADO por el
# porton de despliegue (TRX_FLOW_ENABLED=false). Se abre explicitamente aqui para
# probar el flujo; el porton en si se prueba en test_trx_canary_gate.py.
_FLOW_OPEN = patch.object(cs, "_trx_flow_enabled", return_value=True)


def setUpModule() -> None:
    _FLOW_OPEN.start()


def tearDownModule() -> None:
    _FLOW_OPEN.stop()


def _conv(step: str) -> Conversation:
    return Conversation(
        conversation_id="1013634960_20260813",
        status=ConversationStatus.ACTIVE,
        current_step=step,
        general_workflow="Transaccion no reconocida",
        workflow="trx_no_reconocida",
        flow_version=1,
        user_id="1013634960",
    )


def _prefetch(conv: Conversation) -> None:
    # Sin back_trx (trx_service_url=None): solo se ejercitan los gates offline.
    asyncio.run(cs._prefetch_trx_data_if_needed(conv, None, None, None))


class TrxPendienteGateTests(unittest.TestCase):
    def test_pendiente_tdc_routes_to_exit(self) -> None:
        conv = _conv("2.4.0.1.12")
        conv.captured_data["trx_clasificacion"] = json.dumps({"pendiente_tdc": True})
        _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.1.12.exit")

    def test_not_pendiente_routes_to_investigar(self) -> None:
        conv = _conv("2.4.0.1.12")
        conv.captured_data["trx_clasificacion"] = json.dumps({"pendiente_tdc": False})
        _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.1.13")


class TrxValidacionesGateTests(unittest.TestCase):
    def _route(self, resultado: str) -> str:
        conv = _conv("2.4.0.1.19")
        conv.captured_data["trx_clasificacion"] = json.dumps({"resultado": resultado})
        _prefetch(conv)
        return conv.current_step

    def test_presencial(self) -> None:
        self.assertEqual(self._route("presencial"), "2.4.0.1.19.1")

    def test_reversado(self) -> None:
        self.assertEqual(self._route("reversado"), "2.4.0.1.19.2")

    def test_pqr(self) -> None:
        self.assertEqual(self._route("pqr"), "2.4.0.1.19.pqr")

    def test_devolucion(self) -> None:
        self.assertEqual(self._route("devolucion"), "2.4.0.1.20")

    def test_unknown_defaults_to_devolucion(self) -> None:
        self.assertEqual(self._route(""), "2.4.0.1.20")


class TrxLoopGateTests(unittest.TestCase):
    def test_last_tx_closes(self) -> None:
        # El cierre explicito (2.4.0.1.20.2, "ya reportaste todas") es SOLO
        # para quien declaro 2 o 3 (decision Pablo 21/08): a quien reporta una
        # sola, decirselo suena raro y va directo a satisfaccion.
        conv = _conv("2.4.0.1.20.1")
        conv.flow_answers["trx_cantidad"] = "2"
        conv.captured_data["trx_index"] = "2"
        _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.1.20.2")

    def test_single_tx_skips_close_message(self) -> None:
        conv = _conv("2.4.0.1.20.1")
        conv.flow_answers["trx_cantidad"] = "1"
        conv.captured_data["trx_index"] = "1"
        _prefetch(conv)
        self.assertEqual(conv.current_step, "satisfaction_check")

    def test_pending_tx_keeps_loop_node(self) -> None:
        conv = _conv("2.4.0.1.20.1")
        conv.flow_answers["trx_cantidad"] = "3"
        conv.captured_data["trx_index"] = "1"
        _prefetch(conv)
        self.assertEqual(conv.current_step, "2.4.0.1.20.1")


class TrxVigenciaTests(unittest.TestCase):
    def test_old_date_visa_vencida(self) -> None:
        self.assertTrue(cs._trx_vigencia_vencida("01/01/2000", "VISA"))

    def test_today_is_vigente(self) -> None:
        hoy = datetime.now().strftime("%d/%m/%Y")
        self.assertFalse(cs._trx_vigencia_vencida(hoy, "VISA"))

    def test_invalid_date_not_vencida(self) -> None:
        self.assertFalse(cs._trx_vigencia_vencida("no-fecha", "MASTER"))


class TrxLoopHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_si_siguiente_advances_index_and_resets(self) -> None:
        conv = _conv("2.4.0.1.20.1")
        conv.flow_answers["trx_cantidad"] = "2"
        conv.captured_data["trx_index"] = "1"
        conv.flow_answers["producto_trx_no_reconocida"] = "producto_1"
        conv.flow_answers["trx_fecha"] = "06/08/2026"
        conv.captured_data["trx_card_id"] = "4912680517940060"
        out = asyncio.run(
            cs._handle_trx_interactive_capture_step(
                conversation=conv,
                user_content="si_siguiente",
                workflow_engine=self.engine,
                trx_service_url=None,
                back_data_service_url=None,
                control_store=None,
            )
        )
        self.assertIsNotNone(out)
        self.assertEqual(conv.current_step, "2.4.0.1.3")
        self.assertEqual(conv.captured_data.get("trx_index"), "2")
        # per-tx state limpiado
        self.assertNotIn("trx_card_id", conv.captured_data)
        self.assertNotIn("trx_fecha", conv.flow_answers)
        self.assertNotIn("producto_trx_no_reconocida", conv.flow_answers)

    def test_confirm_data_step_initializes_index_once(self) -> None:
        conv = _conv("2.4.0.1.3")
        conv.captured_data["trx_index"] = "2"  # ya en la 2a tx
        out = asyncio.run(
            cs._handle_trx_interactive_capture_step(
                conversation=conv,
                user_content="continuar",
                workflow_engine=self.engine,
                trx_service_url=None,
                back_data_service_url=None,
                control_store=None,
            )
        )
        self.assertIsNone(out)
        self.assertEqual(conv.captured_data.get("trx_index"), "2")  # no lo pisa


if __name__ == "__main__":
    unittest.main()


class TrxProductosGateTests(unittest.TestCase):
    """Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit."""

    def _run_con_pan(self, products_response: dict | None) -> Conversation:
        """Como _run pero simulando financial-overview (resolucion del PAN)."""
        from unittest.mock import AsyncMock, patch

        conv = _conv("2.4.0.1.4")
        with patch(
            "application.chat.chat_service.consultar_productos_activos",
            new=AsyncMock(return_value=products_response),
        ), patch(
            "application.chat.chat_service.obtener_card_id",
            new=AsyncMock(return_value={"card_id": "4916555123453399"}),
        ):
            asyncio.run(
                cs._prefetch_trx_data_if_needed(conv, "http://trx.local", None, None)
            )
        return conv

    def _run(self, products_response: dict | None) -> Conversation:
        from unittest.mock import AsyncMock, patch

        conv = _conv("2.4.0.1.4")
        with patch(
            "application.chat.chat_service.consultar_productos_activos",
            new=AsyncMock(return_value=products_response),
        ):
            asyncio.run(
                cs._prefetch_trx_data_if_needed(conv, "http://trx.local", None, None)
            )
        return conv

    def test_not_found_va_al_exit(self) -> None:
        conv = self._run({"status": "not_found", "data": {"products": []}})
        self.assertEqual(conv.current_step, "2.4.0.1.4.exit")
        self.assertEqual(conv.captured_data["trx_products_status"], "not_found")

    def test_error_de_db_va_al_error_sin_mocks(self) -> None:
        # A-1 (fail-closed detras de back_trx): status="error" significa "no
        # pudimos consultar", y eso va a .4.error -- no a .4.exit, que AFIRMA
        # que el cliente no tiene productos. Mandarlo al exit era darle una
        # afirmacion falsa nacida de un fallo de infraestructura.
        conv = self._run(
            {"status": "error", "data": {"products": [], "error": "db_error:OperationalError"}}
        )
        self.assertEqual(conv.current_step, "2.4.0.1.4.error")
        self.assertEqual(conv.captured_data["trx_products_status"], "error")

    def test_back_trx_sin_respuesta_va_al_error_no_al_exit(self) -> None:
        # Fail-closed (costuras): "no tienes productos activos" es una AFIRMACION
        # sobre el cliente y solo vale si el servicio respondio. Si no respondio,
        # se va a .error, no a .exit. Lo que importa para el porton es que en
        # NINGUN caso se queda dentro del flujo real.
        conv = self._run(None)
        self.assertEqual(conv.current_step, "2.4.0.1.4.error")
        self.assertEqual(conv.captured_data["trx_products_status"], "unavailable")

    def test_con_productos_reales_va_al_selector(self) -> None:
        # Costuras resuelve el PAN contra financial-overview antes de pintar el
        # selector (los ultimos 4 que ve el cliente son los del PAN). Se simula
        # esa respuesta; sin ella el gate corta a .error por fail-closed.
        conv = self._run_con_pan(
            {
                "status": "ok",
                "data": {
                    "products": [
                        {
                            "contract_id": "00130067000200943399",
                            "last_four": "3399",
                            "origin_flag": "TDC",
                            "card_brand": "VISA",
                            "product_desc": "Tarjeta de Credito",
                        }
                    ]
                },
            }
        )
        self.assertEqual(conv.current_step, "2.4.0.1.5")

    def test_nunca_aparecen_mocks_4979_4567(self) -> None:
        for resp in (
            {"status": "not_found", "data": {"products": []}},
            {"status": "error", "data": {"products": []}},
            None,
        ):
            conv = self._run(resp)
            raw = conv.captured_data.get("trx_products_result") or ""
            self.assertNotIn("4979", raw)
            self.assertNotIn("4567", raw)

class TrxNavegacionPaginasGateTests(unittest.TestCase):
    """Gate 2.4.0.1.9.nav (04/09): pide la pagina al servicio y reencamina a .9.

    Sabor A: el agente NO rebana; el gate llama movimientos-pagina con la pagina
    destino (actual +/- 1, acotada a [1, total_pages]) y guarda pagina+metadata.
    """

    def _pagina_resp(self, page: int, total: int = 12, total_pages: int = 3):
        inicio = (page - 1) * 5
        movs = [{"id": f"TX{i}", "descripcion": f"COMPRA {i}", "valor": 100000 + i,
                 "fecha": "2026-08-06"} for i in range(inicio + 1, min(inicio + 5, total) + 1)]
        return {
            "status": "ok", "page": page, "page_size": 5, "total": total,
            "total_pages": total_pages, "has_prev": page > 1,
            "has_next": page < total_pages, "fuera_de_rango": 0, "movimientos": movs,
        }

    def _run_nav(self, direction: str, pagina_actual: int, resp):
        from unittest.mock import AsyncMock, patch

        conv = _conv("2.4.0.1.9.nav")
        conv.captured_data["trx_card_id"] = "4916555123453399"
        conv.captured_data["trx_fecha"] = "06/08/2026"
        conv.captured_data["trx_movs_pagina"] = str(pagina_actual)
        conv.captured_data["trx_movs_total_pages"] = "3"
        conv.flow_answers["trx_movimiento_seleccionado"] = direction
        with patch(
            "application.chat.chat_service.movimientos_pagina",
            new=AsyncMock(return_value=resp),
        ) as mock_pag:
            asyncio.run(
                cs._prefetch_trx_data_if_needed(conv, "http://trx.local", None, None)
            )
        return conv, mock_pag

    def test_ver_mas_pide_la_pagina_siguiente_y_reencamina(self) -> None:
        conv, mock_pag = self._run_nav("mas_movimientos", 1, self._pagina_resp(2))
        self.assertEqual(mock_pag.await_args.kwargs["page"], 2)
        self.assertEqual(conv.current_step, "2.4.0.1.9")
        self.assertEqual(conv.captured_data["trx_movs_pagina"], "2")
        self.assertEqual(conv.captured_data["trx_movs_has_prev"], "1")
        self.assertEqual(conv.captured_data["trx_movs_has_next"], "1")
        # la respuesta de navegacion se consume (no re-navega en un re-render)
        self.assertIsNone(conv.flow_answers.get("trx_movimiento_seleccionado"))

    def test_anterior_pide_la_pagina_previa(self) -> None:
        conv, mock_pag = self._run_nav("anterior_movimientos", 2, self._pagina_resp(1))
        self.assertEqual(mock_pag.await_args.kwargs["page"], 1)
        self.assertEqual(conv.current_step, "2.4.0.1.9")
        self.assertEqual(conv.captured_data["trx_movs_has_prev"], "0")

    def test_no_pasa_de_la_ultima_pagina(self) -> None:
        # En la ultima (3 de 3), "Ver mas" no debe pedir page=4: se acota a 3.
        conv, mock_pag = self._run_nav("mas_movimientos", 3, self._pagina_resp(3))
        self.assertEqual(mock_pag.await_args.kwargs["page"], 3)

    def test_fallo_al_navegar_conserva_pagina_y_vuelve_al_selector(self) -> None:
        conv, _ = self._run_nav("mas_movimientos", 1, None)  # servicio no contesta
        self.assertEqual(conv.current_step, "2.4.0.1.9")
        # no se pisa la pagina actual con basura
        self.assertEqual(conv.captured_data["trx_movs_pagina"], "1")


if __name__ == "__main__":
    unittest.main()
