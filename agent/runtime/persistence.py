from __future__ import annotations

from typing import Any, Optional

from storage.sqlite import TaskRepository
from utils.logger import logger

class RuntimePersistence:
    """Runtime-side persistence helper for task/step/artifact writes."""

    def __init__(
        self,
        agent_core: Any = None,
        *,
        task_store: Optional[Any] = None,
        task_repository: Optional[Any] = None,
        session_provider: Optional[Any] = None,
    ):
        self.agent_core = agent_core
        self.task_store = task_store or getattr(agent_core, "task_store", None)
        self.task_repository = task_repository or (TaskRepository(self.task_store) if self.task_store is not None else None)
        self.session_provider = session_provider

    def _get_session_id(self) -> Optional[Any]:
        if callable(self.session_provider):
            try:
                return self.session_provider()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"[RuntimePersistence] 获取会话ID失败: {exc}")
                return None
        if self.agent_core is not None:
            getter = getattr(self.agent_core, "get_active_session_id", None)
            if callable(getter):
                try:
                    return getter()
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"[RuntimePersistence] 调用 get_active_session_id 失败: {exc}")
        return None

    def save_task(self, task: Any) -> None:
        if not self.task_repository:
            return
        try:
            self.task_repository.save_task(task, session_id=self._get_session_id())
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[RuntimePersistence] 保存任务失败（已忽略）: {exc}")

    def save_step(self, task_id: str, step: Any, position: int) -> None:
        if not self.task_repository:
            return
        try:
            self.task_repository.save_step(task_id=task_id, step=step, position=position)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[RuntimePersistence] 保存步骤失败（已忽略）: {exc}")

    def save_artifact(self, task_id: str, artifact: Any) -> None:
        if not self.task_repository:
            return
        try:
            self.task_repository.save_artifact(task_id=task_id, artifact=artifact)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[RuntimePersistence] 保存产物失败（已忽略）: {exc}")
