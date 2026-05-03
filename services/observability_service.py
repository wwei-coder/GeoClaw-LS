from __future__ import annotations

from typing import Any, Dict

from api.context import read_observability_enabled_from_config, write_observability_enabled_to_config


class ObservabilityService:
    def status(self) -> Dict[str, Any]:
        try:
            from utils.phoenix_monitor import get_phoenix_status

            status = get_phoenix_status()
            enabled = bool(status.get("launched") or status.get("starting"))
            configured_enabled = read_observability_enabled_from_config()
            return {
                "ok": True,
                "enabled": enabled,
                "configured_enabled": configured_enabled,
                "status": status,
            }
        except ImportError:
            return {
                "ok": True,
                "enabled": False,
                "configured_enabled": False,
                "status": {"launched": False, "starting": False, "url": "http://localhost:6006"},
            }

    def toggle(self, *, enabled: bool) -> Dict[str, Any]:
        from utils.phoenix_monitor import get_phoenix_status, launch_phoenix_monitor, shutdown_phoenix_monitor

        if enabled:
            launch_phoenix_monitor()
        else:
            shutdown_phoenix_monitor()

        status = get_phoenix_status()
        now_enabled = bool(status.get("launched") or status.get("starting"))
        write_observability_enabled_to_config(now_enabled)
        return {
            "ok": True,
            "enabled": now_enabled,
            "configured_enabled": now_enabled,
            "status": status,
        }
