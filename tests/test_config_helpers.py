import core.config as config


def test_to_bool_variants():
    assert config.to_bool(True) is True
    assert config.to_bool("true") is True
    assert config.to_bool("off") is False
    assert config.to_bool(0) is False
    assert config.to_bool("unknown", default=True) is True


def test_get_config_nested_and_default(monkeypatch):
    monkeypatch.setattr(config, "_config", {"a": {"b": 1}, "x": None})
    assert config.get_config("a.b", 0) == 1
    assert config.get_config("a.c", 9) == 9
    assert config.get_config("x", 7) == 7
