from __future__ import annotations
from typing import Any
from capabilities.memory.tools import build_memory_tool_content
from utils.logger import logger
from tools.base import BaseTool, ToolInput, ToolResult

class MemoryTool(BaseTool):
    name = "MEMORY"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            content = build_memory_tool_content(agent, recent_limit=6)
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
