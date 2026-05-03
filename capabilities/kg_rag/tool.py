from __future__ import annotations
from typing import Any
from tools.base import BaseTool, ToolInput, ToolResult
from .service import KGRagService

class KGRagTool(BaseTool):
    name = "KG_RAG"

    def __init__(self, service: Any = None):
        self.service = service or KGRagService()

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        _ = agent
        query = str(tool_input.task or "")
        result = self.service.hybrid_retrieve(query=query, top_k=5)
        context = result.answer_context.strip()
        if not context:
            context = "KG-RAG capability 已就绪，但当前未接入默认知识图谱数据。"
        return ToolResult(
            success=True,
            content=context,
            metadata={
                "tool": self.name,
                "mode": "kg_rag_stub",
                "graph_entities": len(result.graph_result.entities) if result.graph_result else 0,
                "graph_relations": len(result.graph_result.relations) if result.graph_result else 0,
                "vector_used": bool(result.metadata.get("vector_used")),
            },
        )
