from __future__ import annotations

from typing import Any, Dict, List, Protocol


class Reranker(Protocol):
    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ...
