from __future__ import annotations
from typing import Any
from utils.logger import logger
from tools.base import BaseTool, ToolInput, ToolResult

class MemoryTool(BaseTool):
    name = "MEMORY"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            summary = getattr(agent, "summary_memory", "") or ""
            try:
                sid = agent.get_active_session_id() if hasattr(agent, "get_active_session_id") else getattr(agent, "session_id", None)
                recent = agent.load_history_to_ui(limit=6, session_id=sid)
            except Exception as exc:
                logger.warning(f"[Tools] 读取最近对话失败: {exc}")
                recent = ""
            short = "\n".join(getattr(agent, "short_memory", []) or [])

            parts = []
            if summary.strip():
                parts.append("【摘要记忆】\n" + summary.strip())
            if recent.strip():
                parts.append("【最近对话】\n" + recent.strip())
            if short.strip():
                parts.append("【短期记忆】\n" + short.strip())
            content = "\n\n".join(parts)
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
