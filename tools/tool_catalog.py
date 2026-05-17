"""Shared planner-facing tool catalog helpers.

Keep planner-visible tool metadata out of ``agent.brain`` and keep execution
registry wrappers in ``tools.registry`` thin.
"""

from __future__ import annotations
from typing import Callable, Dict, List, Optional
from loguru import logger
from tools.base import BaseTool
from tools.data_profile_tool import DataProfileTool
from tools.discovery_tool import DiscoveryTool
from tools.file_inspector_tool import FileInspectorTool
from tools.llm_tool import LLMTool
from tools.memory_tool import MemoryTool

STANDARD_TOOL_INSTANCES: Dict[str, BaseTool] = {
    "MEMORY": MemoryTool(),
    "LLM": LLMTool(),
    "DISCOVERY": DiscoveryTool(),
    "DATA_PROFILE": DataProfileTool(),
    "FILE_INSPECTOR": FileInspectorTool(),
}

STANDARD_TOOL_DESCRIPTIONS: Dict[str, str] = {
    "RAG": "知识库检索",
    "MEMORY": "历史记忆",
    "LLM": "直接生成",
    "DISCOVERY": "深度洞察与新知推导",
    "FILE_INSPECTOR": "查看文件信息和内容预览",
    "DATA_PROFILE": "上传数据文件分析：CSV/Excel/JSON/TXT",
}

DEFAULT_PLANNER_TOOL_ORDER: List[str] = [
    "RAG",
    "MEMORY",
    "LLM",
    "DISCOVERY",
    "FILE_INSPECTOR",
    "DATA_PROFILE",
]

def _default_capability_loader() -> Dict[str, BaseTool]:
    from tools.registry import get_capability_tool_instances

    return get_capability_tool_instances()

def get_tool_instances(
    capability_loader: Optional[Callable[[], Dict[str, BaseTool]]] = None,
) -> Dict[str, BaseTool]:
    merged: Dict[str, BaseTool] = dict(STANDARD_TOOL_INSTANCES)
    try:
        capability_tools = (capability_loader or _default_capability_loader)()
        for name, tool in (capability_tools or {}).items():
            merged[str(name).upper()] = tool
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[ToolCatalog] capability 工具加载失败，回退标准工具: {exc}")
    return merged

def get_enabled_tool_names(
    capability_loader: Optional[Callable[[], Dict[str, BaseTool]]] = None,
) -> List[str]:
    instances = get_tool_instances(capability_loader=capability_loader)
    names = [str(name).upper() for name in instances.keys()]
    ordered: List[str] = [name for name in DEFAULT_PLANNER_TOOL_ORDER if name in names]
    extras = sorted([name for name in names if name not in set(ordered)])
    return ordered + extras

def get_planner_tool_specs(
    capability_loader: Optional[Callable[[], Dict[str, BaseTool]]] = None,
) -> List[Dict[str, str]]:
    instances = get_tool_instances(capability_loader=capability_loader)
    specs: List[Dict[str, str]] = []
    for name in get_enabled_tool_names(capability_loader=capability_loader):
        tool = instances.get(name)
        default_desc = STANDARD_TOOL_DESCRIPTIONS.get(name, "")
        spec_desc = str(getattr(tool, "description", "") or "").strip()
        specs.append({"tool": name, "description": spec_desc or default_desc})
    return specs

def render_planner_tool_descriptions(
    capability_loader: Optional[Callable[[], Dict[str, BaseTool]]] = None,
) -> str:
    lines = []
    for item in get_planner_tool_specs(capability_loader=capability_loader):
        tool = item["tool"]
        desc = item["description"]
        lines.append(f"- {tool}" + (f"（{desc}）" if desc else ""))
    return "\n".join(lines)
