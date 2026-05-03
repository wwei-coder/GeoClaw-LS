from __future__ import annotations
from pathlib import Path
from capabilities.rag import RagService
from capabilities.rag.tool import RagTool as CapabilityRagTool
from tools.rag_tool import RagTool as RegistryRagTool

class _FakeCollection:
    def __init__(self, count: int = 1):
        self._count = count
        self.metadata = {"k": "v"}

    def count(self):
        return self._count

class _FakeVectorStore:
    def __init__(self):
        self.collection = _FakeCollection(count=1)
        self.last_search_meta = {}

    def get_runtime_stats(self):
        return {"cache_enabled": True}

    def build_full(self, _chunks):
        return None

    def deactivate_by_docs(self, _doc_names):
        return None

    def add_chunks(self, _chunks):
        return None

    def search(self, query, top_k=3, filter=None, search_mode="hybrid"):
        return [
            {
                "id": "c1",
                "doc_name": "doc.txt",
                "content": f"{query}|{top_k}|{search_mode}|{bool(filter)}",
            }
        ]

def test_rag_service_incremental_no_change(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    fp_path = tmp_path / "fingerprint.json"
    store = _FakeVectorStore()
    service = RagService(
        vector_store=store,
        data_dir=str(data_dir),
        fingerprint_path=str(fp_path),
        collection_name="kb",
        embedding_model="emb",
        embedding_backend="ollama",
        rerank_strategy="keyword",
        rerank_model="none",
    )
    summary = service.incremental_update(current_fp={}, saved_fp={})
    assert summary["mode"] == "no_change"
    assert summary["changes"] == {"added": 0, "updated": 0, "removed": 0}

def test_rag_service_status_and_retrieve(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    fp_path = tmp_path / "fingerprint.json"
    store = _FakeVectorStore()
    service = RagService(
        vector_store=store,
        data_dir=str(data_dir),
        fingerprint_path=str(fp_path),
        collection_name="kb",
        embedding_model="emb",
        embedding_backend="ollama",
        rerank_strategy="keyword",
        rerank_model="none",
    )
    status = service.get_status(last_sync={"mode": "init"})
    assert status["collection_name"] == "kb"
    assert status["collection_count"] == 1
    result = service.retrieve(query="q", top_k=2)
    assert result["sources"] == ["doc.txt"]
    assert result["chunks"][0]["doc_name"] == "doc.txt"

def test_rag_tool_registry_import_available():
    assert CapabilityRagTool is not None
    assert RegistryRagTool is not None
