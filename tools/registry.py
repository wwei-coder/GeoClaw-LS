"""Standard tool registry and execution adapters."""

from __future__ import annotations
from typing import Any, Dict, Optional
from tools.base import BaseTool, ToolInput, ToolResult
from tools.calculator_tool import CalculatorTool
from tools.data_profile_tool import DataProfileTool
from tools.discovery_tool import DiscoveryTool
from tools.file_inspector_tool import FileInspectorTool
from tools.llm_tool import LLMTool
from tools.memory_tool import MemoryTool
from tools.rag_tool import RagTool


STANDARD_TOOL_INSTANCES: Dict[str, BaseTool] = {
    "RAG": RagTool(),
    "MEMORY": MemoryTool(),
    "LLM": LLMTool(),
    "CALCULATOR": CalculatorTool(),
    "DISCOVERY": DiscoveryTool(),
    "DATA_PROFILE": DataProfileTool(),
    "FILE_INSPECTOR": FileInspectorTool(),
}


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


def get_tool_instances() -> Dict[str, BaseTool]:
    return dict(STANDARD_TOOL_INSTANCES)


def build_tool_registry(default_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    registry = _normalize_registry(default_registry or {})
    for tool_name, tool in STANDARD_TOOL_INSTANCES.items():
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
