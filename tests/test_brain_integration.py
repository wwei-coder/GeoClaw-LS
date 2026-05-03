from __future__ import annotations
import asyncio
from agent.brain.schemas import BrainDecision, BrainPlan
from core.graph_agent import GraphAgent

class _FakeCore:
    def __init__(self):
        self.task_store = None
        self._current_stream_callback = None
        self._active_cancel_event = None
        self.brain = _FakeBrain()

    def get_active_session_id(self):
        return 1

class _FakeBrain:
    async def plan(self, question: str):
        return BrainPlan(
            steps=[{"tool": "LLM", "task": question}],
            raw_plan={"steps": [{"tool": "LLM", "task": question}]},
            source="test",
            trace="Planner: test",
        )

    async def decide(self, question: str, plan: dict):
        _ = (question, plan)
        return BrainDecision(force_tool=None, need_kb=False, context_score=0.33, reason="Decision: test")

def test_graph_agent_planner_node_can_delegate_to_brain():
    core = _FakeCore()
    graph = GraphAgent(core)
    state = {
        "question": "测试问题",
        "feedback": "",
        "review_count": 0,
        "task_id": "",
        "run_mode": "sync",
        "resumed_from": "",
    }
    out = asyncio.run(graph._node_planner_async(state))
    assert out["plan"]["steps"][0]["tool"] == "LLM"
    assert "Planner: test" in out["trace"][0]


def test_graph_agent_decision_node_can_delegate_to_brain():
    core = _FakeCore()
    graph = GraphAgent(core)
    state = {
        "question": "测试问题",
        "plan": {"steps": [{"tool": "LLM", "task": "测试问题"}]},
        "steps": [{"tool": "LLM", "task": "测试问题"}],
        "task": {},
        "file_id": "",
    }
    out = asyncio.run(graph._node_decision_async(state))
    assert out["need_kb"] is False
    assert out["context_score"] == 0.33
    assert "Decision: test" in out["trace"][0]


def test_agent_core_exposes_brain_property(monkeypatch):
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

    monkeypatch.setattr(agent_core_module, "DatabaseManager", _FakeDBManager)
    monkeypatch.setattr(agent_core_module, "TaskStore", _FakeTaskStore)
    monkeypatch.setattr(agent_core_module, "TaskRunner", _FakeTaskRunner)
    monkeypatch.setattr(agent_core_module, "VectorStore", _FakeVectorStore)
    monkeypatch.setattr(agent_core_module, "RagService", _FakeRagService)
    monkeypatch.setattr(agent_core_module, "FileWorkspace", _FakeFileWorkspace)
    monkeypatch.setattr(agent_core_module, "GraphAgent", _FakeGraphAgent)
    monkeypatch.setattr(agent_core_module.AgentCore, "_sync_knowledge_base", lambda self: {"mode": "no_change"})

    core = agent_core_module.AgentCore()
    assert hasattr(core, "brain")
    assert core.brain is not None
    assert core.brain.planner_chain is core.planner
    assert core.brain.decision_chain is core.decision
    assert core.brain.synthesis_chain is core.synthesis

