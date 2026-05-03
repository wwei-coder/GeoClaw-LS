"""Tool protocol and wrappers for phase-1 Agent refactor."""

from .base import ToolInput, ToolResult, BaseTool

def build_tool_registry(*args, **kwargs):
    from .registry import build_tool_registry as _impl

    return _impl(*args, **kwargs)

def get_tool_instances(*args, **kwargs):
    from .registry import get_tool_instances as _impl

    return _impl(*args, **kwargs)

def get_tool_registry(*args, **kwargs):
    from .registry import get_tool_registry as _impl

    return _impl(*args, **kwargs)

def execute_tool(*args, **kwargs):
    from .registry import execute_tool as _impl

    return _impl(*args, **kwargs)

__all__ = [
    "ToolInput",
    "ToolResult",
    "BaseTool",
    "build_tool_registry",
    "get_tool_instances",
    "get_tool_registry",
    "execute_tool",
]
