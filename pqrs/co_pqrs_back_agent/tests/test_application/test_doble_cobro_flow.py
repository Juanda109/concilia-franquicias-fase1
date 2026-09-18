"""Golden paths del flujo doble_cobro.

Dos niveles, ambos deterministas (sin LLM):

* ``DobleCobroEngineTests``: rutas estaticas del YAML a nivel de
  ``WorkflowEngine`` (tarjeta de credito, terminales, selector multiple).
* ``DobleCobroGateTests``: los gates del hook con un ``DobleCobroClient``
  falso (reglas: productos, vigencia, grupos) y un ``TrxCaseStore`` falso
  (la ficha del cliente en OpenSearch: recurrencia, registro, confirmacion).
  Cada test fija el estado de la conversacion en la entrada de un gate y
  verifica el paso de salida — incluidos los encadenamientos y los
  fail-closed: si el caso no se pudo escribir o releer nunca se promete un
  abono.

Contrato vigente (ajustes del 7 y 8 de septiembre de 2026):

* El bot NO gestiona estados (PENDIENTE / APROBADO desaparecieron).
* La recurrencia ya NO bloquea: se registra en el log y el flujo continua;
  al registrar, un reporte previo de la misma transaccion (producto + fecha +
  monto) se REEMPLAZA en vez de acumularse.
* En 3.4.0.6 el cliente ve las transacciones sobrantes de cada grupo (N-1 por
  grupo, se conserva la mas antigua) como lista de seleccion multiple, de 6 en
  6, con "Ver mas movimientos" para paginar y "Reportar N cobros" para pasar al
  registro. Solo se registran las transacciones marcadas.
* Ese paso es UNA tarjeta que se repinta: marcar una casilla o cambiar de
  pagina reutiliza el mismo mensaje en vez de encolar otra copia del listado
  (SingleSelectorCardTests).
"""

import asyncio
import json
import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from application.chat import chat_service
from application.chat.actions.doble_cobro import _TRANSACTIONS_PER_PAGE as _PAGE
from infrastructure.core.config import MAX_TRANSACTIONS_PER_PAGE
from application.chat.workflow_actions import execute_workflow_action
from application.chat.workflows import doble_cobro_hook
from application.chat.workflows.doble_cobro_hook import (
    _parse_amount,
    prefetch_doble_cobro,
)
from domain.conversation.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from domain.workflow.workflow_engine import (
    MULTI_SELECT_REFRESH_KEY,
    WorkflowEngine,
)
from infrastructure.persistence.trx_case_store import (
    NOTIFICATION_DOBLE_COBRO,
    NOTIFICATION_TRX_NO_RECONOCIDA,
    TrxCaseStore,
)

_CLIENT_ID = "7667553"
_DATE = "2026-08-28"

_PRODUCT_SAVING = {
    "product_id": "00130766000200022384",
    "contract_id": "00130766000200022384",
    "commercial_product_desc": "Cuenta de ahorro",
    "last_four": "2384",
    "product_type": "ACCOUNT",
    "card_brand": "",
}

_PRODUCT_CARD = {
    "product_id": "4912684136504818",
    "contract_id": "4912684136504818",
    "card_id": "4912684136504818",
    "commercial_product_desc": "Tarjeta débito",
    "last_four": "4818",
    "product_type": "CARD",
    "card_brand": "VISA",
}


def _movement(movement_id: str, hour: str) -> dict[str, Any]:
    return {
        "id": movement_id,
        "operation_time": f"{_DATE}T{hour}:00",
        "raw": {"movementId": movement_id},
    }


def _flatten(groups: list[dict]) -> list[dict[str, Any]]:
    """Grupos -> lista plana de movimientos, tal como responde el servicio.

    El comercio y el importe viven en el grupo porque en un doble cobro son
    identicos para todos sus cargos; al aplanar se copian a cada movimiento.
    """

    return [
        {
            "id": movement["id"],
            "merchant": group["merchant"],
            "amount": group["amount"],
            "time": movement["operation_time"].split("T")[1][:5],
            "raw": movement.get("raw") or {},
        }
        for group in groups
        for movement in group["movements"]
    ]


def _group(group_id: str, merchant: str, amount: float, movements: list[dict]) -> dict:
    return {
        "group_id": group_id,
        "merchant": merchant,
        "amount": amount,
        "count": len(movements),
        "first_seen": movements[0]["operation_time"],
        "last_seen": movements[-1]["operation_time"],
        "movement_ids": [m["id"] for m in movements],
        "movements": movements,
    }


# g-1: par (1 legitimo + 1 duplicado). g-2: triple (1 legitimo + 2 duplicados).
# Aplanado en 3.4.0.6 son TRES transacciones: m-2, m-8, m-9.
_GROUPS = [
    _group(
        "g-1",
        "EXITO CALLE 80",
        145000.0,
        [_movement("m-1", "10:15"), _movement("m-2", "10:19")],
    ),
    _group(
        "g-2",
        "DROGUERIA CENTRAL",
        52000.0,
        [_movement("m-7", "16:00"), _movement("m-8", "16:04"), _movement("m-9", "18:30")],
    ),
]


def _many_groups(pairs: int) -> list[dict]:
    """``pairs`` parejas de cobros, o sea ``pairs * 2`` movimientos.

    Se usa para armar listados largos y probar la paginacion de 6 en 6.
    """

    return [
        _group(
            f"g-{i}",
            f"COMERCIO {i}",
            1000.0 * i,
            [_movement(f"a-{i}", "09:00"), _movement(f"b-{i}", "09:05")],
        )
        for i in range(1, pairs + 1)
    ]


