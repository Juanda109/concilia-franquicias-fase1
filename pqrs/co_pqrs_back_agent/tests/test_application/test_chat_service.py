import asyncio
from datetime import datetime, timezone
import json
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Las clases Trx* de este modulo ejercitan el FLUJO REAL de TXNR, que en produccion
# nace CERRADO por el porton de despliegue (TRX_FLOW_ENABLED=false). Se abre aqui
# para probar el flujo; el porton se prueba en test_trx_canary_gate.py.
from application.chat import chat_service as _cs_for_gate

_FLOW_OPEN = patch.object(_cs_for_gate, "_trx_flow_enabled", return_value=True)


def setUpModule() -> None:
    _FLOW_OPEN.start()


def tearDownModule() -> None:
    _FLOW_OPEN.stop()

fake_strands_module = types.ModuleType("strands")


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        pass


fake_strands_module.Agent = _FakeAgent
sys.modules.setdefault("strands", fake_strands_module)

from application.chat.chat_service import (
    _prefetch_back_data_if_needed,
    get_conversation_snapshot,
    process_chat_message,
    process_chat_message_with_timeout,
    _resolve_end_conversation_callback_url,
    process_start_message,
)
from domain.conversation.models import (
    Conversation,
    Message,
    ConversationStatus,
    MessageRole,
    MessageTiming,
    TokenUsage,
)
from domain.genai.llm.models import WorkflowRoutingDecision
from domain.workflow.general_messages import load_general_messages
from domain.workflow.workflow_engine import WorkflowEngine
from infrastructure.entrypoint.api.errors.exceptions import ConflictError


class FakeDailySessionControlStore:
    """Minimal control store stub exposing the daily-session counter API."""

    def __init__(self, *, initial_count: int = 0) -> None:
        self.count = initial_count
        self.record_session_start_call_count = 0
        self.get_record_call_count = 0
        self.blocked_for_day = False

    async def get_record(self, client_id: str) -> dict[str, object]:
        self.get_record_call_count += 1
        return {"client_id": client_id, "count": self.count}

    def is_blocked_for_day(self, record, *, reference_at=None) -> bool:
        return self.blocked_for_day

    def get_daily_session_count(self, record, *, reference_at=None) -> int:
        if not record:
            return 0
        return int(record.get("count", 0))

    async def record_session_start(self, client_id: str, *, interaction_at=None) -> None:
        self.record_session_start_call_count += 1
        self.count += 1


class InMemoryConversationStore:
    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list] = {}
        self.save_conversation_reference_call_count = 0
        self.save_message_call_count = 0
        self.refresh_call_count = 0

    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def save_conversation_reference(self, conversation: Conversation) -> None:
        self.save_conversation_reference_call_count += 1
        self.conversations[conversation.conversation_id] = conversation

    async def save_message(self, conversation_id: str, message) -> None:
        self.save_message_call_count += 1
        self.messages.setdefault(conversation_id, [])
        self.messages[conversation_id] = [
            stored_message
            for stored_message in self.messages[conversation_id]
            if stored_message.id != message.id
        ]
        self.messages[conversation_id].append(message)

    async def refresh(self) -> None:
        self.refresh_call_count += 1
        return None

    async def delete_conversation_messages(self, conversation_id: str) -> None:
        self.messages[conversation_id] = []


class StubStrandsWorkflowAgent:
    def __init__(self) -> None:
        self.route_call_count = 0
        self.final_response_call_count = 0
        self.routing_decision = WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key="guia_rapida",
            workflow="impuesto_4x1000",
            confidence="high",
            rationale="Porque mencionas el cobro del 4x1000 en tu mensaje.",
            assistant_message=(
                "Segun el contexto que me das, entiendo que tu consulta esta "
                "relacionada con el impuesto 4x1000. Creo que el flujo adecuado "
                "para ayudarte a avanzar es Guia rapida -> Impuesto 4x1000, "
                "porque hablas directamente de ese cobro."
            ),
        )

    async def select_groups_with_usage(self, **kwargs):
        # Prefiltro de grupos (dev, 24/08): lista vacia = "sin filtro" -> el
        # ruteo corre con el catalogo completo (fail-open, como el real).
        return [], TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)

    async def route_initial_workflow_with_usage(
        self,
        *,
        conversation,
        user_message: str,
        routing_catalog,
    ) -> tuple[WorkflowRoutingDecision, TokenUsage]:
        self.route_call_count += 1
        return (
            self.routing_decision,
            TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )

    async def generate_final_response_with_usage(
        self,
        *,
        conversation,
        default_message: str,
        closure_mode: str = "resolved_data",
    ) -> tuple[str, TokenUsage]:
        self.final_response_call_count += 1
        return (
            default_message,
            TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )


class SlowStrandsWorkflowAgent(StubStrandsWorkflowAgent):
    def __init__(self, *, delay_seconds: float) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds

    async def route_initial_workflow_with_usage(
        self,
        *,
        conversation,
        user_message: str,
        routing_catalog,
    ) -> tuple[WorkflowRoutingDecision, TokenUsage]:
        await asyncio.sleep(self.delay_seconds)
        return await super().route_initial_workflow_with_usage(
            conversation=conversation,
            user_message=user_message,
            routing_catalog=routing_catalog,
        )


