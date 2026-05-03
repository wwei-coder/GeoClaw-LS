from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class KnowledgeSyncSummary:
    mode: str
    reason: Optional[str] = None
    changes: Dict[str, int] = field(default_factory=dict)
    documents: int = 0
    chunks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "mode": self.mode,
            "changes": dict(self.changes or {}),
            "documents": int(self.documents or 0),
            "chunks": int(self.chunks or 0),
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass
class KnowledgeBaseStatus:
    data_dir: str
    collection_name: str
    collection_count: int
    collection_metadata: Dict[str, Any]
    embedding_model: str
    embedding_backend: str
    rerank_strategy: str
    rerank_model: str
    last_sync: Dict[str, Any]
    runtime: Dict[str, Any]
    fingerprint: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_dir": self.data_dir,
            "collection_name": self.collection_name,
            "collection_count": int(self.collection_count or 0),
            "collection_metadata": dict(self.collection_metadata or {}),
            "embedding_model": self.embedding_model,
            "embedding_backend": self.embedding_backend,
            "rerank_strategy": self.rerank_strategy,
            "rerank_model": self.rerank_model,
            "last_sync": dict(self.last_sync or {}),
            "runtime": dict(self.runtime or {}),
            "fingerprint": dict(self.fingerprint or {}),
        }


@dataclass
class RetrievalRequest:
    query: str
    top_k: int = 3
    filter: Optional[Dict[str, Any]] = None
    search_mode: str = "hybrid"


@dataclass
class RetrievalResult:
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": list(self.chunks or []),
            "sources": list(self.sources or []),
            "metadata": dict(self.metadata or {}),
        }

