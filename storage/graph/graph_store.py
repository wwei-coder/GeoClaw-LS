from __future__ import annotations
import abc
from typing import Any, Dict, List, Optional

class GraphStore(abc.ABC):
    """Future storage.graph protocol for KG-RAG graph persistence adapters."""

    @abc.abstractmethod
    def add_entity(self, entity: Any) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def add_relation(self, relation: Any) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def search_entities(self, query: str, top_k: int = 5) -> List[Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def search_relations(
        self,
        entity_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_neighbors(self, entity_id: str, depth: int = 1) -> List[Any]:
        raise NotImplementedError

    def get_status(self) -> Dict[str, Any]:
        return {"ready": True, "backend": type(self).__name__}