class StubControlStore:
    def __init__(
        self,
        back_data_sequence: list[dict[str, object] | None],
        *,
        stale_back_data: dict[str, object] | None = None,
    ) -> None:
        self.back_data_sequence = list(back_data_sequence)
        self.stale_back_data = stale_back_data
        self.clear_workflow_back_data_call_count = 0
        self.get_record_call_count = 0
        self.run_id = "RUNID"

    async def get_record(self, client_id: str) -> dict[str, object]:
        self.get_record_call_count += 1
        return {"client_id": client_id}

    def get_workflow_back_data(
        self,
        record: dict[str, object] | None,
        workflow_id: str,
    ) -> dict[str, object] | None:
        if self.clear_workflow_back_data_call_count == 0 and self.stale_back_data:
            return self.stale_back_data
        if self.back_data_sequence:
            return self.back_data_sequence.pop(0)
        return None

    def describe_back_data_envelopes(
        self,
        record: dict[str, object] | None,
        workflow_id: str,
        *,
        reference_at: object | None = None,
    ) -> dict[str, object]:
        # Fase 0 (02/09): solo metadatos para la traza de timeout.
        return {"documento_existe": bool(record), "envelopes": {}}

    def get_workflow_back_data_envelope(
        self,
        record: dict[str, object] | None,
        workflow_id: str,
        *,
        reference_at: object | None = None,
        expected_run_id: str | None = None,
    ) -> dict[str, object]:
        # Stale result is served only until it is cleared (mirrors real store).
        if self.clear_workflow_back_data_call_count == 0 and self.stale_back_data:
            return {
                "status": "ok",
                "run_id": "STALE",
                "data": self.stale_back_data,
                "error": None,
            }
        if self.back_data_sequence:
            item = self.back_data_sequence.pop(0)
            if item is None:
                return {"status": "pending", "run_id": None, "data": None, "error": None}
            return {"status": "ok", "run_id": self.run_id, "data": item, "error": None}
        return {"status": "pending", "run_id": None, "data": None, "error": None}

    async def clear_workflow_back_data(
        self,
        *,
        client_id: str,
        workflow_id: str,
        reference_at=None,
    ) -> None:
        self.clear_workflow_back_data_call_count += 1


class ChatServiceFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._previous_bot_name = os.environ.get("BOT_NAME")
        self._previous_end_callback_url = os.environ.get(
            "END_CONVERSATION_CALLBACK_URL"
        )
        os.environ["BOT_NAME"] = "Blue QA"
        os.environ["END_CONVERSATION_CALLBACK_URL"] = ""

    def tearDown(self) -> None:
        if self._previous_bot_name is None:
            os.environ.pop("BOT_NAME", None)
        else:
            os.environ["BOT_NAME"] = self._previous_bot_name

        if self._previous_end_callback_url is None:
            os.environ.pop("END_CONVERSATION_CALLBACK_URL", None)
            return

        os.environ["END_CONVERSATION_CALLBACK_URL"] = self._previous_end_callback_url

    def _build_assistant_message(self, content: str) -> Message:
        return Message(
            id=f"msg-{len(content)}",
            role=MessageRole.ASSISTANT,
            content=content,
            tokens=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            timing=MessageTiming(
                received_at=datetime.now(timezone.utc),
                responded_at=datetime.now(timezone.utc),
                total_duration_ms=0,
            ),
        )

    def _expected_conversation_id(self, user_id: str) -> str:
        partition_date = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
        return f"{user_id}_{partition_date}"

    async def test_start_returns_configured_greeting_without_user_message(self) -> None:
        store = InMemoryConversationStore()

        # Sin nombre resuelto desde Postgres -> saludo alterno SIN "cliente".
        with patch(
            "application.chat.chat_service._resolve_customer_given_name",
            new=AsyncMock(return_value=""),
        ):
            conversation = await process_start_message(
                user_id="03966512",
                store=store,
            )

        self.assertEqual(
            conversation.conversation_id,
            self._expected_conversation_id("03966512"),
        )
        self.assertEqual(conversation.current_step, "start")
        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(conversation.messages[0].role, MessageRole.ASSISTANT)
        self.assertEqual(
            conversation.messages[0].content,
            load_general_messages().start_greeting_template_no_name,
        )
        self.assertNotIn("cliente", conversation.messages[0].content.lower())

    async def test_start_greets_with_given_name_from_postgres(self) -> None:
        store = InMemoryConversationStore()

        with patch(
            "application.chat.chat_service._resolve_customer_given_name",
            new=AsyncMock(return_value="Juan David"),
        ):
            conversation = await process_start_message(
                user_id="07893963",
                store=store,
            )

        expected = load_general_messages().start_greeting_template.format(
            customer_name="Juan David"
        )
        self.assertEqual(conversation.messages[0].content, expected)
        self.assertIn("Juan David", conversation.messages[0].content)
        self.assertNotIn("cliente", conversation.messages[0].content.lower())

    async def test_start_first_session_records_daily_counter(self) -> None:
        store = InMemoryConversationStore()
        control_store = FakeDailySessionControlStore(initial_count=0)

        conversation = await process_start_message(
            user_id="03966512",
            store=store,
            control_store=control_store,
        )

        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertEqual(control_store.record_session_start_call_count, 1)
        self.assertEqual(control_store.count, 1)

    async def test_start_when_active_session_exists_resumes_idempotently(self) -> None:
        # Architecture A: re-entering while a session is in progress RESUMES it
        # (idempotent) instead of raising a conflict. No new session is created
        # and the daily session counter is NOT incremented.
        store = InMemoryConversationStore()
        control_store = FakeDailySessionControlStore(initial_count=1)
        conversation_id = self._expected_conversation_id("03966512")
        store.conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1",
            user_id="03966512",
            messages=[],
        )

        conversation = await process_start_message(
            user_id="03966512",
            store=store,
            control_store=control_store,
        )

        # Same session returned, resumed where it was (not reset to "start").
        self.assertEqual(conversation.conversation_id, conversation_id)
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertEqual(conversation.current_step, "1.4.1")
        # Idempotent resume: the daily session counter was NOT incremented.
        self.assertEqual(control_store.record_session_start_call_count, 0)
        self.assertEqual(control_store.count, 1)

    async def test_start_reopens_when_previous_session_is_closed(self) -> None:
        store = InMemoryConversationStore()
        control_store = FakeDailySessionControlStore(initial_count=1)
        conversation_id = self._expected_conversation_id("03966512")
        store.conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.CLOSED,
            current_step="end",
            user_id="03966512",
            messages=[],
        )
        store.messages[conversation_id] = ["stale-message"]

        conversation = await process_start_message(
            user_id="03966512",
            store=store,
            control_store=control_store,
        )

        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertEqual(conversation.current_step, "start")
        # Previous session messages were removed and only the fresh greeting remains.
        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(conversation.messages[0].role, MessageRole.ASSISTANT)
        self.assertEqual(store.messages[conversation_id], [conversation.messages[0]])
        self.assertEqual(control_store.record_session_start_call_count, 1)
        self.assertEqual(control_store.count, 2)

    async def test_start_opens_even_past_daily_session_limit(self) -> None:
        # UX: el cap diario de sesiones YA NO bloquea; el unico control es el loop
        # de warning por categoria. La 4a sesion (initial_count=3) abre normal.
        store = InMemoryConversationStore()
        control_store = FakeDailySessionControlStore(initial_count=3)

        conversation = await process_start_message(
            user_id="03966512",
            store=store,
            control_store=control_store,
        )

        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertEqual(len(conversation.messages), 1)  # saludo, no mensaje de limite
        # La sesion se sigue contando (metricas), pero no bloquea.
        self.assertEqual(control_store.record_session_start_call_count, 1)

    async def test_start_without_control_store_skips_limit(self) -> None:
        store = InMemoryConversationStore()

        conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )

        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)

    async def test_prefetch_back_data_clears_stale_result_and_polls_for_fresh_data(
        self,
    ) -> None:
        conversation = Conversation(
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
            captured_data={},
            user_id="7667553",
            messages=[],
        )
        control_store = StubControlStore(
            [
                None,
                {"caso": "no extracto", "id_msg": 17},
            ],
            stale_back_data={"fecha": "", "tipo": "963191", "bandera": "true", "id_msg": 14},
        )

        with patch(
            "application.chat.chat_service.trigger_notificacion_centrales",
            new_callable=AsyncMock,
        ) as mocked_trigger, patch(
            "application.chat.chat_service.uuid4",
            return_value="RUNID",
        ), patch(
            "application.chat.chat_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mocked_sleep:
            await _prefetch_back_data_if_needed(
                conversation=conversation,
                back_data_service_url="http://back-data.test",
                control_store=control_store,
            )

        self.assertEqual(
            json.loads(conversation.captured_data["back_data_result"]),
            {"caso": "no extracto", "id_msg": 17},
        )
        self.assertEqual(conversation.captured_data["back_data_notified"], "1.4.1.3")
        self.assertEqual(control_store.clear_workflow_back_data_call_count, 1)
        self.assertEqual(control_store.get_record_call_count, 2)
        mocked_trigger.assert_awaited_once()
        mocked_sleep.assert_awaited_once()

    async def test_first_chat_message_routes_with_agent_then_keeps_yaml_flow(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        routed_conversation = await process_chat_message(
            content="Necesito ayuda con el impuesto 4x1000",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(strands_agent.route_call_count, 1)
        self.assertEqual(routed_conversation.current_step, "start.confirmation")
        self.assertIn(
            "Segun el contexto que me das, entiendo que tu consulta esta relacionada con el impuesto 4x1000.",
            routed_conversation.messages[-1].content,
        )
        self.assertIn(
            "Quieres continuar con el flujo encontrado?",
            routed_conversation.messages[-1].content,
        )

        confirmed_conversation = await process_chat_message(
            content="continuar",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(confirmed_conversation.current_step, "1")
        self.assertEqual(confirmed_conversation.workflow, "impuesto_4x1000")
        self.assertIn(
            "Se inicia el flujo Impuesto 4x1000.",
            confirmed_conversation.messages[-1].content,
        )

    async def test_pure_greeting_returns_welcome_without_invoking_agent(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        greeted_conversation = await process_chat_message(
            content="Hola, ¿cómo estás?",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        # El guard deterministico responde sin gastar una llamada al LLM de routing.
        self.assertEqual(strands_agent.route_call_count, 0)
        self.assertEqual(greeted_conversation.status, ConversationStatus.ACTIVE)
        self.assertEqual(greeted_conversation.current_step, "start")
        self.assertIsNone(greeted_conversation.workflow)
        self.assertIn(
            "Puedo ayudarte con temas de:",
            greeted_conversation.messages[-1].content,
        )
        # Y re-presenta las categorias reales del catalogo.
        for category_label in (
            group.label for group in workflow_engine.catalog.welcome.groups
        ):
            self.assertIn(category_label, greeted_conversation.messages[-1].content)

    async def test_greeting_with_intent_still_routes_with_agent(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        routed_conversation = await process_chat_message(
            content="Hola, necesito ayuda con el impuesto 4x1000",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        # Un saludo seguido de una solicitud concreta NO debe cortarse en el guard:
        # debe enrutar normalmente con el agente y NO devolver la bienvenida deterministica.
        self.assertEqual(strands_agent.route_call_count, 1)
        self.assertNotIn(
            "Puedo ayudarte con temas de:",
            routed_conversation.messages[-1].content,
        )

    async def test_chat_turn_can_continue_in_background_and_block_parallel_turns(
        self,
    ) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = SlowStrandsWorkflowAgent(delay_seconds=0.05)

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        first_result = await process_chat_message_with_timeout(
            content="Necesito ayuda con el impuesto 4x1000",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            processing_timeout_seconds=0.01,
        )

        self.assertIsNone(first_result)

        running_snapshot = await get_conversation_snapshot(
            conversation_id=conversation_id,
            store=store,
        )
        self.assertEqual(running_snapshot.status, ConversationStatus.RUNNING)

        second_result = await process_chat_message_with_timeout(
            content="Quiero enviar otro mensaje",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
            processing_timeout_seconds=0.01,
        )

        self.assertIsNone(second_result)

        await asyncio.sleep(0.08)

        completed_snapshot = await get_conversation_snapshot(
            conversation_id=conversation_id,
            store=store,
        )
        self.assertEqual(completed_snapshot.status, ConversationStatus.ACTIVE)
        self.assertEqual(completed_snapshot.current_step, "start.confirmation")
        self.assertEqual(strands_agent.route_call_count, 1)
        self.assertEqual(len(completed_snapshot.messages), 3)
        self.assertIn(
            "Quieres continuar con el flujo encontrado?",
            completed_snapshot.messages[-1].content,
        )

    async def test_guide_shortcut_enters_selected_branch_without_skipping_intro(
        self,
    ) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        strands_agent.routing_decision = WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key="guia_rapida",
            workflow="centrales_de_riesgo",
            confidence="high",
            rationale=(
                "Porque hablas de un reporte en centrales de riesgo asociado a tu cuenta."
            ),
            assistant_message=(
                "Segun el contexto que me das, entiendo que tu consulta habla de "
                "centrales de riesgo y del estado de tu cuenta. Creo que el flujo "
                "adecuado para ayudarte a avanzar es Guia rapida -> Cuenta Embargada, "
                "porque mencionas un reporte o novedad de riesgo sobre ese producto."
            ),
        )

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        routed_conversation = await process_chat_message(
            content="No reconozco un reporte en centrales de riesgo de mi cuenta",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(routed_conversation.current_step, "start.confirmation")
        self.assertIn(
            "Guia rapida -> Cuenta Embargada",
            routed_conversation.messages[-1].content,
        )

        confirmed_conversation = await process_chat_message(
            content="continuar",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(confirmed_conversation.workflow, "centrales_de_riesgo")
        self.assertEqual(confirmed_conversation.current_step, "1.4")
        self.assertEqual(
            confirmed_conversation.flow_answers["tipo_consulta"],
            "centrales_de_riesgo",
        )
        self.assertNotIn(
            "continuar_consulta_centrales_de_riesgo",
            confirmed_conversation.flow_answers,
        )
        self.assertIn(
            "Centrales de Informacion",
            confirmed_conversation.messages[-1].content,
        )
        self.assertIn(
            "Quieres continuar con la consulta?",
            confirmed_conversation.messages[-1].content,
        )

    async def test_embargo_context_enters_risk_branch_intro_before_follow_up_steps(
        self,
    ) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        strands_agent.routing_decision = WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key="guia_rapida",
            workflow="centrales_de_riesgo",
            confidence="high",
            rationale=(
                "Porque mencionas que tu cuenta aparece embargada y quieres entender ese embargo."
            ),
            assistant_message=(
                "Entendi que quieres saber si tu cuenta esta embargada y que "
                "necesitas orientacion porque no reconoces que entidad genero ese "
                "embargo. El flujo que mejor encaja es Guia rapida -> Cuenta Embargada, "
                "ya que esta pensado para consultas sobre embargos de cuentas y estado "
                "del producto."
            ),
        )

        started_conversation = await process_start_message(
            user_id="03966512",
            store=store,
        )
        conversation_id = started_conversation.conversation_id

        routed_conversation = await process_chat_message(
            content="Mi cuenta aparece embargada y no se que entidad genero ese embargo",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(routed_conversation.workflow, "centrales_de_riesgo")
        self.assertEqual(routed_conversation.current_step, "1.4.1")
        self.assertNotIn(
            "tipo_inconveniente_centrales_de_riesgo",
            routed_conversation.flow_answers,
        )
        self.assertIn(
            "cuál es tu situación",
            routed_conversation.messages[-1].content,
        )

    async def test_central_risk_terminal_message_skips_agent_and_keeps_default_response(
        self,
    ) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        conversation_id = "03966512_20260506"

        store.conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.1.1",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={
                "tipo_consulta": "centrales_de_riesgo",
                "continuar_consulta_centrales_de_riesgo": "si",
                "tipo_inconveniente_centrales_de_riesgo": (
                    "reporte_no_reconocido_o_incorrecto"
                ),
                "producto_centrales_de_riesgo": "producto_1",
            },
            captured_data={},
            user_id="03966512",
        )

        updated_conversation = await process_chat_message(
            content="1",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(updated_conversation.status, ConversationStatus.CLOSED)
        self.assertEqual(strands_agent.final_response_call_count, 0)
        self.assertIn(
            "centrales_riesgo_default_response",
            updated_conversation.captured_data,
        )
        self.assertEqual(
            updated_conversation.messages[-1].content,
            updated_conversation.captured_data["centrales_riesgo_default_response"],
        )

    async def test_sold_portfolio_terminal_message_keeps_yaml_response(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        conversation_id = "03966512_20260507"

        store.conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1.1.1",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={
                "tipo_consulta": "centrales_de_riesgo",
                "continuar_consulta_centrales_de_riesgo": "si",
                "tipo_inconveniente_centrales_de_riesgo": (
                    "reporte_no_reconocido_o_incorrecto"
                ),
                "producto_centrales_de_riesgo": "producto_1",
            },
            captured_data={},
            user_id="03966512",
        )

        updated_conversation = await process_chat_message(
            content="4",
            conversation_id=conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )

        self.assertEqual(updated_conversation.status, ConversationStatus.CLOSED)
        self.assertEqual(strands_agent.final_response_call_count, 0)
        self.assertEqual(
            updated_conversation.flow_answers[
                "novedad_producto_pasivo_centrales_de_riesgo"
            ],
            "cartera_vendida",
        )
        self.assertIn(
            "tu cartera fue vendida a Gestion Patrimonial Andina S.A.S.",
            updated_conversation.messages[-1].content,
        )
        self.assertIn(
            "radicado CV-18427",
            updated_conversation.messages[-1].content,
        )

    async def test_end_closes_active_conversation_and_notifies_callback(self) -> None:
        from application.chat.chat_service import process_end_conversation

        store = InMemoryConversationStore()
        conversation_id = "03966512_20260506"
        os.environ["END_CONVERSATION_CALLBACK_URL"] = (
            "http://127.0.0.1:8001/end/{conversation_id}"
        )
        assistant_message = self._build_assistant_message("Flujo activo")
        active_conversation = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.ACTIVE,
            current_step="1.4.1",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={"tipo_consulta": "centrales_de_riesgo"},
            captured_data={"foo": "bar"},
            user_id="03966512",
            messages=[assistant_message],
        )
        store.conversations[conversation_id] = active_conversation

        with patch(
            "application.chat.chat_service._notify_end_conversation_callback",
            new_callable=AsyncMock,
        ) as mocked_notify_callback:
            closed_conversation = await process_end_conversation(
                conversation_id=conversation_id,
                store=store,
            )

        self.assertEqual(closed_conversation.status, ConversationStatus.CLOSED)
        self.assertEqual(closed_conversation.current_step, "1.4.1")
        self.assertEqual(closed_conversation.workflow, "centrales_de_riesgo")
        self.assertEqual(len(closed_conversation.messages), 1)
        self.assertEqual(store.save_conversation_reference_call_count, 1)
        self.assertEqual(store.refresh_call_count, 1)
        self.assertEqual(store.save_message_call_count, 0)
        mocked_notify_callback.assert_awaited_once()
        self.assertEqual(
            mocked_notify_callback.await_args.kwargs["callback_url"],
            "http://127.0.0.1:8001/end/{conversation_id}",
        )
        self.assertEqual(
            mocked_notify_callback.await_args.kwargs["conversation"].conversation_id,
            conversation_id,
        )

    def test_end_callback_url_template_is_resolved_with_conversation_id(self) -> None:
        conversation = Conversation(
            conversation_id="03966512_20260506",
            status=ConversationStatus.CLOSED,
            current_step="9",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={},
            captured_data={},
            user_id="03966512",
            messages=[],
        )

        resolved_url = _resolve_end_conversation_callback_url(
            conversation=conversation,
            callback_url="http://127.0.0.1:8001/end/{conversation_id}",
        )

        self.assertEqual(
            resolved_url,
            "http://127.0.0.1:8001/end/03966512_20260506",
        )

    async def test_end_returns_already_closed_conversation_without_persisting_changes(
        self,
    ) -> None:
        from application.chat.chat_service import process_end_conversation

        store = InMemoryConversationStore()
        conversation_id = "03966512_20260506"
        assistant_message = self._build_assistant_message("Ya estaba cerrada")
        closed_conversation = Conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.CLOSED,
            current_step="9",
            general_workflow="Guia rapida",
            workflow="centrales_de_riesgo",
            flow_version=1,
            flow_answers={"tipo_consulta": "centrales_de_riesgo"},
            captured_data={"foo": "bar"},
            user_id="03966512",
            messages=[assistant_message],
        )
        store.conversations[conversation_id] = closed_conversation

        with patch(
            "application.chat.chat_service._notify_end_conversation_callback",
            new_callable=AsyncMock,
        ) as mocked_notify_callback:
            returned_conversation = await process_end_conversation(
                conversation_id=conversation_id,
                store=store,
            )

        self.assertEqual(returned_conversation.status, ConversationStatus.CLOSED)
        self.assertEqual(returned_conversation.current_step, "9")
        self.assertEqual(returned_conversation.messages[-1].content, "Ya estaba cerrada")
        self.assertEqual(store.save_conversation_reference_call_count, 0)
        self.assertEqual(store.refresh_call_count, 0)
        self.assertEqual(store.save_message_call_count, 0)
        mocked_notify_callback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()


class ExtractGivenNamesTests(unittest.TestCase):
    def test_strips_both_surnames_and_titlecases(self) -> None:
        from application.chat.chat_service import _extract_given_names

        self.assertEqual(
            _extract_given_names("NELSON DE JESUS GONZALEZ HOYOS", "GONZALEZ", "HOYOS"),
            "Nelson De Jesus",
        )

    def test_single_surname(self) -> None:
        from application.chat.chat_service import _extract_given_names

        self.assertEqual(
            _extract_given_names("ESTEBAN RESTREPO URIBE", "RESTREPO", "URIBE"),
            "Esteban",
        )

    def test_empty_or_only_surnames_returns_empty(self) -> None:
        from application.chat.chat_service import _extract_given_names

        self.assertEqual(_extract_given_names("", "X", "Y"), "")
        self.assertEqual(_extract_given_names("GONZALEZ HOYOS", "GONZALEZ", "HOYOS"), "")


class AmbiguityConfirmationTests(unittest.IsolatedAsyncioTestCase):
    """Punto 2: candidato ambiguo (confidence=low) -> confirmación '¿Te refieres a ...?'.

    - low + is_match -> se pregunta "¿Te refieres a {hint}?" (no auto-start).
    - "continuar" -> entra al workflow sugerido.
    - "salir"     -> formulario PQRS (workflow interno pqrs_no_ruteo).
    """

    def _low_agent(self) -> StubStrandsWorkflowAgent:
        agent = StubStrandsWorkflowAgent()
        agent.routing_decision = WorkflowRoutingDecision(
            is_match=True,
            general_workflow_key="guia_rapida",
            workflow="impuesto_4x1000",
            confidence="low",
            rationale="Candidato plausible pero ambiguo.",
            assistant_message="Podria tratarse del 4x1000.",
        )
        return agent

    async def _route_low(self, store, workflow_engine, agent):
        started = await process_start_message(user_id="03966512", store=store)
        cid = started.conversation_id
        routed = await process_chat_message(
            content="4x1",
            conversation_id=cid,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=agent,
        )
        return cid, routed

    async def test_low_confidence_asks_natural_confirmation(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        _, routed = await self._route_low(store, workflow_engine, self._low_agent())
        self.assertEqual(routed.current_step, "start.confirmation")
        self.assertIn(
            "¿Te refieres a una consulta sobre el 4x1000?",
            routed.messages[-1].content,
        )

    async def test_low_confidence_continuar_enters_flow(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        agent = self._low_agent()
        cid, _ = await self._route_low(store, workflow_engine, agent)
        confirmed = await process_chat_message(
            content="continuar",
            conversation_id=cid,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=agent,
        )
        self.assertEqual(confirmed.workflow, "impuesto_4x1000")
        self.assertNotEqual(confirmed.current_step, "start.confirmation")

    async def test_low_confidence_salir_goes_to_pqrs_form(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        agent = self._low_agent()
        cid, _ = await self._route_low(store, workflow_engine, agent)
        rejected = await process_chat_message(
            content="salir",
            conversation_id=cid,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=agent,
        )
        self.assertEqual(rejected.workflow, "pqrs_no_ruteo")


class GreetingResilienceTests(unittest.IsolatedAsyncioTestCase):
    """Saludos simples y complejos deben re-saludar (no caer al formulario).

    Cubre: elongaciones ("holaaaa como vassss"), lexico ampliado ("buena tarde"),
    interceptacion en punto neutro a mitad de flujo (satisfaction_check) y que un
    saludo + intencion concreta SI rutee con el agente.
    """

    async def _welcome_first_turn(self, content: str):
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        started = await process_start_message(user_id="03966512", store=store)
        result = await process_chat_message(
            content=content,
            conversation_id=started.conversation_id,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )
        return result, strands_agent, workflow_engine

    async def test_elongated_greeting_returns_welcome_without_agent(self) -> None:
        result, agent, _ = await self._welcome_first_turn("Holaaaaaa como vassss")
        self.assertEqual(agent.route_call_count, 0)
        self.assertIsNone(result.workflow)
        self.assertEqual(result.current_step, "start")
        self.assertIn("Puedo ayudarte con temas de:", result.messages[-1].content)

    async def test_buena_tarde_returns_welcome_without_agent(self) -> None:
        result, agent, _ = await self._welcome_first_turn("buena tarde")
        self.assertEqual(agent.route_call_count, 0)
        self.assertIsNone(result.workflow)
        self.assertEqual(result.current_step, "start")
        self.assertIn("Puedo ayudarte con temas de:", result.messages[-1].content)

    async def test_greeting_at_satisfaction_check_resets_and_welcomes(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        strands_agent = StubStrandsWorkflowAgent()
        started = await process_start_message(user_id="03966512", store=store)
        cid = started.conversation_id
        # Simular una conversacion parada a mitad de flujo en la encuesta.
        conv = store.conversations[cid]
        conv.workflow = "pqrs_no_ruteo"
        conv.general_workflow = "PQRs"
        conv.current_step = "satisfaction_check"
        conv.status = ConversationStatus.ACTIVE

        result = await process_chat_message(
            content="buena tarde",
            conversation_id=cid,
            store=store,
            workflow_engine=workflow_engine,
            strands_agent=strands_agent,
        )
        # Se re-saluda y se resetea al inicio, sin gastar el LLM ni caer al formulario.
        self.assertEqual(strands_agent.route_call_count, 0)
        self.assertIsNone(result.workflow)
        self.assertEqual(result.current_step, "start")
        self.assertIn("Puedo ayudarte con temas de:", result.messages[-1].content)

    async def test_elongated_greeting_plus_intent_still_routes(self) -> None:
        result, agent, _ = await self._welcome_first_turn(
            "holaaa necesito ayuda con el impuesto 4x1000"
        )
        # Saludo + intencion concreta NO es saludo puro: debe rutear con el agente.
        self.assertEqual(agent.route_call_count, 1)
        self.assertNotIn("Puedo ayudarte con temas de:", result.messages[-1].content)


from application.chat.chat_service import _is_bare_pqrs_request


class IsBarePqrsRequestTests(unittest.TestCase):
    """Detector determinista de meta-peticiones 'peladas' de PQR (sin causal)."""

    def test_bare_meta_requests_are_detected(self) -> None:
        for text in (
            "formulario PQR",
            "Radicar PQR",
            "quiero poner una pqr",
            "Necesito radicar una pqrs",
            "como subo una pqr",
            "Poner una queja",
            "Quiero una pqr",
            "necesito llenar el formulario de pqrs",
            "por favor el formulario para pqrs",
            "quiero momar una PQR",  # typo observado en trazas
        ):
            with self.subTest(text=text):
                self.assertTrue(_is_bare_pqrs_request(text))

    def test_requests_with_causal_are_not_bare(self) -> None:
        # Si viene el motivo en el MISMO mensaje, NO es pelado: se rutea normal.
        for text in (
            "quiero radicar una pqr por fraude",
            "Necesito poner un PQR por el bloqueo de mi cuenta de ahorros",
            "quiero radicar una queja de recuperacion de dinero",
            "necesito radicar otro pqr porque no me estan atendiendo",
            "quiero poner una queja sobre la atencion al cliente",
        ):
            with self.subTest(text=text):
                self.assertFalse(_is_bare_pqrs_request(text))

    def test_non_pqr_and_form_failure_messages_are_not_bare(self) -> None:
        # Sin objeto PQR, saludos, o quejas de "el formulario no abre" (bucket aparte).
        for text in (
            "",
            "hola como vas",
            "necesito mi paz y salvo",
            "formulario pqr no abre",
            "no me deja radicar un oficio para obtener un pqrs",
            "En que parte encuentro el formulario de pqr",
        ):
            with self.subTest(text=text):
                self.assertFalse(_is_bare_pqrs_request(text))


class BarePqrsClarificationFlowTests(unittest.IsolatedAsyncioTestCase):
    """Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match."""

    async def _start(self):
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        agent = StubStrandsWorkflowAgent()
        started = await process_start_message(user_id="03966512", store=store)
        return store, workflow_engine, agent, started.conversation_id

    async def _chat(self, content, store, we, agent, cid):
        return await process_chat_message(
            content=content,
            conversation_id=cid,
            store=store,
            workflow_engine=we,
            strands_agent=agent,
        )

    async def test_bare_formulario_pqr_asks_for_reason_post_router(self) -> None:
        store, we, agent, cid = await self._start()
        agent.routing_decision = WorkflowRoutingDecision(is_match=False)

        conv = await self._chat("formulario PQR", store, we, agent, cid)

        # Post-router: el LLM decidio primero (no_match) y recien ahi aclaramos.
        self.assertEqual(agent.route_call_count, 1)
        self.assertEqual(
            conv.captured_data.get("pqrs_clarify_state"), "await_continue"
        )
        self.assertIsNone(conv.workflow)
        self.assertIn("motivo de tu solicitud", conv.messages[-1].content)
        self.assertIn("presiona Continuar", conv.messages[-1].content)

    async def test_continue_moves_to_reason_prompt_without_new_routing(self) -> None:
        store, we, agent, cid = await self._start()
        agent.routing_decision = WorkflowRoutingDecision(is_match=False)

        await self._chat("formulario PQR", store, we, agent, cid)
        conv = await self._chat("continuar", store, we, agent, cid)

        # "Continuar" NO gasta una llamada al router.
        self.assertEqual(agent.route_call_count, 1)
        self.assertEqual(conv.captured_data.get("pqrs_clarify_state"), "await_reason")
        self.assertIn("describe el motivo de tu PQR", conv.messages[-1].content)

    async def test_reason_reroutes_when_it_maps_to_a_workflow(self) -> None:
        store, we, agent, cid = await self._start()
        agent.routing_decision = WorkflowRoutingDecision(is_match=False)

        await self._chat("formulario PQR", store, we, agent, cid)
        await self._chat("continuar", store, we, agent, cid)

        # El causal SI mapea a un workflow -> el router lo enruta.
        agent.routing_decision = StubStrandsWorkflowAgent().routing_decision
        conv = await self._chat(
            "me cobran el impuesto 4x1000", store, we, agent, cid
        )

        self.assertEqual(agent.route_call_count, 2)
        self.assertIsNone(conv.captured_data.get("pqrs_clarify_state"))
        self.assertEqual(
            conv.captured_data.get("pqrs_reason"), "me cobran el impuesto 4x1000"
        )
        self.assertEqual(conv.workflow, "impuesto_4x1000")
        self.assertNotIn("describe el motivo", conv.messages[-1].content)

    async def test_repeated_bare_reinvites_indefinitely(self) -> None:
        store, we, agent, cid = await self._start()
        agent.routing_decision = WorkflowRoutingDecision(is_match=False)

        await self._chat("formulario PQR", store, we, agent, cid)
        # Vuelve a mandar algo pelado en vez de Continuar -> se re-invita (indefinido).
        conv = await self._chat("formulario PQRS", store, we, agent, cid)

        self.assertEqual(agent.route_call_count, 1)  # no volvio a rutear
        self.assertEqual(
            conv.captured_data.get("pqrs_clarify_state"), "await_continue"
        )
        self.assertIn("presiona Continuar", conv.messages[-1].content)

    async def test_router_match_is_never_overridden_by_clarification(self) -> None:
        # Concern #1: aunque el mensaje sea "pelado", si el router MATCHEA, jamas
        # se aclara ni se secuestra la intencion.
        store, we, agent, cid = await self._start()  # stub por defecto = match high

        conv = await self._chat("formulario PQR", store, we, agent, cid)

        self.assertEqual(agent.route_call_count, 1)
        self.assertIsNone(conv.captured_data.get("pqrs_clarify_state"))
        self.assertEqual(conv.workflow, "impuesto_4x1000")
        self.assertNotIn("presiona Continuar", conv.messages[-1].content)

    async def test_pqr_with_causal_in_same_message_is_not_clarified(self) -> None:
        # Concern #2a: "formulario PQR" + causal en el mismo mensaje -> no aclara
        # el CAUSAL (no pregunta "por que"), porque el cliente ya lo dio.
        #
        # Un no-match de una solicitud bancaria que no pertenece a un workflow
        # independiente ni a una FAQ abre el selector de subflujos de Centrales.
        # Lo que este test protege sigue igual: NO se activa el clarify de
        # causal para una PQR que ya trae el motivo.
        store, we, agent, cid = await self._start()
        agent.routing_decision = WorkflowRoutingDecision(is_match=False)

        conv = await self._chat(
            "quiero radicar una pqr por un cobro no reconocido",
            store,
            we,
            agent,
            cid,
        )

        self.assertIsNone(conv.captured_data.get("pqrs_clarify_state"))
        self.assertNotIn("presiona Continuar", conv.messages[-1].content)
        self.assertEqual(conv.captured_data.get("routing_outcome"), "centrales_selector")
        self.assertEqual(conv.workflow, "centrales_de_riesgo")
        self.assertEqual(conv.current_step, "1.4.1")
        self.assertIn("cuál es tu situación", conv.messages[-1].content)


from application.chat.chat_service import (
    _handle_trx_interactive_capture_step as _trx_loop_handler,
)


class TrxLoopTests(unittest.IsolatedAsyncioTestCase):
    """Bucle 'una transacción a la vez' del flujo TXNR (Árbol 1)."""

    def _conv(self, *, current_step: str, cantidad: str, index: int) -> Conversation:
        return Conversation(
            conversation_id="1013634958_20260807",
            status=ConversationStatus.ACTIVE,
            current_step=current_step,
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            flow_answers={"trx_cantidad": cantidad},
            captured_data={"trx_index": str(index)},
            user_id="1013634958",
        )

    async def test_si_siguiente_advances_to_next_transaction(self) -> None:
        we = WorkflowEngine()
        conv = self._conv(current_step="2.4.0.1.20.1", cantidad="2", index=1)
        conv.status = ConversationStatus.RUNNING

        result = await _trx_loop_handler(
            conversation=conv,
            user_content="si_siguiente",
            workflow_engine=we,
            trx_service_url=None,
            back_data_service_url=None,
            control_store=None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(conv.current_step, "2.4.0.1.3")
        self.assertEqual(conv.captured_data["trx_index"], "2")
        self.assertIn("2 de 2", result)
        # El avance NO pasa por generate_response: debe dejar ACTIVE (no RUNNING).
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)

    async def test_last_transaction_does_not_advance(self) -> None:
        we = WorkflowEngine()
        conv = self._conv(current_step="2.4.0.1.20.1", cantidad="2", index=2)

        result = await _trx_loop_handler(
            conversation=conv,
            user_content="si_siguiente",
            workflow_engine=we,
            trx_service_url=None,
            back_data_service_url=None,
            control_store=None,
        )

        # index>=n: el handler no avanza (el prefetch ya habria cerrado antes).
        self.assertIsNone(result)
        self.assertEqual(conv.current_step, "2.4.0.1.20.1")

    async def test_handler_ignores_other_workflows(self) -> None:
        we = WorkflowEngine()
        conv = self._conv(current_step="2.4.0.1.20.1", cantidad="1", index=1)
        conv.workflow = "centrales_de_riesgo"
        result = await _trx_loop_handler(
            conversation=conv,
            user_content="si_siguiente",
            workflow_engine=we,
            trx_service_url=None,
            back_data_service_url=None,
            control_store=None,
        )
        self.assertIsNone(result)


from application.chat.chat_service import (
    _prefetch_trx_data_if_needed as _trx_prefetch,
)


class TrxVigenciaRoutingTests(unittest.IsolatedAsyncioTestCase):
    """Ruteo del gate 2.4.0.1.8 (vigencia offline por franquicia/fecha)."""

    def _conv(self, *, fecha: str, brand: str = "VISA") -> Conversation:
        conv = Conversation(
            conversation_id="1013634958_20260810",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.1.8",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            user_id="1013634958",
        )
        conv.flow_answers["producto_trx_no_reconocida"] = "producto_1"
        conv.flow_answers["trx_fecha"] = fecha
        conv.captured_data["trx_products_result"] = json.dumps(
            {"data": {"products": [{"last_four_pan_id": "4979", "card_brand": brand}]}}
        )
        return conv

    async def test_vencida_routes_to_date_exit(self) -> None:
        conv = self._conv(fecha="01/01/2000", brand="VISA")
        await _trx_prefetch(conv, None, None, None)
        self.assertEqual(conv.current_step, "2.4.0.1.7.exit")

    async def test_vigente_without_movements_routes_to_return(self) -> None:
        from datetime import datetime

        hoy = datetime.now().strftime("%d/%m/%Y")
        conv = self._conv(fecha=hoy, brand="VISA")
        # Sin trx_service_url no hay ASO -> movimientos vacios -> 2.4.0.1.8.return.
        await _trx_prefetch(conv, None, None, None)
        self.assertEqual(conv.current_step, "2.4.0.1.8.return")


if __name__ == "__main__":
    unittest.main()


from application.chat.chat_service import (
    _prefetch_trx_data_if_needed as _trx_prefetch_recurrence,
)


class TrxRecurrenceRoutingTests(unittest.IsolatedAsyncioTestCase):
    """Ruteo del paso 2.4.0.1 segun la recurrencia detectada por back_trx."""

    def _conv(self) -> Conversation:
        return Conversation(
            conversation_id="80425247_20260810",
            status=ConversationStatus.ACTIVE,
            current_step="2.4.0.1",
            general_workflow="Transaccion no reconocida",
            workflow="trx_no_reconocida",
            flow_version=1,
            user_id="80425247",
        )

    async def test_recurrence_redirects_to_dedicated_pqr_step(self) -> None:
        conv = self._conv()
        with patch(
            "application.chat.chat_service.validar_recurrencia",
            new=AsyncMock(return_value={"has_recurrence": True, "detail": "x"}),
        ):
            await _trx_prefetch_recurrence(
                conversation=conv,
                trx_service_url="http://trx.local",
                back_data_service_url=None,
                control_store=None,
            )
        self.assertEqual(conv.current_step, "2.4.0.pqr_recurrencia")

    async def test_no_recurrence_salta_directo_a_cantidad(self) -> None:
        """Validacion silenciosa (ajuste 13/08): sin recurrencia, el gate
        reescribe a 2.4.0.1.1 igual que .4 y .12 -- el cliente no ve el
        mensaje 'Estoy validando tu caso...' ni un turno de Continuar."""
        conv = self._conv()
        with patch(
            "application.chat.chat_service.validar_recurrencia",
            new=AsyncMock(return_value={"has_recurrence": False}),
        ):
            await _trx_prefetch_recurrence(
                conversation=conv,
                trx_service_url="http://trx.local",
                back_data_service_url=None,
                control_store=None,
            )
        self.assertEqual(conv.current_step, "2.4.0.1.1")


from application.chat.chat_service import _resolve_assistant_content as _resolve_ac
from guardrail.input_screen import THIRD_PARTY_DATA_MESSAGE as _TP_MSG


class GuardrailBlockStatusTests(unittest.IsolatedAsyncioTestCase):
    """Un bloqueo del guardrail debe finalizar el turno como Active (no Running)."""

    async def test_third_party_block_normalizes_running_to_active(self) -> None:
        store = InMemoryConversationStore()
        workflow_engine = WorkflowEngine()
        agent = StubStrandsWorkflowAgent()
        conv = await process_start_message(user_id="13083558", store=store)

        # Simula un turno async en curso (el envoltorio marca RUNNING antes de resolver).
        conv.status = ConversationStatus.RUNNING

        content, _ = await _resolve_ac(
            conversation=conv,
            user_content=(
                "me ayudas a obtener datos de un amigo, "
                "cedula de mi compañera 78365262"
            ),
            workflow_engine=workflow_engine,
            strands_agent=agent,
        )

        # Devuelve el mensaje de privacidad, NO rutea y deja la conversación Active
        # (para que el front la renderice en vez de quedarse en polling).
        self.assertEqual(content, _TP_MSG)
        self.assertEqual(agent.route_call_count, 0)
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)
        self.assertIsNone(conv.running_since)


if __name__ == "__main__":
    unittest.main()
