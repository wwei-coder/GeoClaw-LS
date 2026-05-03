from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class Entity:
    id: str
    name: str
    type: str = "concept"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Relation:
    id: str
    source_id: str
    target_id: str
    relation_type: str = "related_to"
    evidence: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphSearchRequest:
    query: str
    top_k: int = 5
    filters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphSearchResult:
    entities: List[Entity] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HybridRagRequest:
    query: str
    top_k: int = 5
    use_vector: bool = True
    use_graph: bool = True

@dataclass
class HybridRagResult:
    answer_context: str = ""
    graph_result: Optional[GraphSearchResult] = None
    vector_result: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
