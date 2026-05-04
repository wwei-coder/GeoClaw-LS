from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
from tools.base import BaseTool

ToolFactory = Callable[[], BaseTool]

@dataclass
class CapabilityToolSpec:
    tool_name: str
    description: str = ""
    tool_instance: Optional[BaseTool] = None
    tool_factory: Optional[ToolFactory] = None
    enabled: bool = True

    def build_tool(self) -> Optional[BaseTool]:
        if not self.enabled:
            return None
        if self.tool_instance is not None:
            return self.tool_instance
        if self.tool_factory is not None:
            return self.tool_factory()
        return None

@dataclass
class CapabilityMetadata:
    name: str
    description: str = ""
    enabled: bool = True
    tools: Dict[str, CapabilityToolSpec] = field(default_factory=dict)

    def get_enabled_tools(self) -> Dict[str, BaseTool]:
        resolved: Dict[str, BaseTool] = {}
        if not self.enabled:
            return resolved
        for key, spec in (self.tools or {}).items():
            tool = spec.build_tool()
            if tool is None:
                continue
            resolved[str(key).upper()] = tool
        return resolved
