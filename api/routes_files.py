from pathlib import Path
from typing import Any
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from api.context import MAX_UPLOAD_BYTES, bridge
from services.file_service import FileService

router = APIRouter()
service = FileService()

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
            return service.upload_data_file(agent, filename=file.filename or "upload.bin", content=content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"上传失败：{exc}") from exc

    return bridge.with_agent(_inner)

@router.get("/api/files")
def list_uploaded_files():
    def _inner(agent: Any):
        return service.list_uploaded_files(agent)

    return bridge.with_agent(_inner)

@router.get("/api/artifacts/{artifact_id}")
def download_artifact(artifact_id: str):
    def _inner(agent: Any):
        return service.get_artifact_download(agent, artifact_id=artifact_id)

    try:
        result = bridge.with_agent(_inner)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    def _inner(agent: Any):
        return service.list_artifacts(agent, limit=limit)

    return bridge.with_agent(_inner)
