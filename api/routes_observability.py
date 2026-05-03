from fastapi import APIRouter, HTTPException
from api.context import (
    ObservabilityToggleRequest,
)
from services.observability_service import ObservabilityService

router = APIRouter()
service = ObservabilityService()

@router.get("/api/observability/status")
def observability_status():
    try:
        return service.status()
    except ImportError:
        return service.status()

@router.post("/api/observability/toggle")
def toggle_observability(req: ObservabilityToggleRequest):
    try:
        return service.toggle(enabled=req.enabled)
    except (ImportError, OSError, RuntimeError, ValueError) as e:
        action = "启用" if req.enabled else "关闭"
        raise HTTPException(status_code=500, detail=f"{action}观测链路失败: {e}") from e
