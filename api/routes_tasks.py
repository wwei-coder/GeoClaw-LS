from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from api.context import (
    CreateTaskRequest,
    ResetPendingError,
    RetryTaskRequest,
    bridge,
)
from services.task_service import TaskService

router = APIRouter()
service = TaskService()

@router.get("/api/tasks")
def list_tasks(session_id: Optional[int] = None, limit: int = 50):
    def _inner(agent: Any):
        return service.list_tasks(agent, session_id=session_id, limit=limit)

    return bridge.with_agent_readonly(_inner)

@router.get("/api/tasks/{task_id}")
def get_task_detail(task_id: str):
    def _inner(agent: Any):
        return service.get_task_detail(agent, task_id=task_id)

    try:
        return bridge.with_agent_readonly(_inner)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResetPendingError:
        raise


@router.post("/api/tasks")
def create_background_task(req: CreateTaskRequest):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="任务内容不能为空")
    if (req.run_mode or "background").lower() != "background":
        raise HTTPException(status_code=400, detail="当前仅支持 run_mode=background")

    def _inner(agent: Any):
        return service.create_background_task(
            agent,
            message=message,
            session_id=req.session_id,
            file_id=req.file_id,
            run_mode=req.run_mode,
        )

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ResetPendingError:
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
        return service.cancel_task(agent, task_id=tid)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ResetPendingError:
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
        return service.retry_task(agent, task_id=tid, step_id=req.step_id)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ResetPendingError:
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
        return service.resume_task(agent, task_id=tid)

    try:
        return bridge.with_agent(_inner)
    except HTTPException:
        raise
    except ResetPendingError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"继续任务失败：{exc}") from exc

@router.get("/api/tasks/{task_id}/artifacts")
def get_task_artifacts(task_id: str, limit: int = 50):
    def _inner(agent: Any):
        return service.list_task_artifacts(agent, task_id=task_id, limit=limit)

    return bridge.with_agent_readonly(_inner)
