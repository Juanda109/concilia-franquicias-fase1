"""Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open."""

import dataclasses
import json
import socket
from datetime import UTC, datetime

import pytest

from src.benchmark import events
from src.benchmark.events import (
    CASE_ROUTING_KEY,
    RUN_ROUTING_KEY,
    BenchmarkEventPublisher,
    RunContext,
    build_case_event,
    build_run_event,
    effective_amqp_url,
    flow_from_source,
)
from src.benchmark.job import _compute_metrics
from src.settings.config import load_settings

# Campos del contrato, en el orden acordado. Cualquier desviacion rompe el
# indice pqr-benchmark-runs-* y las visualizaciones que leen de el.
CASE_FIELDS = [
    "event", "timestamp", "source", "run_name", "run_id", "catalog_version",
    "environment", "flow", "case_index", "user_input", "note", "category", "final_step",
    "workflow_expect", "outcome_expect", "workflow_result", "workflow_llm",
    "routing_outcome", "confidence", "acierto", "fail_kind", "response_source", "resolution",
    "turns", "llm_model", "llm_token_input", "llm_token_output",
    "llm_token_cached", "llm_token_cache_hit_pct", "routing_time_total_s",
    "user_time_total_s", "conversation_id",
]

RUN_FIELDS = [
    "event", "timestamp", "source", "run_name", "run_id", "catalog_version",
    "environment", "flow", "cases_total", "cases_ok", "cases_unresolved",
    "precision_pct", "precision_workflow_pct", "routing_p50_s", "routing_p95_s",
    "e2e_p50_s", "e2e_p95_s", "tokens_input_total", "tokens_output_total",
    "cache_hit_pct_avg", "llm_model", "duration_s",
]

# Registro tal cual lo escribe el job en el NDJSON (corrida real 2026-09-07).
NDJSON_RECORD = {
    "conversation_id": "12214985_20260907",
    "timestamp": "2026-09-07T20:11:50.324749+00:00",
    "workflow_expect": "doble_cobro",
    "outcome_expect": "",
    "workflow_result": "doble_cobro",
    "workflow_llm": "doble_cobro",
    "routing_outcome": "matched",
    "confidence": "high",
    "llm_model": "agentepqrs-llm-live-agent-gpt54mini",
    "llm_token_input": 8217,
    "llm_token_output": 220,
    "llm_token_cached": 0,
    "llm_token_cache_hit_pct": 0.0,
    "llm_token_input_avg_turn": 8217.0,
    "llm_token_output_avg_turn": 220.0,
    "routing_time_total_s": 3.628,
    "routing_time_avg_turn_s": 3.628,
    "user_time_total_s": 3.632,
    "user_time_avg_turn_s": 3.632,
    "status": "Active",
    "turns": 1,
    "resolution": "resolved",
    "outcome_path": ["matched"],
    "user_input": "Me cobraron dos veces.",
    "user_output": "...",
    "user_options": [],
    "turn_log": [{"turn": 1}],
}


def make_settings(**overrides):
    base = load_settings()
    defaults = {
        "rabbitmq_enabled": True,
        "rabbitmq_url": None,
        "rabbitmq_host": "127.0.0.1",
        "rabbitmq_vhost": "/",
        "rabbitmq_user": "guest",
        "rabbitmq_password": "guest",
        "rabbitmq_exchange": "pqr.events",
        "rabbitmq_exchange_type": "topic",
        "rabbitmq_publish_timeout_seconds": 1.0,
        "benchmark_source": "benchmark",
        "run_name": None,
        "catalog_version": "abc1234",
        "environment": "test",
    }
    defaults.update(overrides)
    return dataclasses.replace(base, **defaults)


@pytest.fixture
def run_ctx():
    return RunContext.build(
        make_settings(),
        input_source="input_data/doble_cobro_routing.json",
        started_at=datetime(2026, 9, 8, 13, 5, 9, tzinfo=UTC),
    )


