import re
import os
import time
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from api.context import APP_ROOT, MAX_UPLOAD_BYTES, bridge

router = APIRouter()
KB_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
KB_DATA_DIR = APP_ROOT / "data"


def _safe_name(file_name: str) -> str:
    name = Path(file_name or "").name.strip()
    name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name)
    return name or "knowledge.txt"


def _reserve_unique_path(base_dir: Path, file_name: str) -> Path:
    candidate = (base_dir / file_name).resolve()
    if base_dir not in candidate.parents:
        raise HTTPException(status_code=400, detail="文件名非法")
    if not candidate.exists():
        return candidate
    stem = Path(file_name).stem or "knowledge"
    suffix = Path(file_name).suffix
    for idx in range(1, 1000):
        named = f"{stem}_{idx}{suffix}"
        next_path = (base_dir / named).resolve()
        if base_dir in next_path.parents and not next_path.exists():
            return next_path
    raise HTTPException(status_code=500, detail="同名文件过多，请先清理后重试")

@router.post("/api/kb/sync")
def sync_kb():
    def _inner(agent: Any):
        return agent.sync_knowledge_base_now()

    return bridge.with_agent(_inner)

@router.get("/api/kb/status")
def kb_status():
    def _inner(agent: Any):
        return agent.get_knowledge_base_status()

    return bridge.with_agent(_inner)

@router.get("/api/kb/documents")
def kb_documents():
    def _inner(agent: Any):
        return {"documents": agent.get_document_index_stats()}

    return bridge.with_agent(_inner)

@router.get("/api/kb/diagnostics")
def kb_diagnostics(limit: int = 20):
    safe_limit = max(1, min(limit, 100))

    def _inner(agent: Any):
        return agent.get_retrieval_diagnostics(limit=safe_limit)

    return bridge.with_agent(_inner)

@router.post("/api/kb/rebuild")
def kb_rebuild():
    def _inner(agent: Any):
        return agent.rebuild_knowledge_base_now()

    return bridge.with_agent(_inner)

@router.post("/api/system/reset")
def system_reset():
    def _inner(agent: Any):
        agent.factory_reset()
        return {"ok": True, "message": "已触发系统重置，下一次请求将重新初始化引擎。"}

    result = bridge.with_agent(_inner)
    bridge.reset_agent()
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
    if not content:
        raise HTTPException(status_code=400, detail="文件为空，请重新选择")

    KB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_name(file.filename or f"knowledge{suffix}")
    target_path = _reserve_unique_path(KB_DATA_DIR.resolve(), safe_name)

    try:
        target_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存失败：{exc}") from exc

    return {
        "ok": True,
        "file": {
            "original_name": file.filename or safe_name,
            "saved_name": target_path.name,
            "size": len(content),
            "relative_path": str(Path("data") / target_path.name),
        },
    }
