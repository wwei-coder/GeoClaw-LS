import asyncio
import sys
import types

import api.context as context_module
import app as app_module
import core.reset_handler as reset_handler


def test_consume_reset_flag_once_calls_perform_once(monkeypatch):
    calls = {"count": 0}

    def fake_perform_reset_if_needed():
        calls["count"] += 1

    monkeypatch.setattr(reset_handler, "_RESET_CHECK_PERFORMED", False)
    monkeypatch.setattr(reset_handler, "perform_reset_if_needed", fake_perform_reset_if_needed)

    reset_handler.consume_reset_flag_once()
    reset_handler.consume_reset_flag_once()

    assert calls["count"] == 1


def test_bridge_get_agent_consumes_reset_before_init(monkeypatch):
    calls = {"count": 0}

    def fake_perform_reset_if_needed():
        calls["count"] += 1

    class FakeAgent:
        pass

    monkeypatch.setattr(reset_handler, "_RESET_CHECK_PERFORMED", False)
    monkeypatch.setattr(reset_handler, "perform_reset_if_needed", fake_perform_reset_if_needed)
    monkeypatch.setattr(context_module, "AGENT_CORE_CTOR", FakeAgent)

    bridge = context_module.RAGBridge()
    first = bridge.get_agent()
    second = bridge.get_agent()

    assert isinstance(first, FakeAgent)
    assert first is second
    assert calls["count"] == 1


def test_lifespan_consumes_reset_flag_on_startup(monkeypatch):
    calls = {"count": 0}

    def fake_consume_reset_flag_once():
        calls["count"] += 1

    fake_monitor = types.SimpleNamespace(
        launch_phoenix_monitor=lambda: None,
        shutdown_phoenix_monitor=lambda: None,
    )

    monkeypatch.setattr(reset_handler, "consume_reset_flag_once", fake_consume_reset_flag_once)
    monkeypatch.setattr(app_module, "read_observability_enabled_from_config", lambda: False)
    monkeypatch.setitem(sys.modules, "utils.phoenix_monitor", fake_monitor)

    async def _run():
        async with app_module.lifespan(app_module.app):
            return None

    asyncio.run(_run())
    assert calls["count"] == 1
