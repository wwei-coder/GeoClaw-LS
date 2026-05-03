from __future__ import annotations

from typing import Any, Dict


class KnowledgeBaseService:
    def sync(self, agent: Any) -> Dict[str, Any]:
        return agent.sync_knowledge_base_now()

    def status(self, agent: Any) -> Dict[str, Any]:
        return agent.get_knowledge_base_status()

    def documents(self, agent: Any) -> Dict[str, Any]:
        return {"documents": agent.get_document_index_stats()}

    def diagnostics(self, agent: Any, *, limit: int) -> Dict[str, Any]:
        safe_limit = max(1, min(limit, 100))
        return agent.get_retrieval_diagnostics(limit=safe_limit)

    def rebuild(self, agent: Any) -> Dict[str, Any]:
        return agent.rebuild_knowledge_base_now()

    def system_reset(self, agent: Any) -> Dict[str, Any]:
        agent.factory_reset()
        return {"ok": True, "message": "已触发系统重置，下一次请求将重新初始化引擎。"}