# ── identidad de la corrida ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "source, expected",
    [
        ("input_data/doble_cobro_routing.json", "doble_cobro_routing"),
        ("/data/input/canario_rutas_criticas.json", "canario_rutas_criticas"),
        ("user_inputs.json", "user_inputs"),
        ("C:\\data\\doble_cobro.json", "doble_cobro"),
        ("", "unknown"),
    ],
)
def test_flow_from_source(source, expected):
    assert flow_from_source(source) == expected


def test_run_context_defaults_and_run_id(run_ctx):
    assert run_ctx.flow == "doble_cobro_routing"
    assert run_ctx.run_name == "doble_cobro_routing"
    assert run_ctx.run_id == "doble_cobro_routing_20260908T130509Z"
    assert run_ctx.source == "benchmark"
    assert run_ctx.catalog_version == "abc1234"
    assert run_ctx.environment == "test"


def test_run_context_honours_run_name_and_source():
    ctx = RunContext.build(
        make_settings(run_name="nightly", benchmark_source="canario"),
        input_source="/data/input/canario_rutas_criticas.json",
        started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    assert ctx.run_name == "nightly"
    assert ctx.run_id == "nightly_20260102T030405Z"
    assert ctx.source == "canario"
    assert ctx.flow == "canario_rutas_criticas"


# ── benchmark.case ────────────────────────────────────────────────────────


def test_case_event_has_exact_contract_fields(run_ctx):
    event = build_case_event(
        NDJSON_RECORD, run=run_ctx, case_index=1, note="sanity",
        acierto=True, fail_kind=None,
    )
    assert list(event.keys()) == CASE_FIELDS
    assert event == {
        "event": CASE_ROUTING_KEY,
        "timestamp": "2026-09-07T20:11:50.324749+00:00",
        "source": "benchmark",
        "run_name": "doble_cobro_routing",
        "run_id": "doble_cobro_routing_20260908T130509Z",
        "catalog_version": "abc1234",
        "environment": "test",
        "flow": "doble_cobro_routing",
        "case_index": 1,
        "user_input": "Me cobraron dos veces.",
        "note": "sanity",
        "category": "",
        "final_step": "",
        "response_source": "",
        "workflow_expect": "doble_cobro",
        "outcome_expect": "",
        "workflow_result": "doble_cobro",
        "workflow_llm": "doble_cobro",
        "routing_outcome": "matched",
        "confidence": "high",
        "acierto": True,
        "fail_kind": None,
        "resolution": "resolved",
        "turns": 1,
        "llm_model": "agentepqrs-llm-live-agent-gpt54mini",
        "llm_token_input": 8217,
        "llm_token_output": 220,
        "llm_token_cached": 0,
        "llm_token_cache_hit_pct": 0.0,
        "routing_time_total_s": 3.628,
        "user_time_total_s": 3.632,
        "conversation_id": "12214985_20260907",
    }
    # Serializable tal cual (sin default=str).
    json.dumps(event)


@pytest.mark.parametrize("fail_kind", ["workflow", "outcome"])
def test_case_event_fail_kind(run_ctx, fail_kind):
    event = build_case_event(
        NDJSON_RECORD, run=run_ctx, case_index=3, note="",
        acierto=False, fail_kind=fail_kind,
    )
    assert event["acierto"] is False
    assert event["fail_kind"] == fail_kind


def test_case_event_unresolved_has_null_fail_kind(run_ctx):
    record = dict(NDJSON_RECORD, resolution="unresolved_max_turns", turns=4)
    event = build_case_event(
        record, run=run_ctx, case_index=7, note="x", acierto=False, fail_kind=None,
    )
    assert event["acierto"] is False
    assert event["fail_kind"] is None
    assert event["resolution"] == "unresolved_max_turns"
    assert event["turns"] == 4


def test_case_event_rejects_unknown_fail_kind(run_ctx):
    event = build_case_event(
        NDJSON_RECORD, run=run_ctx, case_index=1, note="", acierto=False,
        fail_kind="",
    )
    assert event["fail_kind"] is None


# ── benchmark.run ─────────────────────────────────────────────────────────


def _stats():
    return {
        "total": 6, "ok": 3, "miss": 2, "miss_workflow": 1, "miss_outcome": 1,
        "unresolved": 1, "unresolved_max_turns": 1,
        "unresolved_needs_follow_up": 0, "skipped": 0,
        "tokens_in": 40000, "tokens_out": 1000, "tokens_cached": 10000,
        "models": {"gpt-a"},
        "routing_s": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "user_s": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        "routing_s_sum": 21.0, "user_s_sum": 24.0,
        "turns": [1, 1, 2, 1, 1, 4],
    }


def test_run_event_has_exact_contract_fields(run_ctx):
    metrics = _compute_metrics(_stats(), 123.45)
    event = build_run_event(
        metrics, run=run_ctx, timestamp="2026-09-08T13:10:00+00:00"
    )
    assert list(event.keys()) == RUN_FIELDS
    assert event == {
        "event": RUN_ROUTING_KEY,
        "timestamp": "2026-09-08T13:10:00+00:00",
        "source": "benchmark",
        "run_name": "doble_cobro_routing",
        "run_id": "doble_cobro_routing_20260908T130509Z",
        "catalog_version": "abc1234",
        "environment": "test",
        "flow": "doble_cobro_routing",
        "cases_total": 6,
        "cases_ok": 3,
        "cases_unresolved": 1,
        "precision_pct": 60.0,              # 3 de 5 evaluados
        "precision_workflow_pct": 80.0,     # (3 ok + 1 fallo de outcome) de 5
        "routing_p50_s": 4.0,
        "routing_p95_s": 6.0,
        "e2e_p50_s": 4.5,
        "e2e_p95_s": 6.5,
        "tokens_input_total": 40000,
        "tokens_output_total": 1000,
        "cache_hit_pct_avg": 25.0,
        "llm_model": "gpt-a",
        "duration_s": 123.5,
    }
    json.dumps(event)


def test_run_event_timestamp_defaults_to_now(run_ctx):
    event = build_run_event(_compute_metrics(_stats(), 1.0), run=run_ctx)
    parsed = datetime.fromisoformat(event["timestamp"])
    assert parsed.tzinfo is not None


def test_run_event_empty_run(run_ctx):
    stats = _stats()
    stats.update(
        total=0, ok=0, miss=0, miss_workflow=0, miss_outcome=0, unresolved=0,
        tokens_in=0, tokens_out=0, tokens_cached=0, models=set(),
        routing_s=[], user_s=[], turns=[],
    )
    event = build_run_event(_compute_metrics(stats, 0.0), run=run_ctx)
    assert event["precision_pct"] == 0.0
    assert event["precision_workflow_pct"] == 0.0
    assert event["llm_model"] == "(desconocido)"


# ── URL ───────────────────────────────────────────────────────────────────


def test_effective_url_matches_agent_format():
    s = make_settings(
        rabbitmq_host="rabbitmq.pqr-genai-dev.svc.cluster.local",
        rabbitmq_port=5672, rabbitmq_user="u@x", rabbitmq_password="p/w",
        rabbitmq_vhost="/",
    )
    assert effective_amqp_url(s) == (
        "amqp://u%40x:p%2Fw@rabbitmq.pqr-genai-dev.svc.cluster.local:5672/"
    )
    assert effective_amqp_url(dataclasses.replace(s, rabbitmq_vhost="pqr")).endswith("/pqr")
    assert effective_amqp_url(
        dataclasses.replace(s, rabbitmq_url="amqp://a:b@h:1/")
    ) == "amqp://a:b@h:1/"


# ── publicador ────────────────────────────────────────────────────────────


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_publish_connection_refused_does_not_raise():
    publisher = BenchmarkEventPublisher(
        make_settings(rabbitmq_host="127.0.0.1", rabbitmq_port=_closed_port())
    )
    assert publisher.publish(CASE_ROUTING_KEY, {"event": "x"}) is False
    assert publisher.publish(RUN_ROUTING_KEY, {"event": "y"}) is False
    assert publisher.failed == 2
    assert publisher.published == 0
    publisher.close()  # tampoco lanza


def test_publish_disabled_is_inert(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def forbid_pika(name, *args, **kwargs):
        if name == "pika":
            raise AssertionError("pika no debe importarse con RABBITMQ_ENABLED=false")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid_pika)
    publisher = BenchmarkEventPublisher(make_settings(rabbitmq_enabled=False))
    assert publisher.enabled is False
    assert publisher.publish(CASE_ROUTING_KEY, {"event": "x"}) is False
    assert publisher.failed == 0
    publisher.close()


class _FakeChannel:
    def __init__(self):
        self.declared = []
        self.published = []
        self.is_open = True

    def exchange_declare(self, **kwargs):
        self.declared.append(kwargs)

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)


