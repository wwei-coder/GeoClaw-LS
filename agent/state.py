from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

@dataclass
class Artifact:
    """步骤执行生成的结构化产物。"""

    id: str
    task_id: str = ""
    name: str = "artifact"
    type: str = "text"
    path: str = ""
    url: str = ""
    mime_type: str = ""
    size: int = 0
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_iso_now)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Artifact":
        data = dict(payload or {})
        art_type = str(data.get("type") or data.get("kind") or "text")
        return cls(
            id=str(data.get("id") or ""),
            task_id=str(data.get("task_id") or ""),
            name=str(data.get("name") or "artifact"),
            type=art_type,
            path=str(data.get("path") or ""),
            url=str(data.get("url") or ""),
            mime_type=str(data.get("mime_type") or ""),
            size=int(data.get("size") or 0),
            content=data.get("content"),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or _iso_now()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "name": self.name,
            "type": self.type,
            "kind": self.type,
            "path": self.path,
            "url": self.url,
            "download_url": self.url,
            "mime_type": self.mime_type,
            "size": self.size,
            "content": self.content,
            "metadata": dict(self.metadata or {}),
            "created_at": self.created_at,
        }

@dataclass
class AgentStep:
    """任务中的单个可执行步骤。"""

    id: str
    tool_name: str
    instruction: str
    status: str = "pending"
    retry_of: Optional[str] = None
    attempts: int = 1
    cancel_requested: bool = False
    input: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Artifact] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AgentStep":
        data = dict(payload or {})
        artifacts_raw = data.get("artifacts") or []
        artifacts = []
        for item in artifacts_raw:
            if isinstance(item, Artifact):
                artifacts.append(item)
            elif isinstance(item, dict):
                artifacts.append(Artifact.from_dict(item))
        return cls(
            id=str(data.get("id") or ""),
            tool_name=str(data.get("tool_name") or data.get("tool") or ""),
            instruction=str(data.get("instruction") or data.get("task") or ""),
            status=str(data.get("status") or "pending"),
            retry_of=data.get("retry_of"),
            attempts=int(data.get("attempts") or 1),
            cancel_requested=bool(data.get("cancel_requested") or False),
            input=dict(data.get("input") or {}),
            result=dict(data.get("result") or {}),
            error=data.get("error"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            metadata=dict(data.get("metadata") or {}),
            artifacts=artifacts,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "instruction": self.instruction,
            "status": self.status,
            "retry_of": self.retry_of,
            "attempts": int(self.attempts or 1),
            "cancel_requested": bool(self.cancel_requested),
            "input": dict(self.input or {}),
            "result": dict(self.result or {}),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": dict(self.metadata or {}),
            "artifacts": [a.to_dict() if isinstance(a, Artifact) else a for a in (self.artifacts or [])],
        }

    def to_legacy_step(self) -> Dict[str, str]:
        return {"tool": self.tool_name, "task": self.instruction}

@dataclass
class AgentTask:
    """单次请求级任务上下文。"""

    id: str
    user_query: str
    status: str = "pending"
    run_mode: str = "sync"
    cancel_requested: bool = False
    resumed_from: Optional[str] = None
    steps: List[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    artifacts: List[Artifact] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_iso_now)
    updated_at: str = field(default_factory=_iso_now)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AgentTask":
        data = dict(payload or {})
        steps_raw = data.get("steps") or []
        steps = []
        for item in steps_raw:
            if isinstance(item, AgentStep):
                steps.append(item)
            elif isinstance(item, dict):
                steps.append(AgentStep.from_dict(item))

        artifacts_raw = data.get("artifacts") or []
        artifacts = []
        for item in artifacts_raw:
            if isinstance(item, Artifact):
                artifacts.append(item)
            elif isinstance(item, dict):
                artifacts.append(Artifact.from_dict(item))

        return cls(
            id=str(data.get("id") or ""),
            user_query=str(data.get("user_query") or ""),
            status=str(data.get("status") or "pending"),
            run_mode=str(data.get("run_mode") or "sync"),
            cancel_requested=bool(data.get("cancel_requested") or False),
            resumed_from=data.get("resumed_from"),
            steps=steps,
            final_answer=str(data.get("final_answer") or ""),
            artifacts=artifacts,
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or _iso_now()),
            updated_at=str(data.get("updated_at") or _iso_now()),
        )

    def touch(self) -> None:
        self.updated_at = _iso_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_query": self.user_query,
            "status": self.status,
            "run_mode": self.run_mode,
            "cancel_requested": bool(self.cancel_requested),
            "resumed_from": self.resumed_from,
            "steps": [s.to_dict() if isinstance(s, AgentStep) else s for s in (self.steps or [])],
            "final_answer": self.final_answer,
            "artifacts": [a.to_dict() if isinstance(a, Artifact) else a for a in (self.artifacts or [])],
            "metadata": dict(self.metadata or {}),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass
class AgentState:
    """运行态结构，便于 Graph 与 API 间传递。"""

    task: AgentTask
    steps: List[AgentStep] = field(default_factory=list)
    current_step_index: int = 0
    final_answer: str = ""
    sources: List[str] = field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
