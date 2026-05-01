"""Agent-side registry facade (phase-1 keeps planner tool names unchanged)."""

from typing import Any, Dict, Optional

from tools.registry import build_tool_registry, get_tool_registry

__all__ = ["build_tool_registry", "get_tool_registry"]


def get_agent_registry(default_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return get_tool_registry(default_registry=default_registry)
