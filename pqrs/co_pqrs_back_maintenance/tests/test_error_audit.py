from __future__ import annotations

from unittest.mock import patch

import commons.error_audit as audit

from helpers import make_settings


def test_report_job_failure_noop_without_url() -> None:
    settings = make_settings(error_handler_service_url=None)
    with patch.object(audit.urllib.request, "urlopen") as mock_open:
        audit.report_job_failure(settings, ValueError("x"), source="run_maintenance_job")
    mock_open.assert_not_called()


def test_report_job_failure_posts_payload() -> None:
    settings = make_settings(error_handler_service_url="http://eh:8002")
    captured = {}

    class _Resp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(request, timeout=None):
        import json

        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Resp()

    with patch.object(audit.urllib.request, "urlopen", new=_fake_urlopen):
        audit.report_job_failure(
            settings, RuntimeError("opensearch down"), source="run_maintenance_job"
        )

    assert captured["url"] == "http://eh:8002/v0/error-reports"
    assert captured["payload"]["component"] == "co_pqrs_back_maintenance"
    assert captured["payload"]["error_type"] == "RuntimeError"
    assert captured["payload"]["conversation_id"] is None
    assert "traceback" in captured["payload"]["extra_context"]


def test_report_job_failure_swallows_errors() -> None:
    settings = make_settings(error_handler_service_url="http://eh:8002")

    def _boom(request, timeout=None):
        raise OSError("connection refused")

    with patch.object(audit.urllib.request, "urlopen", new=_boom):
        # Must not raise.
        audit.report_job_failure(settings, ValueError("x"), source="run_maintenance_job")
