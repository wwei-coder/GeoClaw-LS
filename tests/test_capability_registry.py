from __future__ import annotations

import capabilities.automl as automl_cap
import capabilities.kg_rag as kg_rag_cap
from capabilities.registry import (
    get_capability_tool_instances,
    get_default_capabilities,
    get_enabled_capabilities,
)
from tools.rag_tool import RagTool
from tools.registry import (
    get_enabled_tool_names,
    get_planner_tool_specs,
    get_tool_instances,
    get_tool_registry,
    render_planner_tool_descriptions,
)


def test_capabilities_registry_import_and_default_rag():
    defaults = get_default_capabilities()
    names = [c.name for c in defaults]
    assert "rag" in names

    enabled = get_enabled_capabilities()
    enabled_names = [c.name for c in enabled]
    assert "rag" in enabled_names


def test_capability_registry_exposes_rag_tool():
    tools = get_capability_tool_instances()
    assert "RAG" in tools
    assert getattr(tools["RAG"], "name", "").upper() == "RAG"


def test_standard_tools_still_available_in_tools_registry():
    instances = get_tool_instances()
    required = {
        "RAG",
        "MEMORY",
        "LLM",
        "CALCULATOR",
        "DISCOVERY",
        "DATA_PROFILE",
        "FILE_INSPECTOR",
    }
    assert required.issubset(set(instances.keys()))

    registry = get_tool_registry()
    for name in required:
        assert name in registry
        assert callable(registry[name])


def test_default_enabled_tool_names_match_expected():
    expected = {
        "RAG",
        "MEMORY",
        "LLM",
        "CALCULATOR",
        "DISCOVERY",
        "FILE_INSPECTOR",
        "DATA_PROFILE",
    }
    assert set(get_enabled_tool_names()) == expected
    assert "KG_RAG" not in get_enabled_tool_names()


def test_planner_tool_specs_and_render_exclude_kg_rag_by_default():
    specs = get_planner_tool_specs()
    names = {item["tool"] for item in specs}
    assert "KG_RAG" not in names
    rendered = render_planner_tool_descriptions()
    assert "KG_RAG" not in rendered
    assert "RAG" in rendered


def test_registry_rag_tool_import_is_available():
    assert RagTool is not None


def test_placeholders_importable_but_not_registered_as_tools():
    assert kg_rag_cap is not None
    assert automl_cap is not None
    tool_names = set(get_capability_tool_instances().keys())
    assert "KG_RAG" not in tool_names
    assert "AUTOML" not in tool_names
