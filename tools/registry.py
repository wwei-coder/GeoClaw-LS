"""Standard tool registry and execution adapters."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from loguru import logger
from capabilities.registry import get_capability_tool_instances
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

STANDARD_TOOL_DESCRIPTIONS: Dict[str, str] = {
    "RAG": "知识库检索",
    "MEMORY": "历史记忆",
    "LLM": "直接生成",
    "CALCULATOR": "数学计算",
    "DISCOVERY": "深度洞察与新知推导",
    "FILE_INSPECTOR": "查看文件信息和内容预览",
    "DATA_PROFILE": "上传数据文件分析：CSV/Excel/JSON/TXT",
}

DEFAULT_PLANNER_TOOL_ORDER: List[str] = [
    "RAG",
    "MEMORY",
    "LLM",
    "CALCULATOR",
    "DISCOVERY",
    "FILE_INSPECTOR",
    "DATA_PROFILE",
]

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
    merged: Dict[str, BaseTool] = dict(STANDARD_TOOL_INSTANCES)
    try:
        capability_tools = get_capability_tool_instances()
        for name, tool in (capability_tools or {}).items():
            merged[str(name).upper()] = tool
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[ToolRegistry] capability 工具加载失败，回退标准工具: {exc}")
    return merged

def get_enabled_tool_names() -> List[str]:
    instances = get_tool_instances()
    names = [str(name).upper() for name in instances.keys()]
    ordered: List[str] = [name for name in DEFAULT_PLANNER_TOOL_ORDER if name in names]
    extras = sorted([name for name in names if name not in set(ordered)])
    return ordered + extras

def get_planner_tool_specs() -> List[Dict[str, str]]:
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
