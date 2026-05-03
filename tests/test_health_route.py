from __future__ import annotations

import api.context as context_module
import api.routes_health as health_module


def test_health_payload_compatible(monkeypatch):
    monkeypatch.setattr(health_module, "AGENT_CORE_CTOR", object)
    monkeypatch.setattr(health_module, "RAG_IMPORT_ERROR", None)

    payload = health_module.health()

    assert payload["ok"] is True
    assert "app_root" in payload
    assert "config_path" in payload
    assert "default_config_path" in payload
    assert "config_exists" in payload
    assert "agent_import_ok" in payload
    assert "agent_import_error" in payload
    assert payload["agent_import_ok"] is True


def test_health_route_no_agent_init_and_logs(monkeypatch):
    called = {"get_agent": 0, "log": 0}

    def _boom():
        called["get_agent"] += 1
        raise AssertionError("health route should not initialize agent")

    class _FakeLogger:
        def info(self, *args, **kwargs):
            _ = (args, kwargs)
            called["log"] += 1

    monkeypatch.setattr(context_module.bridge, "get_agent", _boom)
    monkeypatch.setattr(health_module, "logger", _FakeLogger())
    monkeypatch.setattr(health_module, "AGENT_CORE_CTOR", None)
    monkeypatch.setattr(health_module, "RAG_IMPORT_ERROR", "import-failed")

    payload = health_module.health()

    assert payload["ok"] is True
    assert payload["agent_import_ok"] is False
    assert payload["agent_import_error"] == "import-failed"
    assert called["get_agent"] == 0
    assert called["log"] == 1
