from __future__ import annotations
from typing import Any
from tools.base import BaseTool, ToolInput, ToolResult
from utils.ollama_client import ask_ollama


class LLMTool(BaseTool):
    name = "LLM"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            content = ask_ollama(tool_input.task)
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
