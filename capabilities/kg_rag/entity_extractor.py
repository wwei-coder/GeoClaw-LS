from __future__ import annotations
import re
from typing import List
from .schemas import Entity

class EntityExtractor:
    """Rule-based lightweight extractor stub (no LLM calls)."""

    WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}")

    def extract(self, text: str) -> List[Entity]:
        words = []
        seen = set()
        for token in self.WORD_RE.findall(text or ""):
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(token)
            if len(words) >= 8:
                break
        entities: List[Entity] = []
        for idx, word in enumerate(words, start=1):
            entities.append(Entity(id=f"ent_{idx}_{word}", name=word, type="keyword"))
        return entities

