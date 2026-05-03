from __future__ import annotations

from typing import Any, Dict

import yaml

from api.context import (
    CONFIG_PATH,
    DEFAULT_CONFIG_PATH,
    flatten_config,
    read_yaml,
    write_yaml,
)


class ConfigService:
    EFFECTIVE_PROVIDER = "ollama"
    PROVIDER_LOCK_REASON = "当前版本强制本地 Ollama-only，models.api.* 不会生效"
    IGNORED_PATHS = ["models.provider", "models.api.*"]

    def _build_effective_runtime(self) -> Dict[str, Any]:
        return {
            "effective_provider": self.EFFECTIVE_PROVIDER,
            "provider_locked": True,
            "provider_lock_reason": self.PROVIDER_LOCK_REASON,
            "ignored_paths": list(self.IGNORED_PATHS),
        }

    def get_config(self) -> Dict[str, Any]:
        data = read_yaml(CONFIG_PATH)
        defaults = read_yaml(DEFAULT_CONFIG_PATH)
        return {
            "data": data,
            "defaults": defaults,
            "items": flatten_config(data),
            "effective": self._build_effective_runtime(),
        }

    def save_config(self, agent: Any, *, data: Dict[str, Any]) -> Dict[str, Any]:
        write_yaml(CONFIG_PATH, data)
        try:
            temp = data.get("models", {}).get("ollama", {}).get("temperature")
            if temp is not None:
                agent.temperature = float(temp)
        except (TypeError, ValueError):
            pass
        return {
            "ok": True,
            "effective": self._build_effective_runtime(),
            "warning": self.PROVIDER_LOCK_REASON,
        }

    def reset_config(self) -> Dict[str, Any]:
        defaults = read_yaml(DEFAULT_CONFIG_PATH)
        if not defaults:
            raise FileNotFoundError("未找到默认配置")
        write_yaml(CONFIG_PATH, defaults)
        return {"ok": True}

    def export_config(self) -> str:
        data = read_yaml(CONFIG_PATH)
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    def import_config(self, *, raw: bytes) -> Dict[str, Any]:
        loaded = yaml.safe_load(raw.decode("utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("模板根节点必须是对象")
        write_yaml(CONFIG_PATH, loaded)
        return {"ok": True}
