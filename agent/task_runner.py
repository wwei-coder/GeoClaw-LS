from __future__ import annotations

import asyncio
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional

from utils.logger import logger
from .state import AgentTask
from .task_store import TaskStore


def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class TaskRunner:
    """轻量后台任务运行器（本地串行）。"""

    def __init__(self, agent_core: Any, max_workers: int = 1):
        self.agent_core = agent_core
        self.task_store: TaskStore = agent_core.task_store
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers or 1)), thread_name_prefix="agent-task")
        self.running_tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.task_store.mark_interrupted_running_tasks(interrupted_status="partial")

    def _new_task_id(self) -> str:
        return f"task_{uuid.uuid4().hex}"

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            item = self.running_tasks.get(str(task_id))
            if not item:
                return False
            fut = item.get("future")
            return bool(fut and not fut.done())

    def list_running_status(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for task_id, item in self.running_tasks.items():
                fut = item.get("future")
                out[task_id] = {
                    "is_running": bool(fut and not fut.done()),
                    "cancel_requested": bool(item.get("cancel_event") and item["cancel_event"].is_set()),
                    "started_at": item.get("started_at", ""),
                }
            return out

    def _run_task(
        self,
        task_id: str,
        message: str,
        session_id: Optional[int],
        file_id: Optional[str],
        resumed_from: Optional[str],
    ) -> Dict[str, Any]:
        try:
            self.task_store.set_task_cancel_requested(task_id, False)
            if session_id:
                self.agent_core.switch_session(int(session_id))
            result = asyncio.run(
                self.agent_core.chat_async(
                    message,
                    cancel_event=self.running_tasks[task_id]["cancel_event"],
                    file_id=file_id,
                    task_id=task_id,
                    run_mode="background",
                    resumed_from=resumed_from,
                )
            )
            final_task_id = str(result.get("task_id") or task_id)
            final_answer = str(result.get("answer") or "")
            record = self.task_store.get_task_record(final_task_id)
            if not record:
                self.task_store.update_task_status(task_id, "success", final_answer=final_answer)
            elif str(record.get("status") or "").lower() in {"running", "pending"}:
                self.task_store.update_task_status(final_task_id, "success", final_answer=final_answer)
            return result
        except Exception as exc:  # pragma: no cover
            logger.exception(f"[TaskRunner] 后台任务执行异常 task_id={task_id}: {exc}")
            self.task_store.update_task_status(task_id, "failed", final_answer=f"后台任务执行失败：{exc}")
            return {"answer": f"后台任务执行失败：{exc}", "task_id": task_id}
        finally:
            with self._lock:
                self.running_tasks.pop(task_id, None)

    def submit_task(
        self,
        message: str,
        session_id: Optional[int] = None,
        file_id: Optional[str] = None,
        resumed_from: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            raise ValueError("任务内容不能为空")
        target_task_id = str(task_id or self._new_task_id())
        with self._lock:
            if target_task_id in self.running_tasks:
                raise ValueError("该任务正在运行中，请勿重复提交")
            pre_task = AgentTask(
                id=target_task_id,
                user_query=text,
                status="pending",
                run_mode="background",
                cancel_requested=False,
                resumed_from=resumed_from,
                metadata={"file_id": file_id or "", "submitted_at": _iso_now()},
            )
            self.task_store.save_task(pre_task, session_id=session_id)
            cancel_event = threading.Event()
            fut = self.executor.submit(self._run_task, target_task_id, text, session_id, file_id, resumed_from)
            self.running_tasks[target_task_id] = {
                "future": fut,
                "cancel_event": cancel_event,
                "started_at": _iso_now(),
            }
            self.task_store.update_task_status(target_task_id, "running")
            return {"task_id": target_task_id, "status": "running"}

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        tid = str(task_id or "").strip()
        if not tid:
            raise ValueError("任务ID不能为空")
        with self._lock:
            item = self.running_tasks.get(tid)
            if not item:
                record = self.task_store.get_task_record(tid)
                if not record:
                    raise ValueError("任务不存在")
                if record.get("status") in {"success", "failed", "partial", "canceled"}:
                    return {"task_id": tid, "status": record.get("status"), "message": "任务已结束，无需取消"}
                self.task_store.set_task_cancel_requested(tid, True)
                return {"task_id": tid, "status": record.get("status"), "message": "已记录取消请求"}
            item["cancel_event"].set()
            self.task_store.set_task_cancel_requested(tid, True)
            return {"task_id": tid, "status": "running", "message": "已发送取消请求，等待当前步骤安全退出"}

    def retry_task(self, task_id: str, step_id: Optional[str] = None) -> Dict[str, Any]:
        record = self.task_store.get_task_record(task_id)
        if not record:
            raise ValueError("任务不存在")
        if record.get("status") == "success" and not step_id:
            raise ValueError("任务已成功完成，无需重试")
        metadata = dict(record.get("metadata") or {})
        if step_id:
            metadata["retry_step_id"] = str(step_id)
        message = record.get("user_query", "")
        session_id = record.get("session_id")
        file_id = metadata.get("file_id")
        return self.submit_task(
            message=message,
            session_id=int(session_id) if str(session_id or "").isdigit() else None,
            file_id=file_id if isinstance(file_id, str) else None,
            resumed_from=str(task_id),
        )

    def resume_task(self, task_id: str) -> Dict[str, Any]:
        record = self.task_store.get_task_record(task_id)
        if not record:
            raise ValueError("任务不存在")
        if record.get("status") == "success":
            raise ValueError("任务已成功完成，无需继续")
        metadata = dict(record.get("metadata") or {})
        message = record.get("user_query", "")
        if not message:
            raise ValueError("缺少任务问题内容，无法继续执行")
        session_id = record.get("session_id")
        file_id = metadata.get("file_id")
        return self.submit_task(
            message=message,
            session_id=int(session_id) if str(session_id or "").isdigit() else None,
            file_id=file_id if isinstance(file_id, str) else None,
            resumed_from=str(task_id),
        )

    def shutdown(self) -> None:
        with self._lock:
            for item in self.running_tasks.values():
                evt = item.get("cancel_event")
                if evt is not None:
                    evt.set()
        self.executor.shutdown(wait=False, cancel_futures=False)
