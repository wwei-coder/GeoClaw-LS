from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional
from loguru import logger
from utils.ollama_client import ask_ollama_async
from capabilities.rag.indexing.fingerprint import (
    diff_fingerprint,
    generate_fingerprint,
    load_fingerprint,
)
from config_runtime import (
    DATA_DIR,
    FINGERPRINT_PATH,
    RETRIEVAL_METRICS_ENABLED,
    RETRIEVAL_METRICS_LOG_PATH,
    RETRIEVAL_METRICS_WINDOW,
)

class AgentSessionFacade:
    def __init__(self, agent: Any):
        self.agent = agent

    def create_new_session(self, title: str = "新对话") -> int:
        self.agent.session_id = self.agent.db_manager.create_session(title)
        self.agent.short_memory = []
        self.agent.summary_memory = ""
        logger.info(f"[Session] Created new session {self.agent.session_id}")
        return self.agent.session_id

    def delete_session(self, session_id: int):
        self.agent.db_manager.delete_session(session_id)
        if self.agent.session_id == session_id:
            sessions = self.agent.db_manager.get_all_sessions()
            if sessions:
                self.switch_session(sessions[0][0])
            else:
                self.create_new_session()

    def rename_session(self, session_id: int, new_title: str):
        self.agent.db_manager.update_session_title(session_id, new_title)

    def switch_session(self, session_id: int):
        self.agent.session_id = session_id
        self.agent.short_memory = []
        self.agent.summary_memory = ""
        recent = self.agent.db_manager.get_recent_conversations(
            self.agent.user_id,
            limit=4,
            session_id=session_id,
        )
        for q, a in recent:
            self.agent.short_memory.append(f"用户：{q}")
            self.agent.short_memory.append(f"助手：{a}")
        logger.info(f"[Session] Switched to session {session_id}, loaded {len(recent)} rounds of context")

    def get_active_session_id(self) -> Optional[int]:
        req_ctx = self.agent._request_context_var.get()
        if req_ctx is not None and getattr(req_ctx, "session_id", None) is not None:
            return req_ctx.session_id
        sid = self.agent._request_session_id_var.get()
        if sid is not None:
            return sid
        sid = getattr(self.agent, "_active_chat_session_id", None)
        if sid is not None:
            return sid
        return self.agent.session_id

    def load_history_to_ui(self, limit: int = 10, session_id: Optional[int] = None) -> str:
        sid = session_id if session_id is not None else self.get_active_session_id()
        if sid is not None:
            rows = self.agent.db_manager.get_conversations_by_session(sid, limit)
        else:
            rows = self.agent.db_manager.get_recent_conversations(self.agent.user_id, limit)
        return "\n".join([f"用户：{q}\n助手：{a}" for q, a in rows])

    def build_fallback_session_title(self, first_question: str) -> str:
        text = (first_question or "").strip()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[\"'《》“”‘’`]", "", text)
        text = re.sub(r"[，,。！？!?:：；;（）()【】\[\]{}<>]", "", text)
        if not text:
            return "新对话"
        return text[:10]

    async def auto_rename_session_async(self, session_id: int, first_question: str):
        try:
            prompt = f"请为以下用户问题生成一个简短的会话标题（不超过10个字），直接输出标题，不要包含引号或其他文字：\n{first_question}"
            title = await ask_ollama_async(prompt)
            title = title.strip()
            title = re.sub(r'["\'《》]', "", title)
            if len(title) > 15:
                title = title[:15]

            if not title:
                title = self.build_fallback_session_title(first_question)

            logger.info(f"[Session] Auto-renaming session {session_id} to '{title}'")
            self.rename_session(session_id, title)
        except Exception as e:
            fallback_title = self.build_fallback_session_title(first_question)
            try:
                self.rename_session(session_id, fallback_title)
                logger.warning(f"[Session] Auto-rename failed: {e}；已使用兜底标题 '{fallback_title}'")
            except Exception as rename_error:
                logger.warning(f"[Session] Auto-rename failed: {e}；兜底重命名也失败: {rename_error}")

class AgentKnowledgeBaseFacade:
    def __init__(self, agent: Any):
        self.agent = agent

    def sync_knowledge_base_now(self) -> Dict[str, Any]:
        return self.agent._sync_knowledge_base()

    def get_last_kb_sync_summary(self) -> Dict[str, Any]:
        return dict(self.agent._last_kb_sync_summary)

    def rebuild_knowledge_base_now(self) -> Dict[str, Any]:
        current_fp = generate_fingerprint(DATA_DIR)
        with self.agent._kb_sync_lock:
            summary = self.agent._full_rebuild_knowledge_base(current_fp, reason="manual_web_reindex")
            self.agent._last_kb_sync_summary = summary
            return summary

    def get_knowledge_base_status(self) -> Dict[str, Any]:
        return self.agent.rag_service.get_status(last_sync=dict(self.agent._last_kb_sync_summary))

    def get_document_index_stats(self) -> List[Dict[str, Any]]:
        current_fp = generate_fingerprint(DATA_DIR)
        saved_fp = load_fingerprint(FINGERPRINT_PATH) or {}
        changes = diff_fingerprint(current_fp, saved_fp)
        changed = set(changes.get("changed", []))
        docs: List[Dict[str, Any]] = []
        collection = getattr(self.agent.vector_store, "collection", None)
        for name, fp in sorted(current_fp.items()):
            path = os.path.join(DATA_DIR, name)
            chunk_count = 0
            try:
                if collection is not None:
                    data = collection.get(where={"doc_name": name}, include=[])
                    chunk_count = len(data.get("ids", []) or [])
            except Exception as e:
                logger.warning(f"[AgentCore] 获取文档切片数失败 {name}: {e}")
            docs.append(
                {
                    "name": name,
                    "path": path,
                    "type": os.path.splitext(name)[1].lower().lstrip(".") or "file",
                    "size": int(fp.get("size", 0) or 0),
                    "mtime": float(fp.get("mtime", 0) or 0),
                    "indexed_chunks": chunk_count,
                    "fingerprint_status": "changed" if name in changed else "synced",
                    "saved": name in saved_fp,
                }
            )
        for name in sorted(set(saved_fp.keys()) - set(current_fp.keys())):
            docs.append(
                {
                    "name": name,
                    "path": os.path.join(DATA_DIR, name),
                    "type": os.path.splitext(name)[1].lower().lstrip(".") or "file",
                    "size": int((saved_fp.get(name) or {}).get("size", 0) or 0),
                    "mtime": float((saved_fp.get(name) or {}).get("mtime", 0) or 0),
                    "indexed_chunks": 0,
                    "fingerprint_status": "removed",
                    "saved": True,
                }
            )
        return docs

    def get_retrieval_diagnostics(self, limit: int = 20) -> Dict[str, Any]:
        metrics = []
        try:
            if os.path.exists(RETRIEVAL_METRICS_LOG_PATH):
                with open(RETRIEVAL_METRICS_LOG_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-max(1, int(limit)):]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        metrics.append(json.loads(line))
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"[AgentCore] 读取检索指标失败: {e}")
        try:
            vector_runtime = self.agent.vector_store.get_runtime_stats()
        except Exception:
            vector_runtime = {}
        return {
            "metrics": metrics,
            "last_search": dict(getattr(self.agent.vector_store, "last_search_meta", {}) or {}),
            "vector_runtime": vector_runtime,
            "metrics_path": RETRIEVAL_METRICS_LOG_PATH,
            "metrics_enabled": RETRIEVAL_METRICS_ENABLED,
            "window": RETRIEVAL_METRICS_WINDOW,
        }