def _reported_item(product: dict, amount: float, date: str = _DATE, tx_id: str = "prev-1") -> dict:
    """Un item ya guardado en la ficha, con la forma que escribe el hook."""

    return {
        "contrato": product["contract_id"],
        "numero_tarjeta": product.get("card_id", ""),
        "fecha_trx": date,
        "movimiento_valor": amount,
        "tx_id": tx_id,
    }


class FakeDobleCobroClient:
    """Respuestas del servicio :8006 fijadas por test. Registra las llamadas."""

    def __init__(
        self,
        *,
        products: list[dict] | None = None,
        validity: dict | None = None,
        groups: list[dict] | None = None,
    ) -> None:
        self._products = products
        self._validity = validity
        self._groups = groups
        self.calls: list[str] = []

    async def consultar_productos(self, **_: object) -> dict | None:
        self.calls.append("productos")
        if self._products is None:
            return None
        return {"data": {"products": self._products}}

    async def validar_vigencia(self, **_: object) -> dict | None:
        self.calls.append("vigencia")
        if self._validity is None:
            return None
        return {"data": self._validity}

    async def buscar_grupos(self, **_: object) -> dict | None:
        """Devuelve TODOS los movimientos del rango, que es el contrato real.

        Los fixtures se siguen escribiendo como grupos porque asi se lee de
        un vistazo cual pareja es el cobro duplicado, pero el servicio ya no
        decide la agrupacion: entrega la lista plana y es el cliente quien
        marca los cargos en 3.4.0.6.
        """

        self.calls.append("grupos")
        return {"data": {"transactions": _flatten(self._groups or [])}}


class FakeTrxCaseStore:
    """Ficha del cliente en memoria, con la misma interfaz que ``TrxCaseStore``.

    Indexa por el ``document_id`` REAL del store, para que el test compruebe la
    regla de no-colision entre flujos (doble cobro con prefijo, TXNR sin el).
    ``fail_reads_from`` hace fallar las lecturas a partir de esa posicion
    (1 = la primera) y ``fail_writes`` hace fallar toda escritura.
    """

    def __init__(
        self,
        *,
        fail_reads_from: int | None = None,
        fail_writes: bool = False,
    ) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.reads = 0
        self.writes: list[dict[str, Any]] = []
        self._fail_reads_from = fail_reads_from
        self._fail_writes = fail_writes

    # -- helpers de test ----------------------------------------------------

    def seed(self, tipo: str, items: list[dict], client_id: str = _CLIENT_ID) -> None:
        doc_id = TrxCaseStore.document_id(client_id, tipo)
        self.records[doc_id] = {
            "client_id": client_id,
            "tipo_de_notificacion": tipo,
            "trx_case_state_snapshot": {"tantia_items": list(items)},
        }

    def items(self, tipo: str, client_id: str = _CLIENT_ID) -> list[dict]:
        doc_id = TrxCaseStore.document_id(client_id, tipo)
        record = self.records.get(doc_id) or {}
        return (record.get("trx_case_state_snapshot") or {}).get("tantia_items") or []

    # -- interfaz de TrxCaseStore -------------------------------------------

    async def get_case(
        self,
        client_id: str,
        *,
        tipo_de_notificacion: str = NOTIFICATION_TRX_NO_RECONOCIDA,
    ) -> dict | None:
        self.reads += 1
        if self._fail_reads_from is not None and self.reads >= self._fail_reads_from:
            raise RuntimeError("opensearch down (read)")
        return self.records.get(TrxCaseStore.document_id(client_id, tipo_de_notificacion))

    async def record_milestone(
        self,
        *,
        client_id: str,
        conversation_id: str,
        milestone: str,
        snapshot: dict | None = None,
        outcome: str | None = None,
        tipo_de_notificacion: str = NOTIFICATION_TRX_NO_RECONOCIDA,
        **_: object,
    ) -> None:
        if self._fail_writes:
            raise RuntimeError("opensearch down (write)")
        doc_id = TrxCaseStore.document_id(client_id, tipo_de_notificacion)
        record = self.records.get(doc_id) or {"milestones": []}
        record.update(
            {
                "client_id": client_id,
                "tipo_de_notificacion": tipo_de_notificacion,
                "conversation_id": conversation_id,
                "milestones": [*record.get("milestones", []), milestone],
                "outcome": outcome,
            }
        )
        if snapshot is not None:
            record["trx_case_state_snapshot"] = snapshot
        self.records[doc_id] = record
        self.writes.append({"doc_id": doc_id, "milestone": milestone, "outcome": outcome})


class _MessageStore:
    """Store minimo con la semantica de OpenSearch: indexar por id es un upsert."""

    def __init__(self) -> None:
        self.documents: dict[str, str] = {}
        self.deleted: list[str] = []

    async def save_message(self, conversation_id: str, message) -> None:
        del conversation_id
        self.documents[message.id] = message.content

    async def delete_message(self, conversation_id: str, message_id: str) -> None:
        del conversation_id
        self.deleted.append(message_id)
        self.documents.pop(message_id, None)

    async def refresh(self) -> None:
        return None

    async def save_conversation_reference(self, conversation) -> None:
        del conversation


def _conversation(step: str = "3.4.0") -> Conversation:
    return Conversation(
        conversation_id=f"{_CLIENT_ID}_20260905",
        status=ConversationStatus.ACTIVE,
        current_step=step,
        general_workflow="Duplicidad en el cobro o doble cobro",
        workflow="doble_cobro",
        flow_version=1,
        user_id=_CLIENT_ID,
    )


