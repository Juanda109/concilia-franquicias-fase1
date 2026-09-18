"""El job publica benchmark.case con la MISMA evaluacion que su precision,
manda la cabecera X-Benchmark-Mode en /start, /chat y /end, y sigue igual
aunque RabbitMQ no exista."""

import json
import socket
from datetime import UTC, datetime

import requests

from src.benchmark import events, job
from src.benchmark.events import BenchmarkEventPublisher, RunContext
from tests.test_events import make_settings


class _RecordingPublisher:
    enabled = True

    def __init__(self):
        self.events = []

    def publish(self, routing_key, payload):
        self.events.append((routing_key, payload))
        return True

    def close(self):
        pass


def _fake_case(workflow_result, outcome, *, resolution="resolved", turns=1):
    turn_log = [
        {
            "turn": i + 1, "reply_source": "dataset", "user_input": "q",
            "workflow_result": workflow_result, "workflow_llm": workflow_result,
            "routing_outcome": outcome, "confidence": "high",
            "prefilter_groups": [], "llm_token_input": 100,
            "llm_token_output": 10, "llm_token_cached": 50,
            "routing_time_s": 1.0, "user_time_s": 1.5,
            "user_output": "", "user_options": [],
        }
        for i in range(turns)
    ]
    bench = {
        "workflow_result": workflow_result, "workflow_llm": workflow_result,
        "routing_outcome": outcome, "confidence": "high", "llm_model": "m1",
    }
    return {
        "conversation_id": "11111111_20260908", "bench": bench,
        "response_data": {"status": "Active"},
        "content_data": {"label": "", "options": []},
        "turn_log": turn_log, "resolution": resolution,
    }


DATASET = [
    {"question": "ok", "expect_output": "doble_cobro", "nota": "n1"},
    {"question": "wf miss", "expect_output": "doble_cobro", "nota": "n2"},
    {"question": "outcome miss", "expect_output": "doble_cobro",
     "expect_outcome": "matched", "nota": "n3"},
    {"question": "open", "expect_output": "doble_cobro", "nota": "n4"},
    {"question": "skipped", "expect_output": "doble_cobro", "nota": "n5"},
]

CASES = {
    "ok": _fake_case("doble_cobro", "matched"),
    "wf miss": _fake_case("trx_no_reconocida", "matched"),
    "outcome miss": _fake_case("doble_cobro", "confirmation"),
    "open": _fake_case("", "confirmation", resolution="unresolved_max_turns", turns=4),
}


