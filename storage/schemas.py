from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class StoredSession:
    session_id: int
    title: str = ""
    created_at: str = ""
    updated_at: str = ""

@dataclass
class StoredTaskSummary:
    task_id: str
    status: str = ""
    run_mode: str = ""
    session_id: int = 0
    updated_at: str = ""

@dataclass
class StoredArtifact:
    artifact_id: str
    task_id: str = ""
    name: str = ""
    kind: str = ""
    uri: str = ""
    created_at: str = ""

@dataclass
class VectorIndexStatus:
    collection_name: str = ""
    count: int = 0
    runtime: Dict[str, Any] = field(default_factory=dict)