def _with_product(conv: Conversation, product: dict) -> None:
    conv.captured_data["doble_cobro_products_map"] = json.dumps([product])
    conv.flow_answers["doble_cobro_producto"] = "producto_1"


def _selected(conv: Conversation) -> list[str]:
    return json.loads(conv.captured_data.get("dc_transactions_selected") or "[]")


def _transactions(conv: Conversation) -> list[dict]:
    return json.loads(conv.captured_data.get("dc_transactions") or "[]")


def _run_hook(
    conv: Conversation,
    fake: FakeDobleCobroClient | None = None,
    store: FakeTrxCaseStore | None = None,
) -> None:
    client = fake or FakeDobleCobroClient()
    case_store = store or FakeTrxCaseStore()
    with (
        patch.object(doble_cobro_hook, "DobleCobroClient", lambda: client),
        patch.object(doble_cobro_hook, "TrxCaseStore", lambda: case_store),
    ):
        asyncio.run(prefetch_doble_cobro(conv))


# ---------------------------------------------------------------------------
# Rutas estaticas del YAML
# ---------------------------------------------------------------------------


class DobleCobroEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_entry_step_offers_three_families(self) -> None:
        conv = _conversation()
        self.assertIsNotNone(self.engine.render_current_step_prompt(conv))
        _, step = self.engine.get_current_step(conv)
        self.assertEqual(
            {option.key for option in step.options},
            {"SAVING", "CHECKING", "CREDIT_CARD"},
        )

    def test_credit_card_goes_to_pqr_form_and_satisfaction(self) -> None:
        conv = _conversation()
        response = self.engine.generate_response(conv, "CREDIT_CARD")
        self.assertEqual(conv.current_step, "3.4.0.pqr_tarjeta_credito")
        self.assertIn("formulario", response.lower())
        self.engine.generate_response(conv, "pqr")
        self.assertEqual(conv.current_step, "satisfaction_check")

    def test_terminal_steps_are_terminal(self) -> None:
        for step_id in (
            "3.4.0.3.pendiente",
            "3.4.0.8.pendiente",
            "3.4.0.8.no_procede",
        ):
            conv = _conversation(step_id)
            _, step = self.engine.get_current_step(conv)
            self.assertEqual(step.input_type, "terminal", step_id)

    def test_approved_terminals_no_longer_exist(self) -> None:
        """El bot no gestiona estados: no puede decir que un caso fue aprobado."""

        for step_id in ("3.4.0.5.aprobado", "3.4.0.8.aprobado"):
            conv = _conversation(step_id)
            self.assertIsNone(self.engine.get_current_step(conv), step_id)

    def test_transaction_selector_is_multi_select_with_paging_and_report(self) -> None:
        """3.4.0.6: seleccion multiple, paginar, reportar o no encontrar.

        El YAML declara ``MAX_TRANSACTIONS_PER_PAGE`` posiciones fijas porque
        el tamano de pagina es configurable: deben alcanzar para el maximo.
        """

        conv = _conversation("3.4.0.6")
        _, step = self.engine.get_current_step(conv)
        self.assertEqual(step.input_type, "multi_select")
        self.assertEqual(step.save_as, "doble_cobro_trx_seleccion")
        by_key = {option.key: option.next_step for option in step.options}
        self.assertEqual(
            [key for key in by_key if key.startswith("transaccion_")],
            [f"transaccion_{i}" for i in range(1, MAX_TRANSACTIONS_PER_PAGE + 1)],
        )
        self.assertEqual(by_key["mas_movimientos"], "3.4.0.6")
        self.assertEqual(by_key["reportar_seleccionados"], "3.4.0.7")
        self.assertEqual(by_key["no_encuentro"], "3.4.0.6.pqr")

    def test_no_procede_never_promises_a_credit(self) -> None:
        """El terminal por defecto no puede contener promesa de abono."""

        conv = _conversation("3.4.0.8.no_procede")
        prompt = (self.engine.render_current_step_prompt(conv) or "").lower()
        self.assertNotIn("abono a tu cuenta", prompt)
        self.assertNotIn("verás reflejado el dinero", prompt)


# ---------------------------------------------------------------------------
# Entradas libres (capa C3): el monto llega como lo escribio el cliente
# ---------------------------------------------------------------------------


class ParseAmountTests(unittest.TestCase):
    """El YAML pide "solo numeros"; el cliente escribe con $ y puntos igual."""

    def test_variants_reach_the_same_amount(self) -> None:
        for raw, expected in (
            ("50000", 50000.0),        # como pide el YAML
            ("50.000", 50000.0),       # punto de miles colombiano
            ("$50.000", 50000.0),
            ("$ 145.000", 145000.0),
            ("1.145.000", 1145000.0),  # varios grupos de miles
            ("50,000", 50000.0),       # coma de miles (formato gringo)
            ("145000.50", 145000.5),   # decimal real (2 digitos, no grupo)
            (" 145000 ", 145000.0),
        ):
            self.assertEqual(_parse_amount(raw), expected, raw)

    def test_unparseable_input_is_zero_not_crash(self) -> None:
        for raw in ("cincuenta mil", "", None, "$."):
            self.assertEqual(_parse_amount(raw), 0.0, repr(raw))


# ---------------------------------------------------------------------------
# Gates del hook
# ---------------------------------------------------------------------------


