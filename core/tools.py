from typing import Any, Dict
from tools.base import ToolResult
from tools.registry import execute_tool, get_tool_registry
from utils.logger import logger

# Compatibility registry, now backed by standard tools in tools/registry.py.
TOOL_REGISTRY: Dict[str, Any] = get_tool_registry()
LEGACY_TOOL_REGISTRY: Dict[str, Any] = dict(TOOL_REGISTRY)

def execute_tool_with_protocol(tool_name: str, query: str, agent) -> ToolResult:
    tool_key = (tool_name or "").upper().strip()
    try:
        return execute_tool(tool_key, query, agent, registry=TOOL_REGISTRY)
    except Exception as exc:  # pragma: no cover
        logger.error(f"[ToolError] {tool_key} 执行失败: {exc}")
        return ToolResult(success=False, content="", metadata={"tool": tool_key}, error=str(exc))

def tool_rag(query: str, agent) -> str:
    return execute_tool_with_protocol("RAG", query, agent).to_legacy_text()

def tool_memory(query: str, agent) -> str:
    return execute_tool_with_protocol("MEMORY", query, agent).to_legacy_text()

def tool_llm(query: str, agent) -> str:
    return execute_tool_with_protocol("LLM", query, agent).to_legacy_text()

def tool_calculator(query: str, agent) -> str:
    return execute_tool_with_protocol("CALCULATOR", query, agent).to_legacy_text()

def tool_discovery(query: str, agent) -> str:
    return execute_tool_with_protocol("DISCOVERY", query, agent).to_legacy_text()

def tool_data_profile(query: str, agent) -> ToolResult:
    return execute_tool_with_protocol("DATA_PROFILE", query, agent)

def tool_file_inspector(query: str, agent) -> ToolResult:
    return execute_tool_with_protocol("FILE_INSPECTOR", query, agent)
