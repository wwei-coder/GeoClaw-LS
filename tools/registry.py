"""Standard tool execution registry and thin execution adapters."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from tools.base import BaseTool, ToolInput, ToolResult

def get_capability_tool_instances() -> Dict[str, BaseTool]:
    from capabilities.registry import get_capability_tool_instances as _get_capability_tool_instances

    return _get_capability_tool_instances()

def get_tool_instances() -> Dict[str, BaseTool]:
    from tools.tool_catalog import STANDARD_TOOL_INSTANCES

    merged: Dict[str, BaseTool] = dict(STANDARD_TOOL_INSTANCES)
    for name, tool in (get_capability_tool_instances() or {}).items():
        merged[str(name).upper()] = tool
    return merged

def get_enabled_tool_names() -> List[str]:
    from tools.tool_catalog import DEFAULT_PLANNER_TOOL_ORDER

    names = [str(name).upper() for name in get_tool_instances().keys()]
    ordered: List[str] = [name for name in DEFAULT_PLANNER_TOOL_ORDER if name in names]
    extras = sorted([name for name in names if name not in set(ordered)])
    return ordered + extras

def get_planner_tool_specs() -> List[Dict[str, str]]:
    from tools.tool_catalog import STANDARD_TOOL_DESCRIPTIONS

    instances = get_tool_instances()
    specs: List[Dict[str, str]] = []
    for name in get_enabled_tool_names():
        tool = instances.get(name)
        default_desc = STANDARD_TOOL_DESCRIPTIONS.get(name, "")
        spec_desc = str(getattr(tool, "description", "") or "").strip()
        specs.append({"tool": name, "description": spec_desc or default_desc})
    return specs

def render_planner_tool_descriptions() -> str:
    lines = []
    for item in get_planner_tool_specs():
        tool = item["tool"]
        desc = item["description"]
        lines.append(f"- {tool}" + (f"（{desc}）" if desc else ""))
    return "\n".join(lines)

def _normalize_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for name, fn in (registry or {}).items():
        normalized[str(name).upper()] = fn
    return normalized

def _adapt_tool(tool: BaseTool):
    def _runner(query: str, agent: Any) -> ToolResult:
        request = ToolInput(task=str(query or ""), tool=tool.name)
        return tool.run(request, agent)

    return _runner

def build_tool_registry(default_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    registry = _normalize_registry(default_registry or {})
    for tool_name, tool in get_tool_instances().items():
        registry[tool_name] = _adapt_tool(tool)
    return registry

def get_tool_registry(default_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return build_tool_registry(default_registry=default_registry)

def execute_tool(tool_name: str, query: str, agent: Any, registry: Optional[Dict[str, Any]] = None) -> ToolResult:
    tool_key = str(tool_name or "").upper().strip()
    active_registry = registry or get_tool_registry()
    tool_fn = active_registry.get(tool_key)
    if not tool_fn:
        return ToolResult(success=False, content="", metadata={"tool": tool_key}, error=f"未知工具：{tool_key}")
    try:
        raw = tool_fn(query, agent)
        if isinstance(raw, ToolResult):
            metadata = dict(raw.metadata or {})
            metadata.setdefault("tool", tool_key)
            raw.metadata = metadata
            return raw
        return ToolResult(success=True, content=str(raw), metadata={"tool": tool_key})
    except Exception as exc:  # pragma: no cover
        return ToolResult(success=False, content="", metadata={"tool": tool_key}, error=str(exc))
