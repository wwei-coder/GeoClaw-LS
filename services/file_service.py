from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from api.context import serialize_artifact

class FileService:
    def upload_data_file(self, agent: Any, *, filename: str, content: bytes) -> Dict[str, Any]:
        saved = agent.file_workspace.save_upload(filename or "upload.bin", content)
        return {"ok": True, "file": saved}

    def list_uploaded_files(self, agent: Any) -> Dict[str, Any]:
        return {"files": agent.file_workspace.list_files()}

    def list_artifacts(self, agent: Any, *, limit: int) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 200))
        store = getattr(agent, "task_store", None)
        if not store:
            return {"artifacts": []}
        artifacts = store.list_artifacts(task_id=None, limit=safe_limit)
        return {"artifacts": [serialize_artifact(a) for a in artifacts]}

    def get_artifact_download(self, agent: Any, *, artifact_id: str) -> Dict[str, Any]:
        item = agent.file_workspace.get_artifact(artifact_id)
        if item:
            return {"mode": "file", "file": item}
        store = getattr(agent, "task_store", None)
        if not store:
            raise ValueError("未找到指定分析产物")
        artifact = store.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError("未找到指定分析产物")
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
            raise FileNotFoundError("产物文件不存在或不可访问")
        payload["download_url"] = payload.get("url") or f"/api/artifacts/{artifact_id}"
        return {"mode": "metadata", "artifact": payload}
