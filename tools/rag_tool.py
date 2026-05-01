from __future__ import annotations
from typing import Any
from core.config import RAG_MAX_CHUNK_LENGTH, TOOL_RAG_TOP_K
from tools.base import BaseTool, ToolInput, ToolResult

class RagTool(BaseTool):
    name = "RAG"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            chunks = agent.vector_store.search(tool_input.task, top_k=TOOL_RAG_TOP_K)
            if not chunks:
                content = "[RAG] 未检索到相关资料"
                return ToolResult(success=True, content=content, metadata={"tool": self.name})
            lines = []
            for c in chunks:
                item = c if isinstance(c, dict) else {}
                text = item.get("content", "")
                if len(text) > RAG_MAX_CHUNK_LENGTH:
                    text = text[:RAG_MAX_CHUNK_LENGTH] + "…"
                cid = item.get("id", "")
                doc = item.get("doc_name", "")
                head = f"【{doc}｜{cid}】" if cid else f"【{doc}】"
                lines.append(head + "\n" + text)
            content = "\n\n".join(lines)
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