class DobleCobroGateTests(unittest.TestCase):
    # ----- 3.4.0.1: productos -----

    def test_products_found_stay_on_selector(self) -> None:
        conv = _conversation("3.4.0.1")
        conv.flow_answers["doble_cobro_familia"] = "SAVING"
        _run_hook(conv, FakeDobleCobroClient(products=[_PRODUCT_SAVING]))
        self.assertEqual(conv.current_step, "3.4.0.1")
        self.assertIn("dc_products_result", conv.captured_data)

    def test_no_products_reroutes_to_pqr(self) -> None:
        conv = _conversation("3.4.0.1")
        conv.flow_answers["doble_cobro_familia"] = "SAVING"
        _run_hook(conv, FakeDobleCobroClient(products=[]))
        self.assertEqual(conv.current_step, "3.4.0.1.pqr")

    # ----- 3.4.0.3: vigencia -----

    def _validity_conv(self) -> Conversation:
        conv = _conversation("3.4.0.3")
        _with_product(conv, _PRODUCT_SAVING)
        conv.flow_answers["doble_cobro_fecha"] = _DATE
        return conv

    def test_validity_ok_advances_to_amount(self) -> None:
        conv = self._validity_conv()
        _run_hook(conv, FakeDobleCobroClient(validity={"outcome": "ok"}))
        self.assertEqual(conv.current_step, "3.4.0.4")

    def test_settlement_pending_terminates_with_dynamic_days(self) -> None:
        conv = self._validity_conv()
        _run_hook(
            conv,
            FakeDobleCobroClient(
                validity={"outcome": "settlement_pending", "settlement_days": 7}
            ),
        )
        self.assertEqual(conv.current_step, "3.4.0.3.pendiente")
        self.assertIn(
            "7 días hábiles",
            conv.captured_data["dynamic_prompt_3.4.0.3.pendiente"],
        )

    def test_expired_windows_reroute_to_pqr(self) -> None:
        for outcome in ("report_window_expired", "franchise_expired"):
            conv = self._validity_conv()
            _run_hook(conv, FakeDobleCobroClient(validity={"outcome": outcome}))
            self.assertEqual(conv.current_step, "3.4.0.3.pqr", outcome)

    def test_validity_service_down_fails_closed_to_pqr(self) -> None:
        conv = self._validity_conv()
        _run_hook(conv, FakeDobleCobroClient(validity=None))
        self.assertEqual(conv.current_step, "3.4.0.3.pqr")

    # ----- 3.4.0.5: recurrencia (informativa, ya no bloquea) -----

    def _recurrence_conv(self) -> Conversation:
        conv = _conversation("3.4.0.5")
        _with_product(conv, _PRODUCT_SAVING)
        conv.flow_answers["doble_cobro_fecha"] = _DATE
        conv.flow_answers["doble_cobro_monto"] = "145000"
        return conv

    def test_previous_report_no_longer_blocks_the_flow(self) -> None:
        """Ajuste del 8-sep: con reporte previo se continua igual a los grupos."""

        conv = self._recurrence_conv()
        store = FakeTrxCaseStore()
        store.seed(NOTIFICATION_DOBLE_COBRO, [_reported_item(_PRODUCT_SAVING, 145000.0)])
        fake = FakeDobleCobroClient(groups=_GROUPS)
        _run_hook(conv, fake, store)
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertEqual(fake.calls, ["grupos"])
        self.assertEqual(store.reads, 1)  # se consulta, aunque no decida

    def test_report_from_other_flow_is_not_read_as_doble_cobro(self) -> None:
        """La ficha de TXNR del mismo cliente no se confunde con la de doble cobro."""

        conv = self._recurrence_conv()
        store = FakeTrxCaseStore()
        store.seed(NOTIFICATION_TRX_NO_RECONOCIDA, [_reported_item(_PRODUCT_SAVING, 145000.0)])
        _run_hook(conv, FakeDobleCobroClient(groups=_GROUPS), store)
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertEqual(store.items(NOTIFICATION_TRX_NO_RECONOCIDA)[0]["tx_id"], "prev-1")

    def test_clean_client_chains_into_group_search(self) -> None:
        """Sin reporte previo, el mismo turno encadena la busqueda de grupos."""

        conv = self._recurrence_conv()
        fake = FakeDobleCobroClient(groups=_GROUPS)
        store = FakeTrxCaseStore()
        _run_hook(conv, fake, store)
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertEqual(fake.calls, ["grupos"])
        self.assertEqual(len(json.loads(conv.captured_data["dc_movements"])), 5)

    def test_store_unreadable_fails_open_into_group_search(self) -> None:
        """Sin lectura de la ficha no se bloquea al cliente."""

        conv = self._recurrence_conv()
        _run_hook(
            conv,
            FakeDobleCobroClient(groups=_GROUPS),
            FakeTrxCaseStore(fail_reads_from=1),
        )
        self.assertEqual(conv.current_step, "3.4.0.6")

    # ----- 3.4.0.6: transacciones (seleccion multiple + paginacion) -----

    def _groups_conv(self, amount: str = "145000") -> Conversation:
        conv = _conversation("3.4.0.6")
        _with_product(conv, _PRODUCT_CARD)
        conv.flow_answers["doble_cobro_fecha"] = _DATE
        conv.flow_answers["doble_cobro_monto"] = amount
        return conv

    def test_no_groups_reroutes_to_pqr(self) -> None:
        conv = self._groups_conv()
        _run_hook(conv, FakeDobleCobroClient(groups=[]))
        self.assertEqual(conv.current_step, "3.4.0.6.pqr")

    def test_every_movement_in_range_is_offered(self) -> None:
        """Se ofrecen TODOS los movimientos del rango, no solo los sobrantes.

        Es el cliente quien arma la pareja. Antes se mostraba unicamente el
        cargo sobrante, asi que el original quedaba oculto y la pareja venia
        decidida de fabrica.
        """

        conv = self._groups_conv()
        _run_hook(conv, FakeDobleCobroClient(groups=_GROUPS))
        self.assertEqual(conv.current_step, "3.4.0.6")
        transactions = _transactions(conv)
        self.assertEqual(
            [t["movement_id"] for t in transactions],
            ["m-1", "m-2", "m-7", "m-8", "m-9"],
        )
        self.assertEqual(
            [t["selection_id"] for t in transactions],
            [f"transaccion_{n}" for n in range(1, 6)],
        )
        self.assertEqual(transactions[0]["merchant"], "EXITO CALLE 80")
        self.assertEqual(transactions[0]["amount"], 145000.0)
        self.assertEqual(transactions[0]["last_four"], "4818")
        self.assertEqual(conv.captured_data["dc_transactions_page"], "0")
        self.assertEqual(_selected(conv), [])

    def test_a_lone_charge_is_still_offered(self) -> None:
        """Un cargo suelto se muestra igual, no se descarta por adelantado.

        Que forme o no una pareja se decide al reportar (3.4.0.7), avisando
        al cliente cual quedo fuera. Solo se desvia a PQR cuando el rango no
        devuelve ningun movimiento.
        """

        singles = [_group("g-1", "EXITO CALLE 80", 145000.0, [_movement("m-1", "10:15")])]
        conv = self._groups_conv()
        _run_hook(conv, FakeDobleCobroClient(groups=singles))
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertEqual(len(_transactions(conv)), 1)

    def test_transaction_click_toggles_selection_on_and_off(self) -> None:
        conv = self._groups_conv()
        fake = FakeDobleCobroClient(groups=_GROUPS)
        _run_hook(conv, fake)

        conv.flow_answers["doble_cobro_trx_seleccion"] = "transaccion_2"
        _run_hook(conv, fake)
        self.assertEqual(_selected(conv), ["transaccion_2"])
        self.assertNotIn("doble_cobro_trx_seleccion", conv.flow_answers)  # clic consumido

        conv.flow_answers["doble_cobro_trx_seleccion"] = "transaccion_3"
        _run_hook(conv, fake)
        self.assertEqual(_selected(conv), ["transaccion_2", "transaccion_3"])

        conv.flow_answers["doble_cobro_trx_seleccion"] = "transaccion_2"
        _run_hook(conv, fake)
        self.assertEqual(_selected(conv), ["transaccion_3"])
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertEqual(fake.calls, ["grupos"])  # los grupos se consultan una sola vez

    def test_unknown_transaction_click_is_ignored(self) -> None:
        conv = self._groups_conv()
        fake = FakeDobleCobroClient(groups=_GROUPS)
        _run_hook(conv, fake)
        conv.flow_answers["doble_cobro_trx_seleccion"] = "transaccion_9"
        _run_hook(conv, fake)
        self.assertEqual(_selected(conv), [])

    def test_more_movements_pages_forward_and_stops_at_the_last_page(self) -> None:
        """Dos paginas justas: un clic avanza a la 1 y el segundo no pasa de ahi."""

        conv = self._groups_conv()
        fake = FakeDobleCobroClient(groups=_many_groups(_PAGE))
        _run_hook(conv, fake)
        self.assertEqual(len(_transactions(conv)), _PAGE * 2)
        self.assertEqual(conv.captured_data["dc_transactions_page"], "0")

        conv.flow_answers["doble_cobro_trx_seleccion"] = "mas_movimientos"
        _run_hook(conv, fake)
        self.assertEqual(conv.captured_data["dc_transactions_page"], "1")

        conv.flow_answers["doble_cobro_trx_seleccion"] = "mas_movimientos"
        _run_hook(conv, fake)
        self.assertEqual(conv.captured_data["dc_transactions_page"], "1")

    def test_changed_query_refetches_groups_and_resets_selection(self) -> None:
        """Si el cliente cambia el monto, se vuelve a buscar y la seleccion se descarta."""

        conv = self._groups_conv(amount="145000")
        fake = FakeDobleCobroClient(groups=_GROUPS)
        _run_hook(conv, fake)
        conv.flow_answers["doble_cobro_trx_seleccion"] = "transaccion_1"
        _run_hook(conv, fake)
        self.assertEqual(_selected(conv), ["transaccion_1"])

        conv.flow_answers["doble_cobro_monto"] = "52000"
        _run_hook(conv, fake)
        self.assertEqual(fake.calls, ["grupos", "grupos"])
        self.assertEqual(_selected(conv), [])
        self.assertEqual(conv.captured_data["dc_transactions_page"], "0")

    # ----- 3.4.0.7 y 3.4.0.8: registro y confirmacion (encadenados) -----

    def _register_conv(
        self,
        selected: list[str],
        groups: list[dict] | None = None,
        product: dict = _PRODUCT_SAVING,
    ) -> Conversation:
        conv = _conversation("3.4.0.7")
        _with_product(conv, product)
        conv.flow_answers["doble_cobro_fecha"] = _DATE
        groups = _GROUPS if groups is None else groups
        movements = _flatten(groups)
        conv.captured_data["dc_movements"] = json.dumps(movements)
        conv.captured_data["dc_transactions"] = json.dumps(
            doble_cobro_hook._build_transactions(conv, movements, product=product)
        )
        conv.captured_data["dc_transactions_selected"] = json.dumps(selected)
        # Como lo deja 3.4.0.6 tras la busqueda: firma y pagina, para que un
        # regreso a los grupos no dispare una busqueda nueva.
        conv.captured_data["dc_groups_query_signature"] = (
            doble_cobro_hook._groups_query_signature(conv)
        )
        conv.captured_data["dc_transactions_page"] = "0"
        return conv

    def test_register_without_selection_returns_to_groups_with_warning(self) -> None:
        conv = self._register_conv([])
        store = FakeTrxCaseStore()
        _run_hook(conv, store=store)
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertIn("dc_groups_warning", conv.captured_data)
        self.assertEqual(store.writes, [])

    def test_register_writes_only_the_selected_transactions_and_confirms_pending(self) -> None:
        """Marcadas las dos parejas (m-1/m-2 y m-8/m-9): m-7 queda sin reportar.

        De cada grupo se guarda una sola fila, el cargo repetido: negocio
        revisa el caso mirando los movimientos del cliente.
        """

        conv = self._register_conv(
            ["transaccion_1", "transaccion_2", "transaccion_4", "transaccion_5"]
        )
        store = FakeTrxCaseStore()
        _run_hook(conv, store=store)

        self.assertEqual(conv.current_step, "3.4.0.8.pendiente")
        self.assertEqual(len(store.writes), 1)
        self.assertEqual(store.writes[0]["doc_id"], f"doble_cobro_{_CLIENT_ID}")
        items = store.items(NOTIFICATION_DOBLE_COBRO)
        self.assertEqual([item["tx_id"] for item in items], ["m-2", "m-9"])
        first = items[0]
        self.assertEqual(first["contrato"], _PRODUCT_SAVING["contract_id"])
        self.assertEqual(first["fecha_trx"], _DATE)
        self.assertEqual(first["movimiento_valor"], 145000.0)
        self.assertEqual(first["movimiento_descripcion"], "EXITO CALLE 80")
        self.assertEqual(first["evento"], "doble_cobro")
        self.assertEqual(conv.captured_data["dc_case_items"], "2")

    def test_register_replaces_a_previous_report_of_the_same_transaction(self) -> None:
        """Ajuste del 8-sep: mismo producto + fecha + monto se sobreescribe, el resto se conserva."""

        conv = self._register_conv(["transaccion_1", "transaccion_2"])  # 145000 en EXITO
        store = FakeTrxCaseStore()
        store.seed(
            NOTIFICATION_DOBLE_COBRO,
            [
                _reported_item(_PRODUCT_SAVING, 145000.0, tx_id="viejo-145"),
                _reported_item(_PRODUCT_SAVING, 99000.0, tx_id="viejo-99"),
                _reported_item(_PRODUCT_SAVING, 145000.0, date="2026-08-27", tx_id="viejo-otro-dia"),
            ],
        )
        _run_hook(conv, store=store)

        self.assertEqual(conv.current_step, "3.4.0.8.pendiente")
        tx_ids = [item["tx_id"] for item in store.items(NOTIFICATION_DOBLE_COBRO)]
        self.assertEqual(tx_ids, ["viejo-99", "viejo-otro-dia", "m-2"])
        self.assertEqual(conv.captured_data["dc_case_items"], "3")

    def test_register_does_not_touch_the_trx_case_of_the_same_client(self) -> None:
        """Los dos flujos comparten indice: el prefijo del id evita pisarse."""

        conv = self._register_conv(["transaccion_1", "transaccion_2"])
        store = FakeTrxCaseStore()
        trx_items = [_reported_item(_PRODUCT_CARD, 300000.0)]
        store.seed(NOTIFICATION_TRX_NO_RECONOCIDA, trx_items)
        _run_hook(conv, store=store)

        self.assertEqual(conv.current_step, "3.4.0.8.pendiente")
        self.assertEqual(store.items(NOTIFICATION_TRX_NO_RECONOCIDA), trx_items)
        self.assertEqual(len(store.items(NOTIFICATION_DOBLE_COBRO)), 1)
        self.assertEqual(set(store.records), {_CLIENT_ID, f"doble_cobro_{_CLIENT_ID}"})

    def test_register_with_an_invalid_selection_never_promises_a_credit(self) -> None:
        """Una seleccion que no corresponde a ninguna transaccion no reporta nada.

        Equivale a no haber marcado nada: se vuelve al listado con el aviso
        en vez de cerrar la conversacion, pero jamas se promete un abono.
        """

        conv = self._register_conv(["transaccion_9"])
        store = FakeTrxCaseStore()
        _run_hook(conv, store=store)
        self.assertEqual(conv.current_step, "3.4.0.6")
        self.assertIn("dc_groups_warning", conv.captured_data)
        self.assertEqual(store.writes, [])

    def test_register_write_failure_fails_closed(self) -> None:
        """Si la ficha no se pudo escribir, nunca se promete abono."""

        conv = self._register_conv(["transaccion_1", "transaccion_2"])
        _run_hook(conv, store=FakeTrxCaseStore(fail_writes=True))
        self.assertEqual(conv.current_step, "3.4.0.8.no_procede")

    def test_unreadable_case_after_write_fails_closed(self) -> None:
        """Escrito pero ilegible al releer: nunca se promete abono."""

        conv = self._register_conv(["transaccion_1", "transaccion_2"])
        # Lectura 1: cargar lo ya reportado (ok). Lectura 2: la confirmacion (falla).
        store = FakeTrxCaseStore(fail_reads_from=2)
        _run_hook(conv, store=store)
        self.assertEqual(len(store.writes), 1)
        self.assertEqual(conv.current_step, "3.4.0.8.no_procede")

    @unittest.expectedFailure
    def test_registered_case_is_exportable_to_tantia(self) -> None:
        """DEUDA (8-sep): el CronJob co_pqrs_back_trx_tantia_export solo exporta fichas con
        ``outcome == "devolucion"`` y ``"completed_report"`` en milestones, y el CSV usa
        ``origin_flag`` TDC/PASIVO. El ajuste del 8-sep escribe "reported"/"reported" y
        "card"/"account", asi que los casos de doble cobro dejan de salir hacia Tantia.
        Cuando se alinee el hook (o el job) este test pasara y hay que quitar el decorador.
        """

        conv = self._register_conv(["transaccion_1", "transaccion_2"])
        store = FakeTrxCaseStore()
        _run_hook(conv, store=store)
        self.assertEqual(store.writes[0]["milestone"], "completed_report")
        self.assertEqual(store.writes[0]["outcome"], "devolucion")
        self.assertEqual(store.items(NOTIFICATION_DOBLE_COBRO)[0]["origin_flag"], "PASIVO")


