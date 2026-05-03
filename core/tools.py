from typing import Any, Dict
from tools.base import ToolResult
from tools.registry import execute_tool, get_tool_registry
from utils.logger import logger

class _RegistryProxy(dict):
    """Compatibility proxy that always reads from the unified tool registry."""

    def get(self, key: str, default: Any = None):
        return get_tool_registry().get(str(key or "").upper(), default)

    def __contains__(self, key: object) -> bool:  # pragma: no cover - compatibility hook
        if not isinstance(key, str):
            return False
        return self.get(key) is not None

    def keys(self):  # pragma: no cover - compatibility hook
        return get_tool_registry().keys()

# Compatibility registry, delegated to tools/registry unified source.
TOOL_REGISTRY: Dict[str, Any] = _RegistryProxy()
LEGACY_TOOL_REGISTRY: Dict[str, Any] = TOOL_REGISTRY

def execute_tool_with_protocol(tool_name: str, query: str, agent) -> ToolResult:
    tool_key = (tool_name or "").upper().strip()
    try:
        return execute_tool(tool_key, query, agent, registry=get_tool_registry())
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
