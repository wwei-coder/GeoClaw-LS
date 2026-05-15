from __future__ import annotations
from typing import Any, Dict, List
from agent.state import AgentStep, AgentTask, Artifact

def task_from_state(state: Dict[str, Any]) -> AgentTask:
    task_payload = state.get("task") or {}
    steps: List[AgentStep] = []
    for item in task_payload.get("steps", []) or []:
        if isinstance(item, AgentStep):
            steps.append(item)
            continue
        steps.append(
            AgentStep(
                id=str(item.get("id", "")),
                tool_name=str(item.get("tool_name", "LLM")),
                instruction=str(item.get("instruction", "")),
                status=str(item.get("status", "pending")),
                retry_of=item.get("retry_of"),
                attempts=int(item.get("attempts") or 1),
                cancel_requested=bool(item.get("cancel_requested", False)),
                input=dict(item.get("input", {}) or {}),
                result=dict(item.get("result", {}) or {}),
                error=item.get("error"),
                started_at=item.get("started_at"),
                finished_at=item.get("finished_at"),
                metadata=dict(item.get("metadata", {}) or {}),
                artifacts=[
                    Artifact.from_dict(a)
                    for a in (item.get("artifacts", []) or [])
                ],
            )
        )
    task_artifacts = [Artifact.from_dict(a) for a in (task_payload.get("artifacts", []) or [])]
    return AgentTask(
        id=str(task_payload.get("id") or state.get("task_id") or ""),
        user_query=str(task_payload.get("user_query") or state.get("question") or ""),
        status=str(task_payload.get("status", "running")),
        run_mode=str(task_payload.get("run_mode") or state.get("run_mode") or "sync"),
        cancel_requested=bool(task_payload.get("cancel_requested", state.get("cancel_requested", False))),
        resumed_from=task_payload.get("resumed_from") or state.get("resumed_from") or None,
        steps=steps,
        final_answer=str(task_payload.get("final_answer", "")),
        artifacts=task_artifacts,
        metadata=dict(task_payload.get("metadata", {}) or {}),
        created_at=str(task_payload.get("created_at", "")),
        updated_at=str(task_payload.get("updated_at", "")),
    )


def sync_legacy_steps(task: AgentTask) -> List[Dict[str, Any]]:
    return [step.to_legacy_step() for step in (task.steps or [])]


def normalize_artifacts_with_task(task_id: str, artifacts: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in artifacts or []:
        if isinstance(item, Artifact):
            artifact = item
            artifact.task_id = task_id
        else:
            payload = dict(item or {})
            payload["task_id"] = task_id
            artifact = Artifact.from_dict(payload)
        normalized.append(artifact.to_dict())
    return normalized
