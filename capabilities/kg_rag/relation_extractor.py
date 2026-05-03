from __future__ import annotations
from typing import List
from .schemas import Entity, Relation

class RelationExtractor:
    """Simple sequential relation stub (no LLM calls)."""

    def extract(self, text: str, entities: List[Entity]) -> List[Relation]:
        _ = text
        rels: List[Relation] = []
        for idx in range(len(entities) - 1):
            src = entities[idx]
            tgt = entities[idx + 1]
            rels.append(
                Relation(
                    id=f"rel_{idx+1}_{src.id}_{tgt.id}",
                    source_id=src.id,
                    target_id=tgt.id,
                    relation_type="co_occurs",
                    evidence=f"{src.name} -> {tgt.name}",
                )
            )
        return rels
