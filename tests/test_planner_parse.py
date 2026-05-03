from core.planner import _process_planner_response, get_planner_allowed_tools
from tools.registry import get_enabled_tool_names


def test_planner_parse_markdown_json_block():
    raw = """```json
{"intent":"qa","need_kb":true,"steps":[{"tool":"RAG","task":"检索滑坡定义"}]}
```"""
    plan = _process_planner_response(raw, "滑坡定义是什么")
    assert isinstance(plan["steps"], list)
    assert plan["steps"][0]["tool"] == "RAG"


def test_planner_parse_fallback_on_invalid_json():
    plan = _process_planner_response("not a json", "你好")
    assert plan["steps"][0]["tool"] == "LLM"
    assert plan["steps"][0]["task"] == "你好"


def test_planner_unknown_tool_downgrade_to_llm():
    raw = '{"intent":"qa","need_kb":false,"steps":[{"tool":"UNKNOWN","task":"x"}]}'
    plan = _process_planner_response(raw, "普通问题")
    assert plan["steps"][0]["tool"] == "LLM"


def test_planner_data_tool_requires_file_signal():
    raw = '{"intent":"qa","need_kb":false,"steps":[{"tool":"DATA_PROFILE","task":"分析数据"}]}'
    no_file = _process_planner_response(raw, "请分析这个问题")
    with_file = _process_planner_response(raw, "请分析 file_id:file_123 的数据")
    assert no_file["steps"][0]["tool"] == "LLM"
    assert with_file["steps"][0]["tool"] == "DATA_PROFILE"


def test_planner_allowed_tools_match_runtime_registry():
    assert get_planner_allowed_tools() == set(get_enabled_tool_names())
    assert "KG_RAG" not in get_planner_allowed_tools()
