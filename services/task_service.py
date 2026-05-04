from __future__ import annotations
from typing import Any, Dict, Optional
from agent.runtime import AgentRequestContext
from api.context import compute_progress, serialize_artifact, serialize_step, serialize_task

class TaskService:
    def list_tasks(self, agent: Any, *, session_id: Optional[int], limit: int) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 200))
        store = getattr(agent, "task_store", None)
        if not store:
            return {"tasks": []}
        tasks = store.list_tasks(session_id=session_id, limit=safe_limit)
        runner = getattr(agent, "task_runner", None)
        running_map = runner.list_running_status() if runner else {}
        rows = []
        for task in tasks:
            payload = serialize_task(task)
            detail = store.get_task(task.id)
            steps = [serialize_step(s) for s in ((detail or {}).get("steps") or [])]
            runtime = running_map.get(task.id, {})
            payload["is_running"] = bool(runtime.get("is_running", False))
            payload["cancel_requested"] = bool(payload.get("cancel_requested") or runtime.get("cancel_requested", False))
            payload["progress"] = compute_progress(payload, steps)
            rows.append(payload)
        return {"tasks": rows}

    def get_task_detail(self, agent: Any, *, task_id: str) -> Dict[str, Any]:
        store = getattr(agent, "task_store", None)
        if not store:
            raise RuntimeError("任务存储未启用")
        data = store.get_task(task_id)
        if not data:
            raise ValueError("未找到指定任务")
        task = serialize_task(data.get("task"))
        steps = [serialize_step(s) for s in (data.get("steps") or [])]
        artifacts = [serialize_artifact(a) for a in (data.get("artifacts") or [])]
        runner = getattr(agent, "task_runner", None)
        runtime = runner.list_running_status().get(task_id, {}) if runner else {}
        is_running = bool(runtime.get("is_running", False))
        cancel_requested = bool(task.get("cancel_requested") or runtime.get("cancel_requested", False))
        return {
            "task": task,
            "steps": steps,
            "artifacts": artifacts,
            "is_running": is_running,
            "cancel_requested": cancel_requested,
            "progress": compute_progress(task, steps),
        }

    def create_background_task(
        self,
        agent: Any,
        *,
        message: str,
        session_id: Optional[int],
        file_id: Optional[str],
        run_mode: str,
    ) -> Dict[str, Any]:
        if (run_mode or "background").lower() != "background":
            raise ValueError("当前仅支持 run_mode=background")
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise RuntimeError("后台任务运行器未初始化")
        req_ctx = AgentRequestContext(
            session_id=session_id if session_id is not None else agent.get_active_session_id(),
            file_id=(file_id or "").strip() or None,
            files=[],
            run_mode="background",
            metadata={"entrypoint": "api.tasks.create"},
        )
        return runner.submit_task(
            message=message,
            session_id=req_ctx.session_id,
            file_id=req_ctx.file_id,
            request_context=req_ctx,
        )

    def cancel_task(self, agent: Any, *, task_id: str) -> Dict[str, Any]:
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise RuntimeError("后台任务运行器未初始化")
        return runner.cancel_task(task_id)

    def retry_task(self, agent: Any, *, task_id: str, step_id: Optional[str]) -> Dict[str, Any]:
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise RuntimeError("后台任务运行器未初始化")
        return runner.retry_task(task_id, step_id=(step_id or "").strip() or None)

    def resume_task(self, agent: Any, *, task_id: str) -> Dict[str, Any]:
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise RuntimeError("后台任务运行器未初始化")
        return runner.resume_task(task_id)

    def list_task_artifacts(self, agent: Any, *, task_id: str, limit: int) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 200))
        store = getattr(agent, "task_store", None)
        if not store:
            return {"artifacts": []}
        artifacts = store.list_artifacts(task_id=task_id, limit=safe_limit)
        return {"artifacts": [serialize_artifact(a) for a in artifacts]}