class _FakeConnection:
    def __init__(self, params):
        self.params = params
        self.channel_obj = _FakeChannel()
        self.closed = False

    def channel(self):
        return self.channel_obj

    def close(self):
        self.closed = True


def test_exchange_declaration_and_message_match_agent(monkeypatch):
    import pika

    created = []

    def fake_connection(params):
        conn = _FakeConnection(params)
        created.append(conn)
        return conn

    monkeypatch.setattr(pika, "BlockingConnection", fake_connection)
    publisher = BenchmarkEventPublisher(make_settings())

    assert publisher.publish(CASE_ROUTING_KEY, {"event": "benchmark.case", "n": 1})
    assert publisher.publish(RUN_ROUTING_KEY, {"event": "benchmark.run", "ñ": "sí"})

    # Una sola conexion reutilizada; timeouts cortos y un solo intento.
    assert len(created) == 1
    params = created[0].params
    assert params.connection_attempts == 1
    assert params.socket_timeout == 1.0

    channel = created[0].channel_obj
    assert channel.declared == [
        {"exchange": "pqr.events", "exchange_type": "topic", "durable": True}
    ]
    assert [m["routing_key"] for m in channel.published] == [
        "benchmark.case", "benchmark.run",
    ]
    first = channel.published[0]
    assert first["exchange"] == "pqr.events"
    assert first["properties"].content_type == "application/json"
    assert first["properties"].delivery_mode == 2
    assert json.loads(first["body"]) == {"event": "benchmark.case", "n": 1}
    # UTF-8 sin escapar (ensure_ascii=False), como el agente.
    assert "sí".encode("utf-8") in channel.published[1]["body"]
    assert publisher.published == 2

    publisher.close()
    assert created[0].closed is True


