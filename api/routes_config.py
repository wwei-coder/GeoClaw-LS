from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
import yaml
from api.context import (
    CONFIG_PATH,
    DEFAULT_CONFIG_PATH,
    SaveConfigRequest,
    bridge,
    flatten_config,
    read_yaml,
    write_yaml,
)

router = APIRouter()


@router.get("/api/config")
def get_config():
    data = read_yaml(CONFIG_PATH)
    defaults = read_yaml(DEFAULT_CONFIG_PATH)
    return {
        "data": data,
        "defaults": defaults,
        "items": flatten_config(data),
    }


@router.put("/api/config")
def save_config(req: SaveConfigRequest):
    write_yaml(CONFIG_PATH, req.data)

    def _inner(agent):
        try:
            temp = req.data.get("models", {}).get("ollama", {}).get("temperature")
            if temp is not None:
                agent.temperature = float(temp)
        except (TypeError, ValueError):
            pass
        return {"ok": True}

    return bridge.with_agent(_inner)


@router.post("/api/config/reset")
def reset_config():
    defaults = read_yaml(DEFAULT_CONFIG_PATH)
    if not defaults:
        raise HTTPException(status_code=404, detail="未找到默认配置")
    write_yaml(CONFIG_PATH, defaults)
    return {"ok": True}


@router.get("/api/config/export")
def export_config():
    data = read_yaml(CONFIG_PATH)
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return PlainTextResponse(content=dumped, media_type="text/yaml; charset=utf-8")


@router.post("/api/config/import")
async def import_config(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        loaded = yaml.safe_load(raw.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"解析 YAML 失败: {e}") from e
    if not isinstance(loaded, dict):
        raise HTTPException(status_code=400, detail="模板根节点必须是对象")
    write_yaml(CONFIG_PATH, loaded)
    return {"ok": True}
