from __future__ import annotations

from pathlib import Path
import types

import services.config_service as config_service_module
import services.observability_service as observability_service_module
from services.agent_service import AgentService
from services.config_service import ConfigService
from services.file_service import FileService
from services.knowledge_base_service import KnowledgeBaseService
from services.observability_service import ObservabilityService
from services.session_service import SessionService
from services.task_service import TaskService


class _FakeDBForAgent:
    def get_all_sessions(self):
        return [(1, "默认对话", "x")]


class _FakeAgentForChat:
    def __init__(self):
        self.db_manager = _FakeDBForAgent()
        self._active = 1
        self._switched = None

    def get_active_session_id(self):
        return self._active

    def load_history_to_ui(self, limit=60, session_id=None):
        _ = (limit, session_id)
        return "用户：你好\n助手：您好"

    def switch_session(self, sid):
        self._switched = sid

    async def chat_async(self, question, request_context=None, file_id=None, files=None):
        _ = (question, file_id, files)
        if request_context is not None:
            assert request_context.session_id == 1
            assert request_context.file_id == "f1"
            assert request_context.files == [{"id": "f1"}]
        return {
            "answer": "ok",
            "sources": ["s1"],
            "trace": "t",
            "task_id": "task_1",
            "execution_trace": [{"x": 1}],
            "steps": [{"id": "st1"}],
            "artifacts": [{"id": "a1"}],
        }


class _FakeTask:
    def __init__(self, task_id="t1", status="running"):
        self.id = task_id
        self.status = status

    def to_dict(self):
        return {"id": self.id, "status": self.status, "cancel_requested": False, "final_answer": "answer"}


class _FakeStep:
    def __init__(self, status="success"):
        self.status = status

    def to_dict(self):
        return {"status": self.status}


class _FakeArtifact:
    def to_dict(self):
        return {"id": "a1", "name": "report.md", "path": "artifacts/report.md"}


class _FakeTaskStore:
    def __init__(self):
        self.artifacts = {"a1": _FakeArtifact()}

    def list_tasks(self, session_id=None, limit=50):
        _ = (session_id, limit)
        return [_FakeTask("t1", "running")]

    def get_task(self, task_id):
        if task_id != "t1":
            return None
        return {"task": _FakeTask("t1", "running"), "steps": [_FakeStep("success")], "artifacts": [_FakeArtifact()]}

    def list_artifacts(self, task_id=None, limit=50):
        _ = (task_id, limit)
        return [_FakeArtifact()]

    def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)


class _FakeTaskRunner:
    def list_running_status(self):
        return {"t1": {"is_running": True, "cancel_requested": False}}

    def submit_task(self, **kwargs):
        return {"task_id": "t_new", "kwargs": kwargs}

    def cancel_task(self, task_id):
        return {"task_id": task_id, "status": "cancel_requested"}

    def retry_task(self, task_id, step_id=None):
        return {"task_id": task_id, "step_id": step_id, "status": "retry_queued"}

    def resume_task(self, task_id):
        return {"task_id": task_id, "status": "resumed"}


class _FakeWorkspace:
    def __init__(self):
        self.root = Path("workspace")
        self.artifacts_dir = (self.root / "artifacts").resolve()

    def save_upload(self, filename, content):
        _ = content
        return {"id": "f1", "name": filename}

    def list_files(self):
        return [{"id": "f1"}]

    def get_artifact(self, artifact_id):
        if artifact_id == "local":
            return {"abs_path": str((self.artifacts_dir / "local.md").resolve()), "name": "local.md"}
        return None


class _FakeAgent:
    def __init__(self):
        self.task_store = _FakeTaskStore()
        self.task_runner = _FakeTaskRunner()
        self.file_workspace = _FakeWorkspace()
        self.db_manager = types.SimpleNamespace(get_all_sessions=lambda: [(1, "默认对话", "x")])
        self.temperature = 0.7
        self._active = 1

    def get_active_session_id(self):
        return self._active

    def switch_session(self, sid):
        self._active = sid

    def create_new_session(self, title):
        _ = title
        self._active = 2
        return 2

    def rename_session(self, session_id, title):
        _ = (session_id, title)

    def delete_session(self, session_id):
        _ = session_id

    def load_history_to_ui(self, limit=60, session_id=None):
        _ = (limit, session_id)
        return "用户：q\n助手：a"

    def sync_knowledge_base_now(self):
        return {"mode": "incremental"}

    def get_knowledge_base_status(self):
        return {"collection_count": 1}

    def get_document_index_stats(self):
        return [{"name": "doc1"}]

    def get_retrieval_diagnostics(self, limit=20):
        return {"limit": limit}

    def rebuild_knowledge_base_now(self):
        return {"mode": "full"}

    def factory_reset(self):
        return None


def test_agent_service_bootstrap_and_chat_fields():
    svc = AgentService()
    agent = _FakeAgentForChat()
    boot = svc.bootstrap(agent)
    assert set(boot.keys()) == {"sessions", "current_session_id", "history_messages", "status"}
    out = svc.chat(agent, question="q", session_id=1, file_id="f1", files=[{"id": "f1"}])
    assert out["answer"] == "ok"
    assert "session_id" in out and "task_id" in out and "steps" in out and "artifacts" in out


