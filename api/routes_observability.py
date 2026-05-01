from fastapi import APIRouter, HTTPException
from api.context import (
    ObservabilityToggleRequest,
    read_observability_enabled_from_config,
    write_observability_enabled_to_config,
)

router = APIRouter()

@router.get("/api/observability/status")
def observability_status():
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

@router.post("/api/observability/toggle")
def toggle_observability(req: ObservabilityToggleRequest):
    try:
        from utils.phoenix_monitor import (
            get_phoenix_status,
            launch_phoenix_monitor,
            shutdown_phoenix_monitor,
        )

        if req.enabled:
            launch_phoenix_monitor()
        else:
            shutdown_phoenix_monitor()

        status = get_phoenix_status()
        enabled = bool(status.get("launched") or status.get("starting"))
        write_observability_enabled_to_config(enabled)
        return {
            "ok": True,
            "enabled": enabled,
            "configured_enabled": enabled,
            "status": status,
        }
    except (ImportError, OSError, RuntimeError, ValueError) as e:
        action = "启用" if req.enabled else "关闭"
        raise HTTPException(status_code=500, detail=f"{action}观测链路失败: {e}") from e