# ---------------------------------------------------------------------------
# Paso multi_select 3.4.0.6: toggle, paginacion y payload que ve el front
# ---------------------------------------------------------------------------

_CHECKED = "☑"
_UNCHECKED = "☐"

# Dos paginas llenas, sea cual sea el tamano configurado en la bandera: el
# listado no puede depender del .env de quien corre las pruebas.
_PAGED_GROUPS = _many_groups(_PAGE)


class DobleCobroMultiSelectTests(unittest.TestCase):
    """El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina.

    Un clic entra por ``generate_response`` (motor), el hook aplica el toggle
    o la paginacion y la accion vuelve a pintar el listado, que es el mismo
    orden que sigue ``chat_service`` en un turno real.
    """

    def setUp(self) -> None:
        self.engine = WorkflowEngine()
        self.conv = _conversation("3.4.0.6")
        _with_product(self.conv, _PRODUCT_SAVING)
        self.conv.flow_answers["doble_cobro_fecha"] = _DATE
        self._repaint()

    def _repaint(self) -> None:
        _run_hook(self.conv, FakeDobleCobroClient(groups=_PAGED_GROUPS))
        current = self.engine.get_current_step(self.conv)
        if current is not None:
            execute_workflow_action(conversation=self.conv, step=current[1])

    def _click(self, option_key: str) -> None:
        self.engine.generate_response(self.conv, option_key)
        self._repaint()

    def _options(self) -> list:
        from infrastructure.entrypoint.api.router.v0.chat_router import (
            _build_message_content,
        )

        return _build_message_content(
            conversation=self.conv,
            assistant_content=self.conv.captured_data.get(
                "dynamic_prompt_3.4.0.6"
            )
            or "",
            workflow_engine=self.engine,
        ).options

    def _selected(self) -> list[str]:
        return json.loads(
            self.conv.captured_data.get("dc_transactions_selected") or "[]"
        )

    def test_the_first_page_is_full_and_shows_the_pager(self) -> None:
        self.assertEqual(
            [option.key for option in self._options()],
            [f"transaccion_{n}" for n in range(1, _PAGE + 1)]
            + ["mas_movimientos", "reportar_seleccionados", "no_encuentro"],
        )

    def test_click_toggles_the_box_on_and_off(self) -> None:
        self._click("transaccion_2")
        self.assertEqual(self._selected(), ["transaccion_2"])
        self.assertTrue(self._options()[1].label.startswith(_CHECKED))

        self._click("transaccion_2")
        self.assertEqual(self._selected(), [])
        self.assertTrue(self._options()[1].label.startswith(_UNCHECKED))

    def test_selection_survives_pagination(self) -> None:
        self._click("transaccion_2")
        self._click("mas_movimientos")

        self.assertEqual(self.conv.current_step, "3.4.0.6")
        self.assertEqual(
            [option.key for option in self._options()],
            [f"transaccion_{n}" for n in range(_PAGE + 1, _PAGE * 2 + 1)]
            + ["pagina_anterior", "reportar_seleccionados", "no_encuentro"],
        )

        # La segunda de esta pagina: la casilla marcada en la pagina anterior
        # sigue marcada y esta no altera a las demas.
        segunda = f"transaccion_{_PAGE + 2}"
        self._click(segunda)
        self.assertEqual(
            sorted(self._selected(), key=lambda k: int(k.split("_")[1])),
            ["transaccion_2", segunda],
        )
        marcas = [option.label[0] for option in self._options()[:_PAGE]]
        self.assertEqual(marcas.count(_CHECKED), 1)
        self.assertEqual(marcas[1], _CHECKED)

    def test_report_button_carries_the_count(self) -> None:
        """El conteo va en la etiqueta: es lo unico que ve el front."""

        # Tras las transacciones de la pagina va "mas_movimientos", y luego este.
        reportar = _PAGE + 1
        self.assertEqual(self._options()[reportar].label, "Reportar seleccionados")

        self._click("transaccion_1")
        self.assertEqual(self._options()[reportar].label, "Reportar 1 cobro")

        self._click("transaccion_3")
        self.assertEqual(self._options()[reportar].label, "Reportar 2 cobros")

    def test_only_the_final_actions_leave_the_step(self) -> None:
        self._click("transaccion_1")
        self.assertEqual(self.conv.current_step, "3.4.0.6")

        self.engine.generate_response(self.conv, "reportar_seleccionados")
        self.assertEqual(self.conv.current_step, "3.4.0.7")

    def test_not_found_goes_to_the_pqr_form(self) -> None:
        self.engine.generate_response(self.conv, "no_encuentro")
        self.assertEqual(self.conv.current_step, "3.4.0.6.pqr")

    def test_a_box_or_a_page_is_flagged_as_a_repaint(self) -> None:
        """La marca del turno: repintar la tarjeta en vez de encolar otra."""

        for option_key in ("transaccion_1", "mas_movimientos"):
            self.engine.generate_response(self.conv, option_key)
            self.assertEqual(
                self.conv.captured_data.get(MULTI_SELECT_REFRESH_KEY),
                "true",
                option_key,
            )
            self._repaint()

    def test_leaving_the_step_is_not_a_repaint(self) -> None:
        self.engine.generate_response(self.conv, "reportar_seleccionados")
        self.assertNotIn(MULTI_SELECT_REFRESH_KEY, self.conv.captured_data)

    def test_an_unmatched_option_is_not_a_repaint(self) -> None:
        """Sin opcion valida no se pisa la tarjeta: el aviso es un turno normal."""

        self.engine.generate_response(self.conv, "zzz_no_existe")
        self.assertNotIn(MULTI_SELECT_REFRESH_KEY, self.conv.captured_data)


