from __future__ import annotations

from typing import Any, Dict, List, Optional

from storage.schemas import VectorIndexStatus


class VectorIndexAdapter:
    """Thin adapter over existing VectorStore implementation."""

    def __init__(self, vector_store: Any):
        self.vector_store = vector_store

    def count(self) -> int:
        collection = getattr(self.vector_store, "collection", None)
        if collection is None:
            return 0
        return int(collection.count())

    def get_status(self) -> Dict[str, Any]:
        collection = getattr(self.vector_store, "collection", None)
        collection_name = str(getattr(collection, "name", "") or "")
        runtime = {}
        if hasattr(self.vector_store, "get_runtime_stats"):
            runtime = self.vector_store.get_runtime_stats()
        return VectorIndexStatus(collection_name=collection_name, count=self.count(), runtime=runtime).__dict__

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        return self.vector_store.search(query, top_k=top_k, filter=filter, search_mode=search_mode)

    def build_full(self, chunks: List[Dict[str, Any]]) -> None:
        self.vector_store.build_full(chunks)

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        self.vector_store.add_chunks(chunks)

    def deactivate_by_docs(self, doc_names: List[str]) -> None:
        self.vector_store.deactivate_by_docs(doc_names)

    def load(self) -> Any:
        return self.vector_store.load()

