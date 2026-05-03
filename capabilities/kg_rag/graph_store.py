from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from .schemas import Entity, Relation


class InMemoryGraphStore:
    """Pure in-memory graph store stub for KG-RAG capability."""

    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._relations: Dict[str, Relation] = {}

    def add_entity(self, entity: Entity) -> None:
        self._entities[entity.id] = entity

    def add_relation(self, relation: Relation) -> None:
        self._relations[relation.id] = relation

    def search_entities(self, query: str, top_k: int = 5) -> List[Entity]:
        q = (query or "").strip().lower()
        if not q:
            hits = list(self._entities.values())
        else:
            hits = [e for e in self._entities.values() if q in e.name.lower() or q in e.id.lower()]
        return hits[: max(0, int(top_k))]

    def search_relations(
        self,
        entity_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Relation]:
        rels = list(self._relations.values())
        if entity_id:
            rels = [r for r in rels if r.source_id == entity_id or r.target_id == entity_id]
        if relation_type:
            rels = [r for r in rels if r.relation_type == relation_type]
        return rels[: max(0, int(top_k))]

    def get_neighbors(self, entity_id: str, depth: int = 1) -> List[Entity]:
        if depth <= 0:
            return []
        neighbors: Dict[str, Entity] = {}
        frontier = {entity_id}
        for _ in range(depth):
            next_frontier = set()
            for rid in list(frontier):
                rels = self.search_relations(entity_id=rid, top_k=10_000)
                for rel in rels:
                    other = rel.target_id if rel.source_id == rid else rel.source_id
                    if other in self._entities and other not in neighbors and other != entity_id:
                        neighbors[other] = self._entities[other]
                        next_frontier.add(other)
            frontier = next_frontier
            if not frontier:
                break
        return [replace(e) for e in neighbors.values()]

    def get_stats(self) -> Dict[str, int]:
        return {"entity_count": len(self._entities), "relation_count": len(self._relations)}

