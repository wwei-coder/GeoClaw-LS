from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class StoredSession:
    session_id: int
    title: str
    created_at: str = ""
    updated_at: str = ""

@dataclass
class StoredTaskSummary:
    task_id: str
    session_id: Optional[str] = None
    status: str = "pending"
    run_mode: str = "sync"
    user_query: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StoredArtifact:
    artifact_id: str
    task_id: str = ""
    name: str = "artifact"
    type: str = "text"
    path: str = ""
    url: str = ""
    mime_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorIndexStatus:
    collection_name: str = ""
    count: int = 0
    runtime: Dict[str, Any] = field(default_factory=dict)

