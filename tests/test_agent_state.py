from agent.state import AgentStep, AgentTask, Artifact

def test_artifact_roundtrip():
    obj = Artifact(
        id="artifact_1",
        task_id="task_1",
        name="report.md",
        type="file",
        path="workspace/artifacts/report.md",
        url="/api/artifacts/artifact_1",
        mime_type="text/markdown",
        size=123,
        content=None,
        metadata={"k": "v"},
    )
    payload = obj.to_dict()
    rebuilt = Artifact.from_dict(payload)
    assert rebuilt.id == obj.id
    assert rebuilt.type == obj.type
    assert rebuilt.metadata["k"] == "v"

def test_agent_step_roundtrip():
    step = AgentStep(
        id="step_1",
        tool_name="RAG",
        instruction="检索滑坡定义",
        status="done",
        result={"content": "ok"},
        artifacts=[Artifact(id="a1", name="a", type="text")],
    )
    payload = step.to_dict()
    rebuilt = AgentStep.from_dict(payload)
    assert rebuilt.id == "step_1"
    assert rebuilt.tool_name == "RAG"
    assert rebuilt.result["content"] == "ok"
    assert rebuilt.artifacts[0].id == "a1"

def test_agent_task_roundtrip():
    task = AgentTask(
        id="task_1",
        user_query="滑坡如何监测",
        status="running",
        steps=[AgentStep(id="step_1", tool_name="MEMORY", instruction="读取记忆")],
        artifacts=[Artifact(id="a1", name="a", type="text")],
        metadata={"session_id": "s1"},
    )
    payload = task.to_dict()
    rebuilt = AgentTask.from_dict(payload)
    assert rebuilt.id == "task_1"
    assert rebuilt.user_query == "滑坡如何监测"
    assert rebuilt.steps[0].tool_name == "MEMORY"
    assert rebuilt.artifacts[0].id == "a1"
    assert rebuilt.metadata["session_id"] == "s1"
