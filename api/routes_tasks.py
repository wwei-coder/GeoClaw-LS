from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from api.context import (
    CreateTaskRequest,
    RetryTaskRequest,
    bridge,
    compute_progress,
    serialize_artifact,
    serialize_step,
    serialize_task,
)

router = APIRouter()


@router.get("/api/tasks")
def list_tasks(session_id: Optional[int] = None, limit: int = 50):
    safe_limit = max(1, min(int(limit or 50), 200))

    def _inner(agent: Any):
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

    return bridge.with_agent(_inner)


@router.get("/api/tasks/{task_id}")
def get_task_detail(task_id: str):
    def _inner(agent: Any):
        store = getattr(agent, "task_store", None)
        if not store:
            raise HTTPException(status_code=404, detail="任务存储未启用")
        data = store.get_task(task_id)
        if not data:
            raise HTTPException(status_code=404, detail="未找到指定任务")
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

    return bridge.with_agent(_inner)


@router.post("/api/tasks")
def create_background_task(req: CreateTaskRequest):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="任务内容不能为空")
    if (req.run_mode or "background").lower() != "background":
        raise HTTPException(status_code=400, detail="当前仅支持 run_mode=background")

    def _inner(agent: Any):
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise HTTPException(status_code=500, detail="后台任务运行器未初始化")
        if req.session_id:
            try:
                agent.switch_session(req.session_id)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"切换会话失败：{exc}") from exc
        return runner.submit_task(
            message=message,
            session_id=req.session_id if req.session_id is not None else agent.get_active_session_id(),
            file_id=(req.file_id or "").strip() or None,
        )

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建后台任务失败：{exc}") from exc


@router.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    tid = (task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="任务ID不能为空")

    def _inner(agent: Any):
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise HTTPException(status_code=500, detail="后台任务运行器未初始化")
        return runner.cancel_task(tid)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"取消任务失败：{exc}") from exc


@router.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str, req: RetryTaskRequest):
    tid = (task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="任务ID不能为空")

    def _inner(agent: Any):
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise HTTPException(status_code=500, detail="后台任务运行器未初始化")
        return runner.retry_task(tid, step_id=(req.step_id or "").strip() or None)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重试任务失败：{exc}") from exc


@router.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str):
    tid = (task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="任务ID不能为空")

    def _inner(agent: Any):
        runner = getattr(agent, "task_runner", None)
        if runner is None:
            raise HTTPException(status_code=500, detail="后台任务运行器未初始化")
        return runner.resume_task(tid)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"继续任务失败：{exc}") from exc


@router.get("/api/tasks/{task_id}/artifacts")
def get_task_artifacts(task_id: str, limit: int = 50):
    safe_limit = max(1, min(int(limit or 50), 200))

    def _inner(agent: Any):
        store = getattr(agent, "task_store", None)
        if not store:
            return {"artifacts": []}
        artifacts = store.list_artifacts(task_id=task_id, limit=safe_limit)
        return {"artifacts": [serialize_artifact(a) for a in artifacts]}

    return bridge.with_agent(_inner)
