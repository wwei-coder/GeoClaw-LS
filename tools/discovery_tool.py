from __future__ import annotations
from typing import Any
from config_runtime import LLM_TEMPERATURE_DISCOVERY, TOOL_DISCOVERY_TOP_K
from tools.base import BaseTool, ToolInput, ToolResult
from utils.ollama_client import ask_ollama

class DiscoveryTool(BaseTool):
    name = "DISCOVERY"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            chunks = agent.vector_store.search(tool_input.task, top_k=TOOL_DISCOVERY_TOP_K)
            if not chunks:
                content = "[深度分析] 资料库为空或未匹配到相关内容，无法进行推导。"
                return ToolResult(success=True, content=content, metadata={"tool": self.name})

            evidence = []
            for c in chunks:
                item = c if isinstance(c, dict) else {}
                doc = item.get("doc_name", "未知来源")
                txt = item.get("content", "").strip()
                evidence.append(f"《{doc}》:\n{txt}")
            from agent.brain.prompt_catalog import get_prompt_catalog

            prompt = get_prompt_catalog().render(
                "discovery",
                question=tool_input.task,
                kb_evidence="\n----\n".join(evidence),
            )
            content = ask_ollama(prompt, temperature=LLM_TEMPERATURE_DISCOVERY)
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
