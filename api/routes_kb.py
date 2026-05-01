from typing import Any
from fastapi import APIRouter
from api.context import bridge

router = APIRouter()

@router.post("/api/kb/sync")
def sync_kb():
    def _inner(agent: Any):
        return agent.sync_knowledge_base_now()

    return bridge.with_agent(_inner)

@router.get("/api/kb/status")
def kb_status():
    def _inner(agent: Any):
        return agent.get_knowledge_base_status()

    return bridge.with_agent(_inner)

@router.get("/api/kb/documents")
def kb_documents():
    def _inner(agent: Any):
        return {"documents": agent.get_document_index_stats()}

    return bridge.with_agent(_inner)

@router.get("/api/kb/diagnostics")
def kb_diagnostics(limit: int = 20):
    safe_limit = max(1, min(limit, 100))

    def _inner(agent: Any):
        return agent.get_retrieval_diagnostics(limit=safe_limit)

    return bridge.with_agent(_inner)

@router.post("/api/kb/rebuild")
def kb_rebuild():
    def _inner(agent: Any):
        return agent.rebuild_knowledge_base_now()

    return bridge.with_agent(_inner)

@router.post("/api/system/reset")
def system_reset():
    def _inner(agent: Any):
        agent.factory_reset()
        return {"ok": True, "message": "已触发系统重置，下一次请求将重新初始化引擎。"}

    result = bridge.with_agent(_inner)
    bridge.reset_agent()
    return result
