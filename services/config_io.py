from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import yaml

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_ROOT / "config" / "config.yaml"
DEFAULT_CONFIG_PATH = APP_ROOT / "config" / "config.default.yaml"

def read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} 根节点必须为对象")
    return loaded

def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

def read_observability_enabled_from_config() -> bool:
    data = read_yaml(CONFIG_PATH)
    obs = data.get("observability", {})
    if not isinstance(obs, dict):
        return False
    return bool(obs.get("enabled", False))

def write_observability_enabled_to_config(enabled: bool) -> None:
    data = read_yaml(CONFIG_PATH)
    obs = data.get("observability")
    if not isinstance(obs, dict):
        obs = {}
    obs["enabled"] = bool(enabled)
    data["observability"] = obs
    write_yaml(CONFIG_PATH, data)
