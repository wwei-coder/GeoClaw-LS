from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentRequestContext:
    session_id: Optional[int] = None
    file_id: Optional[str] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    run_mode: str = "sync"
    task_id: Optional[str] = None
    cancel_event: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeStepEvent:
    task_id: str
    step_id: str
    tool_name: str
    status: str
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeArtifactEvent:
    task_id: str
    artifact_id: str
    artifact_name: str
    artifact_type: str
    path: str = ""
    url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeExecutionResult:
    task_id: str
    status: str
    final_answer: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
