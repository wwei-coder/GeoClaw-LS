from __future__ import annotations

from typing import Any, Dict, Optional

from .entity_extractor import EntityExtractor
from .graph_retriever import GraphRetriever
from .graph_store import InMemoryGraphStore
from .hybrid_retriever import HybridRetriever
from .relation_extractor import RelationExtractor
from .schemas import GraphSearchRequest, GraphSearchResult, HybridRagRequest, HybridRagResult


class KGRagService:
    """KG-RAG capability service stub (in-memory, non-LLM)."""

    def __init__(
        self,
        *,
        graph_store: Optional[Any] = None,
        entity_extractor: Optional[EntityExtractor] = None,
        relation_extractor: Optional[RelationExtractor] = None,
        graph_retriever: Optional[GraphRetriever] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        vector_retriever: Optional[Any] = None,
    ):
        self.graph_store = graph_store or InMemoryGraphStore()
        self.entity_extractor = entity_extractor or EntityExtractor()
        self.relation_extractor = relation_extractor or RelationExtractor()
        self.graph_retriever = graph_retriever or GraphRetriever(self.graph_store)
        self.hybrid_retriever = hybrid_retriever or HybridRetriever(
            graph_retriever=self.graph_retriever,
            vector_retriever=vector_retriever,
        )
        self._ingested_sources = 0

    def ingest_text(self, text: str, source: Optional[str] = None) -> Dict[str, Any]:
        entities = self.entity_extractor.extract(text)
        relations = self.relation_extractor.extract(text, entities)
        for ent in entities:
            payload = ent
            if source:
                payload.metadata.setdefault("source", source)
            self.graph_store.add_entity(payload)
        for rel in relations:
            payload = rel
            if source:
                payload.metadata.setdefault("source", source)
            self.graph_store.add_relation(payload)
        if source:
            self._ingested_sources += 1
        return {
            "entities": len(entities),
            "relations": len(relations),
            "source": source or "",
        }

    def search_graph(self, query: str, top_k: int = 5) -> GraphSearchResult:
        return self.graph_retriever.retrieve(GraphSearchRequest(query=query, top_k=top_k))

    def hybrid_retrieve(self, query: str, top_k: int = 5) -> HybridRagResult:
        return self.hybrid_retriever.retrieve(HybridRagRequest(query=query, top_k=top_k))

    def get_status(self) -> Dict[str, Any]:
        stats = {}
        if hasattr(self.graph_store, "get_stats"):
            stats = self.graph_store.get_stats()
        return {
            "ready": True,
            "store": type(self.graph_store).__name__,
            "ingested_sources": self._ingested_sources,
            "stats": stats,
        }

