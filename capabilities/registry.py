from __future__ import annotations
from typing import Dict, List
from loguru import logger
from capabilities.base import CapabilityMetadata
from capabilities.rag import get_capability as get_rag_capability
from tools.base import BaseTool

def get_default_capabilities() -> List[CapabilityMetadata]:
    """Return statically declared default capabilities.

    Keep this list explicit and deterministic to avoid side effects.
    """
    return [get_rag_capability()]

def get_enabled_capabilities() -> List[CapabilityMetadata]:
    return [cap for cap in get_default_capabilities() if bool(cap.enabled)]

def get_capability_tool_instances() -> Dict[str, BaseTool]:
    tool_map: Dict[str, BaseTool] = {}
    for capability in get_enabled_capabilities():
        try:
            tool_map.update(capability.get_enabled_tools())
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[CapabilityRegistry] 加载 capability 工具失败: {capability.name}: {exc}")
            continue
    return tool_map
