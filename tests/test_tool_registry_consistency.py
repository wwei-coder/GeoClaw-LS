from __future__ import annotations

from core.planner import get_planner_allowed_tools
from tools.base import BaseTool, ToolInput, ToolResult
from tools.registry import get_enabled_tool_names, get_tool_registry


class _FakeTool(BaseTool):
    name = "FAKE_CAP"
    description = "fake capability tool"

    def run(self, tool_input: ToolInput, agent):
        _ = (tool_input, agent)
        return ToolResult(success=True, content="ok", metadata={"tool": self.name})


def test_core_tools_compat_registry_delegates_to_unified_registry():
    import core.tools as core_tools

    registry = get_tool_registry()
    for tool_name in get_enabled_tool_names():
        assert core_tools.TOOL_REGISTRY.get(tool_name) is not None
        assert core_tools.LEGACY_TOOL_REGISTRY.get(tool_name) is not None
        assert registry.get(tool_name) is not None


def test_new_capability_tool_flows_through_unified_entry(monkeypatch):
    import tools.registry as tool_registry_module

    fake = _FakeTool()

    def _fake_capability_tools():
        return {"FAKE_CAP": fake}

    monkeypatch.setattr(tool_registry_module, "get_capability_tool_instances", _fake_capability_tools)

    enabled = set(tool_registry_module.get_enabled_tool_names())
    planner_allowed = get_planner_allowed_tools()
    runtime_registry = tool_registry_module.get_tool_registry()

    assert "FAKE_CAP" in enabled
    assert "FAKE_CAP" in planner_allowed
    assert "FAKE_CAP" in runtime_registry
