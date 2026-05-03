from __future__ import annotations
import asyncio
from agent.executor import AgentExecutor
from agent.runtime import GraphRuntime, RuntimeArtifactEvent, RuntimeExecutionResult, RuntimePersistence, RuntimeStepEvent
from agent.state import AgentTask
from agent.task_runner import TaskRunner
from agent.task_store import TaskStore
from utils.logger import logger

class _FakeTaskStore:
    def __init__(self):
        self.calls = []

    def save_task(self, task, session_id=None):
        self.calls.append(("save_task", task, session_id))

    def save_step(self, task_id, step, position):
        self.calls.append(("save_step", task_id, step, position))

    def save_artifact(self, task_id, artifact):
        self.calls.append(("save_artifact", task_id, artifact))

class _FailingTaskStore:
    def save_task(self, task, session_id=None):
        _ = (task, session_id)
        raise RuntimeError("save_task error")

    def save_step(self, task_id, step, position):
        _ = (task_id, step, position)
        raise RuntimeError("save_step error")

    def save_artifact(self, task_id, artifact):
        _ = (task_id, artifact)
        raise RuntimeError("save_artifact error")

class _StubGraphAgent:
    async def run_async(self, **kwargs):
        return {"ok": True, "echo": kwargs}

def test_runtime_persistence_save_calls_task_store():
    store = _FakeTaskStore()
    persistence = RuntimePersistence(task_store=store, session_provider=lambda: 100)
    task = AgentTask(id="t1", user_query="q")
    persistence.save_task(task)
    persistence.save_step("t1", {"id": "s1"}, 0)
    persistence.save_artifact("t1", {"id": "a1"})

    assert len(store.calls) == 3
    assert store.calls[0][0] == "save_task"
    assert store.calls[0][2] == 100
    assert store.calls[1][0] == "save_step"
    assert store.calls[2][0] == "save_artifact"

def test_runtime_persistence_does_not_raise_when_store_fails():
    persistence = RuntimePersistence(task_store=_FailingTaskStore())
    task = AgentTask(id="t1", user_query="q")
    logger.disable("agent.runtime.persistence")
    try:
        persistence.save_task(task)
        persistence.save_step("t1", {"id": "s1"}, 0)
        persistence.save_artifact("t1", {"id": "a1"})
    finally:
        logger.enable("agent.runtime.persistence")

def test_runtime_schemas_instantiation():
    step_event = RuntimeStepEvent(task_id="t1", step_id="s1", tool_name="RAG", status="running")
    artifact_event = RuntimeArtifactEvent(
        task_id="t1", artifact_id="a1", artifact_name="report.md", artifact_type="markdown"
    )
    exec_result = RuntimeExecutionResult(task_id="t1", status="success", final_answer="ok")
    assert step_event.tool_name == "RAG"
    assert artifact_event.artifact_name == "report.md"
    assert exec_result.status == "success"

def test_graph_runtime_delegates_to_graph_agent():
    runtime = GraphRuntime(_StubGraphAgent())
    out = asyncio.run(
        runtime.run_async(
            "测试问题",
            file_id="f1",
            files=[{"id": "f1"}],
            task_id="task_x",
            run_mode="sync",
            resumed_from="task_old",
        )
    )
    assert out["ok"] is True
    assert out["echo"]["question"] == "测试问题"
    assert out["echo"]["task_id"] == "task_x"

def test_agent_runtime_imports_are_available():
    assert AgentExecutor is not None
    assert TaskRunner is not None
    assert TaskStore is not None
    assert AgentTask is not None


def test_agent_core_exposes_runtime_property(monkeypatch):
    import core.agent_core as agent_core_module

    class _FakeDBManager:
        def __init__(self, _path):
            pass

        def get_conversation_count(self):
            return 0

        def get_all_sessions(self):
            return [(1, "默认对话", "", "")]

        def create_session(self, _title):
            return 1

        def get_recent_conversations(self, _user_id, limit=4, session_id=None):
            _ = (limit, session_id)
            return []

    class _FakeTaskStore:
        def __init__(self, _db_manager):
            pass

    class _FakeTaskRunner:
        def __init__(self, _core, max_workers=1):
            _ = max_workers

    class _FakeCollection:
        def count(self):
            return 1

    class _FakeVectorStore:
        def __init__(self, model_name="", index_path=""):
            _ = (model_name, index_path)
            self.collection = _FakeCollection()

    class _FakeRagService:
        def __init__(self, **kwargs):
            _ = kwargs

    class _FakeFileWorkspace:
        def __init__(self, root_dir="workspace"):
            _ = root_dir

    class _FakeGraphAgent:
        def __init__(self, _core):
            pass

        async def run_async(self, **kwargs):
            return {"ok": True, "payload": kwargs}

    monkeypatch.setattr(agent_core_module, "DatabaseManager", _FakeDBManager)
    monkeypatch.setattr(agent_core_module, "TaskStore", _FakeTaskStore)
    monkeypatch.setattr(agent_core_module, "TaskRunner", _FakeTaskRunner)
    monkeypatch.setattr(agent_core_module, "VectorStore", _FakeVectorStore)
    monkeypatch.setattr(agent_core_module, "RagService", _FakeRagService)
    monkeypatch.setattr(agent_core_module, "FileWorkspace", _FakeFileWorkspace)
    monkeypatch.setattr(agent_core_module, "GraphAgent", _FakeGraphAgent)
    monkeypatch.setattr(agent_core_module.AgentCore, "_sync_knowledge_base", lambda self: {"mode": "no_change"})

    core = agent_core_module.AgentCore()
    assert hasattr(core, "runtime")
    assert core.runtime is not None
    out = asyncio.run(core.runtime.run_async("q"))
    assert out["ok"] is True
