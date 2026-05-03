from __future__ import annotations
from typing import Any, Dict, List, Optional
from .schemas import GraphSearchRequest, HybridRagRequest, HybridRagResult

class HybridRetriever:
    def __init__(self, graph_retriever: Any, vector_retriever: Optional[Any] = None):
        self.graph_retriever = graph_retriever
        self.vector_retriever = vector_retriever

    def retrieve(self, request: HybridRagRequest) -> HybridRagResult:
        graph_result = None
        vector_result: List[Dict[str, Any]] = []
        if bool(request.use_graph):
            graph_result = self.graph_retriever.retrieve(
                GraphSearchRequest(query=request.query, top_k=request.top_k)
            )
        if bool(request.use_vector) and self.vector_retriever is not None:
            search = getattr(self.vector_retriever, "search", None)
            if callable(search):
                vector_result = search(request.query, top_k=request.top_k)
        context_parts: List[str] = []
        if graph_result:
            context_parts.extend([e.name for e in graph_result.entities[: request.top_k]])
            context_parts.extend(graph_result.evidence[: request.top_k])
        if vector_result:
            context_parts.append(f"vector_hits={len(vector_result)}")
        return HybridRagResult(
            answer_context="\n".join([p for p in context_parts if p]).strip(),
            graph_result=graph_result,
            vector_result=vector_result,
            metadata={
                "mode": "hybrid",
                "graph_used": bool(request.use_graph),
                "vector_used": bool(request.use_vector and self.vector_retriever is not None),
            },
        )
