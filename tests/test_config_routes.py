from __future__ import annotations

import api.routes_config as routes_config_module


def test_get_config_route_returns_effective_payload(monkeypatch):
    expected = {
        "data": {"models": {"provider": "openai_compatible"}},
        "defaults": {},
        "items": [],
        "effective": {
            "effective_provider": "ollama",
            "provider_locked": True,
            "provider_lock_reason": "当前版本强制本地 Ollama-only，models.api.* 不会生效",
            "ignored_paths": ["models.provider", "models.api.*"],
        },
    }

    monkeypatch.setattr(routes_config_module.service, "get_config", lambda: expected)

    payload = routes_config_module.get_config()

    assert payload["effective"]["effective_provider"] == "ollama"
    assert payload["effective"]["provider_locked"] is True
    assert payload == expected