def test_publish_failure_resets_connection_and_retries(monkeypatch):
    import pika

    created = []

    class _Boom(_FakeChannel):
        def basic_publish(self, **kwargs):
            raise RuntimeError("broker gone")

    def fake_connection(params):
        conn = _FakeConnection(params)
        if not created:
            conn.channel_obj = _Boom()
        created.append(conn)
        return conn

    monkeypatch.setattr(pika, "BlockingConnection", fake_connection)
    publisher = BenchmarkEventPublisher(make_settings())

    assert publisher.publish(CASE_ROUTING_KEY, {"event": "a"}) is False
    assert created[0].closed is True
    assert publisher.publish(CASE_ROUTING_KEY, {"event": "b"}) is True
    assert len(created) == 2
    assert publisher.failed == 1 and publisher.published == 1


@pytest.mark.parametrize("raw, expected", [("benchmark", "benchmark"), ("canario", "canario"), ("canary", "benchmark"), ("", "benchmark")])
def test_benchmark_source_is_validated(monkeypatch, raw, expected):
    """Un typo en el manifiesto no puede producir eventos que nadie vea."""

    monkeypatch.setenv("BENCHMARK_SOURCE", raw)
    assert load_settings().benchmark_source == expected


def test_breaker_resets_after_a_successful_publish(monkeypatch):
    publisher = BenchmarkEventPublisher(make_settings())
    publisher._consecutive_failures = events.MAX_CONSECUTIVE_FAILURES - 1

    class _Channel:
        is_open = True

        def basic_publish(self, **_):
            return None

    publisher._channel = _Channel()
    assert publisher.publish(CASE_ROUTING_KEY, {"event": "benchmark.case"}) is True
    assert publisher._consecutive_failures == 0
    assert publisher._disabled_after_failures is False
