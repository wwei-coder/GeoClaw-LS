from __future__ import annotations
from capabilities.kg_rag import (
    Entity,
    GraphRetriever,
    GraphSearchRequest,
    HybridRagRequest,
    HybridRetriever,
    InMemoryGraphStore,
    KGRagService,
    KGRagTool,
    Relation,
    get_capability,
)
from capabilities.kg_rag.schemas import GraphSearchResult, HybridRagResult
from capabilities.registry import get_default_capabilities
from storage.graph import GraphStore
from tools.base import ToolInput, ToolResult
from tools.registry import get_tool_instances

def test_kg_rag_schemas_can_instantiate():
    ent = Entity(id="e1", name="滑坡", type="hazard")
    rel = Relation(id="r1", source_id="e1", target_id="e2", relation_type="causes", evidence="x")
    assert ent.name == "滑坡"
    assert rel.relation_type == "causes"

def test_inmemory_graph_store_entity_and_neighbor_search():
    store = InMemoryGraphStore()
    e1 = Entity(id="e1", name="滑坡")
    e2 = Entity(id="e2", name="降雨")
    store.add_entity(e1)
    store.add_entity(e2)
    store.add_relation(Relation(id="r1", source_id="e1", target_id="e2", relation_type="related"))

    hits = store.search_entities("滑", top_k=5)
    assert hits and hits[0].id == "e1"
    neighbors = store.get_neighbors("e1", depth=1)
    assert neighbors and neighbors[0].id == "e2"

def test_inmemory_graph_store_relation_search():
    store = InMemoryGraphStore()
    store.add_entity(Entity(id="e1", name="A"))
    store.add_entity(Entity(id="e2", name="B"))
    store.add_relation(Relation(id="r1", source_id="e1", target_id="e2", relation_type="co_occurs"))
    rels = store.search_relations(entity_id="e1", top_k=10)
    assert len(rels) == 1
    assert rels[0].relation_type == "co_occurs"

def test_graph_retriever_returns_structured_result():
    store = InMemoryGraphStore()
    store.add_entity(Entity(id="e1", name="滑坡"))
    retriever = GraphRetriever(store)
    out = retriever.retrieve(GraphSearchRequest(query="滑坡", top_k=3))
    assert isinstance(out, GraphSearchResult)
    assert out.metadata["mode"] == "graph_only"

def test_hybrid_retriever_graph_only_when_no_vector_retriever():
    store = InMemoryGraphStore()
    store.add_entity(Entity(id="e1", name="滑坡"))
    hybrid = HybridRetriever(graph_retriever=GraphRetriever(store), vector_retriever=None)
    out = hybrid.retrieve(HybridRagRequest(query="滑坡", top_k=3, use_vector=True, use_graph=True))
    assert isinstance(out, HybridRagResult)
    assert out.graph_result is not None
    assert out.vector_result == []
    assert out.metadata["vector_used"] is False

def test_kg_rag_service_ingest_search_hybrid_status():
    service = KGRagService()
    summary = service.ingest_text("滑坡 与 降雨 关系明显", source="demo")
    assert summary["entities"] >= 1
    graph_out = service.search_graph("滑坡", top_k=5)
    hybrid_out = service.hybrid_retrieve("滑坡", top_k=5)
    status = service.get_status()
    assert graph_out.metadata["mode"] == "graph_only"
    assert isinstance(hybrid_out, HybridRagResult)
    assert status["ready"] is True

def test_kg_rag_tool_runs_without_llm():
    tool = KGRagTool(service=KGRagService())
    result = tool.run(ToolInput(task="滑坡与降雨关系"), agent=None)
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.metadata["tool"] == "KG_RAG"

def test_kg_rag_capability_disabled_by_default():
    cap = get_capability()
    assert cap.name == "kg_rag"
    assert cap.enabled is False

def test_capability_registry_default_list_not_enabling_kg_rag():
    names = [c.name for c in get_default_capabilities()]
    assert "rag" in names
    assert "kg_rag" not in names

def test_tool_registry_default_not_expose_kg_rag_and_keep_standard_tools():
    tools = get_tool_instances()
    assert "KG_RAG" not in tools
    for name in [
        "RAG",
        "MEMORY",
        "LLM",
        "CALCULATOR",
        "DISCOVERY",
        "DATA_PROFILE",
        "FILE_INSPECTOR",
    ]:
        assert name in tools

def test_storage_graph_importable():
    assert GraphStore is not None
