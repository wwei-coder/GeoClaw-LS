from __future__ import annotations
from typing import Any, List, Optional

class TaskRepository:
    """Thin adapter for TaskStore methods used by runtime and APIs."""

    def __init__(self, task_store: Any):
        self.task_store = task_store

    def save_task(self, task: Any, session_id: Optional[Any] = None) -> None:
        self.task_store.save_task(task, session_id=session_id)

    def save_step(self, task_id: str, step: Any, position: int) -> None:
        self.task_store.save_step(task_id=task_id, step=step, position=position)

    def save_artifact(self, task_id: str, artifact: Any) -> None:
        self.task_store.save_artifact(task_id=task_id, artifact=artifact)

    def get_task(self, task_id: str) -> Optional[Any]:
        return self.task_store.get_task(task_id)

    def list_tasks(self, session_id: Optional[Any] = None, limit: int = 50) -> List[Any]:
        return self.task_store.list_tasks(session_id=session_id, limit=limit)

    def list_artifacts(self, task_id: Optional[str] = None, limit: int = 50) -> List[Any]:
        return self.task_store.list_artifacts(task_id=task_id, limit=limit)

    def get_artifact(self, artifact_id: str) -> Optional[Any]:
        return self.task_store.get_artifact(artifact_id)