class SingleSelectorCardTests(unittest.IsolatedAsyncioTestCase):
    """El selector es UNA tarjeta que se repinta, no un mensaje por clic.

    Se prueba sobre _process_message_turn porque el problema no estaba en el
    motor sino en la contabilidad del turno: cada clic agregaba un par
    usuario/asistente al historial y el listado aparecia duplicado.
    """

    def _conversation(self) -> Conversation:
        conv = _conversation("3.4.0.6")
        conv.add_message(
            Message(
                id="card-1",
                role=MessageRole.ASSISTANT,
                content="Encontre estas transacciones duplicadas. (0 seleccionadas)",
                tokens=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                timing=MessageTiming(received_at=datetime.now(UTC)),
            )
        )
        return conv

    async def _turn(self, conv: Conversation, *, repaint: bool) -> _MessageStore:
        store = _MessageStore()

        async def _resolver(**kwargs):
            conversation = kwargs["conversation"]
            if repaint:
                conversation.captured_data[MULTI_SELECT_REFRESH_KEY] = "true"
            return (
                "Encontre estas transacciones duplicadas. (1 seleccionada)",
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )

        with patch.object(chat_service, "_resolve_assistant_content", new=_resolver):
            await chat_service._process_message_turn(
                conversation=conv,
                content="transaccion_1",
                store=store,
                workflow_engine=object(),
                strands_agent=object(),
            )
        return store

    async def test_a_click_repaints_the_card_instead_of_adding_one(self) -> None:
        conv = self._conversation()
        store = await self._turn(conv, repaint=True)

        # Una sola tarjeta, la misma de antes, con el contenido nuevo.
        self.assertEqual([message.id for message in conv.messages], ["card-1"])
        self.assertIn("1 seleccionada", conv.messages[0].content)

        # Y en el indice tampoco quedan copias ni el clic.
        self.assertEqual(list(store.documents), ["card-1"])

    async def test_the_click_is_not_left_behind_in_the_index(self) -> None:
        """El clic se guarda por durabilidad antes de saber que era; se retira."""

        conv = self._conversation()
        store = await self._turn(conv, repaint=True)
        self.assertEqual(len(store.deleted), 1)
        self.assertNotIn(store.deleted[0], store.documents)

    async def test_a_real_turn_still_appends_both_messages(self) -> None:
        """Sin la marca no cambia nada: choice/text/date/number siguen igual."""

        conv = self._conversation()
        store = await self._turn(conv, repaint=False)

        roles = [message.role for message in conv.messages]
        self.assertEqual(
            roles,
            [MessageRole.ASSISTANT, MessageRole.USER, MessageRole.ASSISTANT],
        )
        self.assertEqual(store.deleted, [])
        # El clic y la respuesta nueva; "card-1" se sembro sin pasar por el store.
        self.assertEqual(
            sorted(store.documents),
            sorted(message.id for message in conv.messages[1:]),
        )

    async def test_a_repaint_adds_up_the_tokens_of_the_card(self) -> None:
        """Repintar no puede borrar el consumo del turno que genero la tarjeta."""

        conv = self._conversation()
        conv.messages[0].tokens = TokenUsage(
            input_tokens=900, output_tokens=100, total_tokens=1000
        )

        async def _resolver(**kwargs):
            kwargs["conversation"].captured_data[MULTI_SELECT_REFRESH_KEY] = "true"
            return (
                "repintada",
                TokenUsage(input_tokens=5, output_tokens=1, total_tokens=6),
            )

        with patch.object(chat_service, "_resolve_assistant_content", new=_resolver):
            await chat_service._process_message_turn(
                conversation=conv,
                content="transaccion_1",
                store=_MessageStore(),
                workflow_engine=object(),
                strands_agent=object(),
            )

        self.assertEqual(conv.messages[0].tokens.total_tokens, 1006)

    async def test_a_repaint_without_a_previous_card_falls_back_to_appending(self) -> None:
        """Sin tarjeta previa no hay nada que pisar: se agrega, no se pierde."""

        conv = _conversation("3.4.0.6")
        store = await self._turn(conv, repaint=True)

        self.assertEqual(len(conv.messages), 2)
        self.assertEqual(store.deleted, [])


if __name__ == "__main__":
    unittest.main()