def _run_with(monkeypatch, publisher):
    def fake_run_case(question, follow_ups, user_id=None):
        if question == "skipped":
            raise RuntimeError("/start HTTP 500")
        return CASES[question]

    monkeypatch.setattr(job, "_run_case", fake_run_case)
    lines = []
    run = RunContext.build(
        make_settings(), input_source="x/doble_cobro_routing.json",
        started_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    stats = job.process_questions(DATASET, lines.append, publisher=publisher, run=run)
    return stats, lines


def test_case_events_mirror_ndjson_and_evaluation(monkeypatch):
    publisher = _RecordingPublisher()
    stats, lines = _run_with(monkeypatch, publisher)

    # La precision del job: 1 ok, 2 fallos (workflow, outcome), 1 abierto, 1 saltado.
    assert (stats["ok"], stats["miss_workflow"], stats["miss_outcome"],
            stats["unresolved"], stats["skipped"]) == (1, 1, 1, 1, 1)

    # Un evento por caso medido (el saltado no tiene registro que transcribir).
    assert [k for k, _ in publisher.events] == ["benchmark.case"] * 4
    by_index = {p["case_index"]: p for _, p in publisher.events}
    assert sorted(by_index) == [1, 2, 3, 4]

    assert (by_index[1]["acierto"], by_index[1]["fail_kind"]) == (True, None)
    assert (by_index[2]["acierto"], by_index[2]["fail_kind"]) == (False, "workflow")
    assert (by_index[3]["acierto"], by_index[3]["fail_kind"]) == (False, "outcome")
    assert (by_index[4]["acierto"], by_index[4]["fail_kind"]) == (False, None)
    assert by_index[4]["resolution"] == "unresolved_max_turns"
    assert [by_index[i]["note"] for i in (1, 2, 3, 4)] == ["n1", "n2", "n3", "n4"]

    # Mismos valores que el NDJSON, campo a campo.
    records = [json.loads(line) for line in lines]
    for record, index in zip(records, (1, 2, 3, 4)):
        event = by_index[index]
        for field in (
            "conversation_id", "timestamp", "workflow_expect", "outcome_expect",
            "workflow_result", "workflow_llm", "routing_outcome", "confidence",
            "llm_model", "llm_token_input", "llm_token_output", "llm_token_cached",
            "llm_token_cache_hit_pct", "routing_time_total_s", "user_time_total_s",
            "turns", "resolution", "user_input",
        ):
            assert event[field] == record[field], field
    assert by_index[4]["turns"] == 4
    assert by_index[4]["llm_token_cached"] == 200


def test_job_survives_unreachable_rabbitmq(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    publisher = BenchmarkEventPublisher(
        make_settings(rabbitmq_host="127.0.0.1", rabbitmq_port=port)
    )
    stats, lines = _run_with(monkeypatch, publisher)
    assert len(lines) == 4
    assert stats["ok"] == 1 and stats["skipped"] == 1
    # Cortacircuito: tras MAX_CONSECUTIVE_FAILURES fallos seguidos deja de
    # intentar, asi que no paga el timeout en los 4 casos.
    assert publisher.published == 0
    assert publisher.failed == events.MAX_CONSECUTIVE_FAILURES
    assert publisher._disabled_after_failures is True


def test_publisher_none_keeps_legacy_behaviour(monkeypatch):
    def fake_run_case(question, follow_ups, user_id=None):
        return CASES["ok"]

    monkeypatch.setattr(job, "_run_case", fake_run_case)
    lines = []
    stats = job.process_questions(DATASET[:1], lines.append)
    assert stats["ok"] == 1 and len(lines) == 1


def test_benchmark_header_on_start_chat_and_end(monkeypatch):
    calls = []

    class _Resp:
        def __init__(self, status, body, headers=None):
            self.status_code = status
            self._body = body
            self.headers = headers or {}
            self.text = json.dumps(body)

        def json(self):
            return self._body

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url.rsplit("/", 1)[-1], headers, timeout))
        if url.endswith("/start"):
            return _Resp(201, {"conversation_id": "12345678_20260908"})
        if url.endswith("/chat"):
            bench = {"workflow_result": "doble_cobro", "routing_outcome": "matched"}
            return _Resp(
                200, {"message": {"content": {"label": "ok", "options": []}}},
                headers={"X-Benchmark-Data": __import__("json").dumps(bench)},
            )
        if url.endswith("/end"):
            return _Resp(201, {"status": "Closed"})
        raise AssertionError(url)

    monkeypatch.setattr(requests, "post", fake_post)
    case = job._run_case("Me cobraron dos veces.", [])

    assert [c[0] for c in calls] == ["start", "chat", "end"]
    for _, headers, _ in calls:
        assert headers == {"X-Benchmark-Mode": "true"}
    assert case["resolution"] == "resolved"
    assert case["conversation_id"] == "12345678_20260908"


def test_end_failure_does_not_break_case(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        if url.endswith("/end"):
            raise requests.ConnectionError("boom")

        class _R:
            status_code = 201 if url.endswith("/start") else 200
            headers = {"X-Benchmark-Data": '{"workflow_result": "x", "routing_outcome": "matched"}'}
            text = ""

            def json(self):
                return (
                    {"conversation_id": "1_20260908"} if url.endswith("/start")
                    else {"message": {"content": {}}}
                )

        return _R()

    monkeypatch.setattr(requests, "post", fake_post)
    case = job._run_case("q", [])
    assert case["resolution"] == "resolved"
