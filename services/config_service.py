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
from services.config_metadata import apply_editable_subset, build_metadata_payload

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
        items = flatten_config(data)
        metadata = build_metadata_payload(data, defaults, items)
        return {
            "data": data,
            "defaults": defaults,
            "items": items,
            "metadata": metadata,
            "categories": metadata.get("categories", []),
            "effects": metadata.get("effects", []),
            "risks": metadata.get("risks", []),
            "levels": metadata.get("levels", []),
            "editable_items_enriched": metadata.get("editable_items_enriched", []),
            "effective": self._build_effective_runtime(),
        }

    def save_config(self, agent: Any, *, data: Dict[str, Any]) -> Dict[str, Any]:
        current = read_yaml(CONFIG_PATH)
        current_items = flatten_config(current)
        editable_paths = [str(item.get("path") or "") for item in current_items if item.get("path")]
        merged = apply_editable_subset(current, data, editable_paths)
        write_yaml(CONFIG_PATH, merged)
        try:
            temp = merged.get("models", {}).get("ollama", {}).get("temperature")
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
