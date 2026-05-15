import os
import time
from pathlib import Path
from typing import Any
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from api.context import APP_ROOT, MAX_UPLOAD_BYTES, bridge
from services.knowledge_base_service import KnowledgeBaseService

router = APIRouter()
service = KnowledgeBaseService()
KB_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
KB_DATA_DIR = APP_ROOT / "data"

@router.post("/api/kb/sync")
def sync_kb():
    def _inner(agent: Any):
        return service.sync(agent)

    return bridge.with_agent(_inner)

@router.get("/api/kb/status")
def kb_status():
    def _inner(agent: Any):
        return service.status(agent)

    return bridge.with_agent(_inner)

@router.get("/api/kb/documents")
def kb_documents():
    def _inner(agent: Any):
        return service.documents(agent)

    return bridge.with_agent(_inner)

@router.get("/api/kb/diagnostics")
def kb_diagnostics(limit: int = 20):
    def _inner(agent: Any):
        return service.diagnostics(agent, limit=limit)

    return bridge.with_agent(_inner)

@router.post("/api/kb/rebuild")
def kb_rebuild():
    def _inner(agent: Any):
        return service.rebuild(agent)

    return bridge.with_agent(_inner)

@router.post("/api/system/reset")
def system_reset(background_tasks: BackgroundTasks):
    def _inner(agent: Any):
        return service.system_reset(agent)

    result = bridge.with_agent(_inner)
    bridge.enter_reset_pending()
    background_tasks.add_task(_shutdown_process)
    return result


def _shutdown_process() -> None:
    # 延迟一小段时间，确保 HTTP 响应先返回给前端。
    time.sleep(0.35)
    os._exit(0)


@router.post("/api/system/shutdown")
def system_shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(_shutdown_process)
    return {"ok": True, "message": "服务即将关闭"}


@router.post("/api/kb/upload")
async def kb_upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in KB_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持上传 .pdf/.docx/.txt 文件")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"文件过大，单文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
    try:
        return service.save_kb_upload(
            filename=file.filename or f"knowledge{suffix}",
            content=content,
            data_dir=KB_DATA_DIR,
        )
    except ValueError as exc:
        if str(exc) in {"文件为空，请重新选择", "文件名非法"}:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise
    except FileExistsError as exc:
        if str(exc) == "同名文件过多，请先清理后重试":
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存失败：{exc}") from exc
