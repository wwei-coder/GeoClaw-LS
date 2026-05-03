from __future__ import annotations
from typing import Any, List
from .schemas import GraphSearchRequest, GraphSearchResult

class GraphRetriever:
    def __init__(self, graph_store: Any):
        self.graph_store = graph_store

    def retrieve(self, request: GraphSearchRequest) -> GraphSearchResult:
        top_k = max(1, int(request.top_k or 5))
        entities = self.graph_store.search_entities(request.query, top_k=top_k)
        entity_ids: List[str] = [e.id for e in entities]
        relations = []
        for eid in entity_ids:
            relations.extend(self.graph_store.search_relations(entity_id=eid, top_k=top_k))
        seen = set()
        dedup = []
        for rel in relations:
            if rel.id in seen:
                continue
            seen.add(rel.id)
            dedup.append(rel)
        evidence = [r.evidence for r in dedup if r.evidence]
        return GraphSearchResult(
            entities=entities,
            relations=dedup[:top_k],
            evidence=evidence[:top_k],
            metadata={"mode": "graph_only", "query": request.query},
        )
