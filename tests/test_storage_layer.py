from __future__ import annotations

from agent.runtime import RuntimePersistence
from capabilities.memory.summary import extract_user_preferences as NewExtractUserPreferences
from capabilities.memory.summary import summarize_dialog as NewSummarizeDialog
from capabilities.rag.indexing.fingerprint import generate_fingerprint as NewGenerateFingerprint
from core.file_workspace import FileWorkspace
from storage.artifacts import ArtifactStore
from storage.schemas import StoredArtifact, StoredSession, StoredTaskSummary, VectorIndexStatus
from storage.sqlite.database_manager import DatabaseManager as StorageDatabaseManager
from storage.sqlite import SessionRepository, TaskRepository
from storage.vector.vector_store import OllamaEmbeddingClient as StorageOllamaEmbeddingClient
from storage.vector.vector_store import VectorStore as StorageVectorStore
from storage.vector import VectorIndexAdapter
from utils.logger import logger


class _FakeDBManager:
    def __init__(self):
        self.sessions = [(1, "默认对话", "2026-01-01", "2026-01-01")]
        self.deleted = []

    def get_all_sessions(self):
        return self.sessions

    def create_session(self, title="新对话"):
        _ = title
        return 2

    def update_session_title(self, session_id, new_title):
        _ = (session_id, new_title)

    def delete_session(self, session_id):
        self.deleted.append(session_id)


class _FakeTaskStore:
    def __init__(self):
        self.calls = []

    def save_task(self, task, session_id=None):
        self.calls.append(("save_task", task, session_id))

    def save_step(self, task_id, step, position):
        self.calls.append(("save_step", task_id, step, position))

    def save_artifact(self, task_id, artifact):
        self.calls.append(("save_artifact", task_id, artifact))

    def get_task(self, task_id):
        return {"task_id": task_id}

    def list_tasks(self, session_id=None, limit=50):
        return [{"session_id": session_id, "limit": limit}]

    def list_artifacts(self, task_id=None, limit=50):
        return [{"task_id": task_id, "limit": limit}]

    def get_artifact(self, artifact_id):
        return {"id": artifact_id, "path": "artifacts/x.md"}


class _FailingRepository:
    def save_task(self, task, session_id=None):
        _ = (task, session_id)
        raise RuntimeError("x")

    def save_step(self, task_id, step, position):
        _ = (task_id, step, position)
        raise RuntimeError("x")

    def save_artifact(self, task_id, artifact):
        _ = (task_id, artifact)
        raise RuntimeError("x")


class _FakeFileWorkspace:
    def __init__(self):
        self.saved = []

    def get_artifact(self, artifact_id):
        if artifact_id == "local":
            return {"id": "local", "abs_path": "workspace/artifacts/local.md", "path": "artifacts/local.md"}
        return None

    def save_artifact(self, name, content, mime_type="text/markdown; charset=utf-8", metadata=None):
        payload = {"id": "a1", "name": name, "path": "artifacts/a1.md", "mime_type": mime_type, "metadata": metadata or {}}
        self.saved.append((name, content, mime_type, metadata))
        return payload


class _FakeCollection:
    def __init__(self):
        self.name = "kb"

    def count(self):
        return 7


class _FakeVectorStore:
    def __init__(self):
        self.collection = _FakeCollection()
        self.calls = []

    def get_runtime_stats(self):
        return {"cache_enabled": True}

    def search(self, query, top_k=3, filter=None, search_mode="hybrid"):
        self.calls.append(("search", query, top_k, filter, search_mode))
        return [{"id": "c1", "doc_name": "d1"}]

    def build_full(self, chunks):
        self.calls.append(("build_full", len(chunks)))

    def add_chunks(self, chunks):
        self.calls.append(("add_chunks", len(chunks)))

    def deactivate_by_docs(self, doc_names):
        self.calls.append(("deactivate_by_docs", list(doc_names)))

    def load(self):
        self.calls.append(("load",))
        return True


def test_storage_schemas_can_instantiate():
    s = StoredSession(session_id=1, title="t")
    t = StoredTaskSummary(task_id="task1")
    a = StoredArtifact(artifact_id="art1")
    v = VectorIndexStatus(collection_name="kb", count=1)
    assert s.session_id == 1
    assert t.task_id == "task1"
    assert a.artifact_id == "art1"
    assert v.count == 1


def test_session_repository_with_fake_db_manager():
    repo = SessionRepository(_FakeDBManager())
    rows = repo.list_sessions()
    assert rows and rows[0].session_id == 1
    assert repo.create_session("新会话") == 2
    repo.rename_session(1, "改名")
    repo.delete_session(1)


def test_task_repository_with_fake_task_store():
    store = _FakeTaskStore()
    repo = TaskRepository(store)
    repo.save_task({"id": "t1"}, session_id=10)
    repo.save_step("t1", {"id": "s1"}, 0)
    repo.save_artifact("t1", {"id": "a1"})
    assert [c[0] for c in store.calls] == ["save_task", "save_step", "save_artifact"]


def test_runtime_persistence_supports_task_repository():
    store = _FakeTaskStore()
    repo = TaskRepository(store)
    p = RuntimePersistence(task_repository=repo, session_provider=lambda: 8)
    p.save_task({"id": "t1"})
    p.save_step("t1", {"id": "s1"}, 0)
    p.save_artifact("t1", {"id": "a1"})
    assert len(store.calls) == 3
    assert store.calls[0][2] == 8


def test_runtime_persistence_repository_exception_does_not_raise():
    p = RuntimePersistence(task_repository=_FailingRepository())
    logger.disable("agent.runtime.persistence")
    try:
        p.save_task({"id": "t1"})
        p.save_step("t1", {"id": "s1"}, 0)
        p.save_artifact("t1", {"id": "a1"})
    finally:
        logger.enable("agent.runtime.persistence")


def test_artifact_store_minimal_wrapper_with_fake_workspace_and_repo():
    repo = TaskRepository(_FakeTaskStore())
    ws = _FakeFileWorkspace()
    store = ArtifactStore(file_workspace=ws, task_repository=repo)
    listed = store.list_artifacts(task_id="t1")
    assert isinstance(listed, list)
    hit_local = store.get_artifact("local")
    assert isinstance(hit_local, dict)
    hit_repo = store.get_artifact("missing")
    assert isinstance(hit_repo, dict)
    saved = store.register_artifact(name="r.md", content="hello")
    assert saved["id"] == "a1"
    assert store.resolve_artifact_path("local")


def test_vector_index_adapter_with_fake_vector_store():
    vs = _FakeVectorStore()
    adapter = VectorIndexAdapter(vs)
    assert adapter.count() == 7
    status = adapter.get_status()
    assert status["count"] == 7
    out = adapter.search("q", top_k=2)
    assert out and out[0]["id"] == "c1"
    adapter.build_full([])
    adapter.add_chunks([])
    adapter.deactivate_by_docs(["d1"])
    assert adapter.load() is True


def test_storage_related_main_imports_available():
    assert FileWorkspace is not None
    assert RuntimePersistence is not None


def test_primary_storage_and_capability_import_paths_available():
    assert StorageDatabaseManager is not None
    assert StorageVectorStore is not None
    assert StorageOllamaEmbeddingClient is not None
    assert NewSummarizeDialog is not None
    assert NewExtractUserPreferences is not None
    assert NewGenerateFingerprint is not None
