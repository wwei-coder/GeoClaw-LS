"""Tool protocol and wrappers for phase-1 Agent refactor."""

from .base import ToolInput, ToolResult, BaseTool
from .registry import build_tool_registry, execute_tool, get_tool_instances, get_tool_registry

__all__ = [
    "ToolInput",
    "ToolResult",
    "BaseTool",
    "build_tool_registry",
    "get_tool_instances",
    "get_tool_registry",
    "execute_tool",
]