def test_task_service_basic_paths():
    svc = TaskService()
    agent = _FakeAgent()
    listed = svc.list_tasks(agent, session_id=None, limit=50)
    assert listed["tasks"] and "progress" in listed["tasks"][0]
    detail = svc.get_task_detail(agent, task_id="t1")
    assert detail["task"]["id"] == "t1"
    created = svc.create_background_task(agent, message="m", session_id=1, file_id="f1", run_mode="background")
    assert created["task_id"] == "t_new"
    assert created["kwargs"]["request_context"].session_id == 1
    assert created["kwargs"]["request_context"].file_id == "f1"
    assert agent.get_active_session_id() == 1
    assert svc.cancel_task(agent, task_id="t1")["status"] == "cancel_requested"
    assert svc.retry_task(agent, task_id="t1", step_id="s1")["status"] == "retry_queued"
    assert svc.resume_task(agent, task_id="t1")["status"] == "resumed"


def test_session_service_basic_paths():
    svc = SessionService()
    agent = _FakeAgent()
    assert svc.list_sessions(agent)["sessions"]
    assert svc.create_session(agent, title="新会话")["session_id"] == 2
    switched = svc.switch_session(agent, session_id=1)
    assert switched["session_id"] == 1
    assert svc.rename_session(agent, session_id=1, title="改名")["ok"] is True
    deleted = svc.delete_session(agent, session_id=1)
    assert deleted["ok"] is True and "sessions" in deleted


def test_knowledge_base_service_basic_paths():
    svc = KnowledgeBaseService()
    agent = _FakeAgent()
    assert svc.sync(agent)["mode"] == "incremental"
    assert "collection_count" in svc.status(agent)
    assert svc.documents(agent)["documents"][0]["name"] == "doc1"
    assert svc.diagnostics(agent, limit=5)["limit"] == 5
    assert svc.rebuild(agent)["mode"] == "full"
    assert svc.system_reset(agent)["ok"] is True


def test_file_service_basic_paths(tmp_path):
    svc = FileService()
    agent = _FakeAgent()
    agent.file_workspace.root = tmp_path
    agent.file_workspace.artifacts_dir = (tmp_path / "artifacts").resolve()
    agent.file_workspace.artifacts_dir.mkdir(parents=True, exist_ok=True)
    local = agent.file_workspace.artifacts_dir / "local.md"
    local.write_text("x", encoding="utf-8")
    (agent.file_workspace.artifacts_dir / "report.md").write_text("x", encoding="utf-8")
    uploaded = svc.upload_data_file(agent, filename="a.csv", content=b"1,2")
    assert uploaded["ok"] is True
    assert svc.list_uploaded_files(agent)["files"]
    assert svc.get_artifact_download(agent, artifact_id="local")["mode"] == "file"
    assert svc.get_artifact_download(agent, artifact_id="a1")["mode"] == "file"
    assert svc.list_artifacts(agent, limit=20)["artifacts"]


def test_config_service_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    default_cfg = tmp_path / "config.default.yaml"
    cfg.write_text("models:\n  ollama:\n    temperature: 0.7\n", encoding="utf-8")
    default_cfg.write_text("models:\n  ollama:\n    temperature: 0.5\n", encoding="utf-8")
    monkeypatch.setattr(config_service_module, "CONFIG_PATH", cfg)
    monkeypatch.setattr(config_service_module, "DEFAULT_CONFIG_PATH", default_cfg)
    svc = ConfigService()
    payload = svc.get_config()
    assert "data" in payload and "defaults" in payload and "items" in payload
    assert "effective" in payload
    assert payload["effective"]["effective_provider"] == "ollama"
    assert payload["effective"]["provider_locked"] is True
    assert "models.provider" in payload["effective"]["ignored_paths"]
    assert "models.api.*" in payload["effective"]["ignored_paths"]
    agent = _FakeAgent()
    out = svc.save_config(
        agent,
        data={
            "models": {
                "provider": "openai_compatible",
                "api": {
                    "base_url": "https://example.invalid/v1",
                    "api_key": "sk-test",
                    "model": "moonshot-v1",
                },
                "ollama": {"temperature": 0.2},
            }
        },
    )
    assert out["ok"] is True
    assert out["effective"]["effective_provider"] == "ollama"
    assert out["effective"]["provider_locked"] is True
    assert "Ollama-only" in out["warning"]
    assert abs(agent.temperature - 0.2) < 1e-9
    assert "models:" in svc.export_config()
    assert svc.import_config(raw=b"models:\n  ollama:\n    temperature: 0.3\n")["ok"] is True
    assert svc.reset_config()["ok"] is True


def test_observability_service_with_fake_monitor(monkeypatch):
    module = types.SimpleNamespace(
        state={"launched": False, "starting": False, "url": "http://localhost:6006"},
    )

    def get_phoenix_status():
        return dict(module.state)

    def launch_phoenix_monitor():
        module.state["launched"] = True
        module.state["starting"] = False

    def shutdown_phoenix_monitor():
        module.state["launched"] = False
        module.state["starting"] = False

    monkeypatch.setattr(
        observability_service_module,
        "read_observability_enabled_from_config",
        lambda: False,
    )
    writes = {}
    monkeypatch.setattr(
        observability_service_module,
        "write_observability_enabled_to_config",
        lambda enabled: writes.setdefault("enabled", enabled),
    )
    fake_monitor = types.SimpleNamespace(
        get_phoenix_status=get_phoenix_status,
        launch_phoenix_monitor=launch_phoenix_monitor,
        shutdown_phoenix_monitor=shutdown_phoenix_monitor,
    )
    import sys

    monkeypatch.setitem(sys.modules, "utils.phoenix_monitor", fake_monitor)
    svc = ObservabilityService()
    assert svc.status()["ok"] is True
    out = svc.toggle(enabled=True)
    assert out["enabled"] is True
    assert writes.get("enabled") is True
