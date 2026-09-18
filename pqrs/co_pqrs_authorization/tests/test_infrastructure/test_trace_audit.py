"""Trazas MinIO: no-op sin URL, fire-and-forget, no rompe el flujo."""

from unittest.mock import patch

from infrastructure.observability import trace_audit


def test_no_op_sin_error_handler_url():
    with patch.object(trace_audit, "load_error_handler_service_url", lambda: ""):
        with patch.object(trace_audit, "_post_trace_event") as post:
            trace_audit.schedule_trace_event(
                event_type="authorization", operation="authorization_created",
                conversation_id="c1",
            )
            post.assert_not_called()


def test_emite_cuando_hay_url(monkeypatch):
    llamadas = []

    async def _fake_post(base_url, payload):
        llamadas.append((base_url, payload))

    monkeypatch.setattr(trace_audit, "load_error_handler_service_url",
                        lambda: "http://error-handler:8002")
    monkeypatch.setattr(trace_audit, "_post_trace_event", _fake_post)
    trace_audit.schedule_trace_event(
        event_type="authorization", operation="authorization_resolved",
        outcome="accepted", conversation_id="c1",
        tags=["authorization", "trx_no_reconocida", "resolved", "ACCEPTED"],
    )
    assert len(llamadas) == 1
    _base, payload = llamadas[0]
    assert payload["component"] == "co_pqrs_authorization"
    assert payload["operation"] == "authorization_resolved"
    assert payload["conversation_id"] == "c1"


def test_error_del_post_no_propaga(monkeypatch):
    async def _boom(base_url, payload):
        raise RuntimeError("error_handler caido")

    monkeypatch.setattr(trace_audit, "load_error_handler_service_url",
                        lambda: "http://error-handler:8002")
    monkeypatch.setattr(trace_audit, "_post_trace_event", _boom)
    trace_audit.schedule_trace_event(
        event_type="authorization", operation="authorization_created",
        conversation_id="c1",
    )
