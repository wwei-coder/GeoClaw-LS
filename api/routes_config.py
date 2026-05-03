from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
import yaml
from api.context import (
    SaveConfigRequest,
    bridge,
)
from services.config_service import ConfigService

router = APIRouter()
service = ConfigService()

@router.get("/api/config")
def get_config():
    return service.get_config()

@router.put("/api/config")
def save_config(req: SaveConfigRequest):
    def _inner(agent):
        return service.save_config(agent, data=req.data)

    return bridge.with_agent(_inner)


@router.post("/api/config/reset")
def reset_config():
    try:
        return service.reset_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

@router.get("/api/config/export")
def export_config():
    dumped = service.export_config()
    return PlainTextResponse(content=dumped, media_type="text/yaml; charset=utf-8")

@router.post("/api/config/import")
async def import_config(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        return service.import_config(raw=raw)
    except (UnicodeDecodeError, yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"解析 YAML 失败: {e}") from e
