from pathlib import Path
from typing import Any
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from api.context import MAX_UPLOAD_BYTES, bridge, serialize_artifact

router = APIRouter()

@router.post("/api/files/upload")
async def upload_data_file(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls", ".txt", ".json"}:
        raise HTTPException(status_code=400, detail="仅支持上传 .csv/.xlsx/.xls/.txt/.json 文件")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"文件过大，单文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")

    def _inner(agent: Any):
        try:
            saved = agent.file_workspace.save_upload(file.filename or "upload.bin", content)
            return {"ok": True, "file": saved}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"上传失败：{exc}") from exc

    return bridge.with_agent(_inner)

@router.get("/api/files")
def list_uploaded_files():
    def _inner(agent: Any):
        return {"files": agent.file_workspace.list_files()}

    return bridge.with_agent(_inner)

@router.get("/api/artifacts/{artifact_id}")
def download_artifact(artifact_id: str):
    def _inner(agent: Any):
        item = agent.file_workspace.get_artifact(artifact_id)
        if item:
            return {"mode": "file", "file": item}
        store = getattr(agent, "task_store", None)
        if not store:
            raise HTTPException(status_code=404, detail="未找到指定分析产物")
        artifact = store.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="未找到指定分析产物")
        payload = serialize_artifact(artifact)
        rel_path = str(payload.get("path") or "").strip()
        if rel_path:
            abs_path = (agent.file_workspace.root / rel_path).resolve()
            if abs_path.exists() and agent.file_workspace.artifacts_dir in abs_path.parents:
                return {
                    "mode": "file",
                    "file": {
                        "abs_path": str(abs_path),
                        "mime_type": payload.get("mime_type"),
                        "name": payload.get("name") or f"{artifact_id}.bin",
                    },
                }
            raise HTTPException(status_code=404, detail="产物文件不存在或不可访问")
        payload["download_url"] = payload.get("url") or f"/api/artifacts/{artifact_id}"
        return {"mode": "metadata", "artifact": payload}

    result = bridge.with_agent(_inner)
    if result.get("mode") == "metadata":
        return {"artifact": result.get("artifact", {})}
    artifact = result.get("file", {})
    return FileResponse(
        path=artifact["abs_path"],
        media_type=artifact.get("mime_type") or "application/octet-stream",
        filename=artifact.get("name") or f"{artifact_id}.bin",
    )

@router.get("/api/artifacts")
def list_artifacts(limit: int = 50):
    safe_limit = max(1, min(int(limit or 50), 200))

    def _inner(agent: Any):
        store = getattr(agent, "task_store", None)
        if not store:
            return {"artifacts": []}
        artifacts = store.list_artifacts(task_id=None, limit=safe_limit)
        return {"artifacts": [serialize_artifact(a) for a in artifacts]}

    return bridge.with_agent(_inner)
