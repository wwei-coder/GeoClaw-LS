from __future__ import annotations
from typing import Any, Dict, List, Optional

class ArtifactStore:
    """Thin wrapper for artifact records across task store and file workspace."""

    def __init__(self, *, file_workspace: Any = None, task_repository: Any = None):
        self.file_workspace = file_workspace
        self.task_repository = task_repository

    def list_artifacts(self, *, task_id: Optional[str] = None, limit: int = 50) -> List[Any]:
        if self.task_repository is None:
            return []
        return self.task_repository.list_artifacts(task_id=task_id, limit=limit)

    def get_artifact(self, artifact_id: str) -> Optional[Any]:
        if self.file_workspace is not None:
            item = self.file_workspace.get_artifact(artifact_id)
            if item is not None:
                return item
        if self.task_repository is None:
            return None
        return self.task_repository.get_artifact(artifact_id)

    def register_artifact(
        self,
        *,
        name: str,
        content: str,
        mime_type: str = "text/markdown; charset=utf-8",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.file_workspace is None:
            raise ValueError("file_workspace 不可用，无法注册文件产物")
        return self.file_workspace.save_artifact(
            name=name,
            content=content,
            mime_type=mime_type,
            metadata=metadata,
        )

    def resolve_artifact_path(self, artifact_id: str) -> Optional[str]:
        item = self.get_artifact(artifact_id)
        if item is None:
            return None
        if hasattr(item, "path"):
            return str(getattr(item, "path") or "")
        if isinstance(item, dict):
            return str(item.get("path") or item.get("abs_path") or "")
        return None
