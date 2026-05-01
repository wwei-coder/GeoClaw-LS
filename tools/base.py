from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolInput:
    """Canonical input object for tool execution."""

    task: str
    tool: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Canonical output object for tool execution."""

    success: bool
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Any] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": bool(self.success),
            "content": self.content,
            "metadata": dict(self.metadata or {}),
            "artifacts": list(self.artifacts or []),
            "error": self.error,
        }

    def to_legacy_text(self) -> str:
        if self.success:
            return self.content
        if self.error:
            return f"[system_error] {self.error}"
        return "[system_error] tool execution failed"


class BaseTool(abc.ABC):
    """Base protocol for next-phase concrete tool classes."""

    name: str = "BASE"

    @abc.abstractmethod
    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        raise NotImplementedError

    async def arun(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        return self.run(tool_input, agent)
