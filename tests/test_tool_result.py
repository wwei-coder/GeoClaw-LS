from tools.base import ToolResult


def test_tool_result_to_dict():
    result = ToolResult(
        success=True,
        content="ok",
        metadata={"tool": "RAG"},
        artifacts=[{"id": "a1"}],
        error=None,
    )
    data = result.to_dict()
    assert set(data.keys()) == {"success", "content", "metadata", "artifacts", "error"}
    assert data["success"] is True
    assert data["metadata"]["tool"] == "RAG"
    assert data["artifacts"][0]["id"] == "a1"
