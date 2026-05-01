import os
import re
import json
import asyncio
import threading
import contextvars
from typing import Dict, List, Any, Optional
from loguru import logger
from utils.ollama_client import ask_ollama, ask_ollama_async
from rag.vector_store import VectorStore
from memory.database_manager import DatabaseManager
import core.prompts as prompts
from core.tools import TOOL_REGISTRY
from core.graph_agent import GraphAgent
from agent.task_store import TaskStore
from agent.task_runner import TaskRunner
from core.file_workspace import FileWorkspace
from memory.doc_fingerprint import generate_fingerprint, load_fingerprint, save_fingerprint, diff_fingerprint
from rag.loader import load_documents_from_dir
from rag.chunker import build_knowledge_chunks
from core.config import (
    DB_PATH,
    DATA_DIR,
    FINGERPRINT_PATH,
    TERMINOLOGY_REPLACEMENTS,
    ALLOWED_ENGLISH_WORDS,
    INSAR_BAD_PHRASES,
    DEFAULT_EMBEDDING_MODEL,
    OLLAMA_TEMPERATURE,
    LLM_TEMPERATURE_TERMINOLOGY_REWRITE,
    LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
    RETRIEVAL_METRICS_ENABLED,
    RETRIEVAL_METRICS_WINDOW,
    RETRIEVAL_METRICS_LOG_PATH,
    VECTOR_COLLECTION_NAME,
    EMBEDDING_BACKEND,
    RERANK_STRATEGY,
    RERANK_MODEL_NAME
)

from core.chains import (
    SmallTalkChain,
    MemoryQueryChain,
    PlannerChain,
    HeuristicDecisionChain,
    RetrieverChain,
    SynthesisChain
)
from core.question_classifier import (
    is_small_talk,
    is_memory_query,
)
class AgentCore:
    def __init__(self):
        self.user_id = "default_user"
        self.session_id = None # Current session
        self.db_manager = DatabaseManager(DB_PATH)
        self.task_store = None
        self.task_runner = None
        try:
            self.task_store = TaskStore(self.db_manager)
            self.task_runner = TaskRunner(self, max_workers=1)
        except Exception as exc:
            logger.warning(f"[TaskStore] 初始化失败，将以无持久化模式运行: {exc}")
        self.short_memory: List[str] = []
        self.summary_memory = ""
        self.user_preferences: Dict[str, str] = {} # 用户偏好记忆
        self.temperature = OLLAMA_TEMPERATURE

        self.pending_tool_call = None  # For human-in-the-loop confirmation
        self._kb_sync_lock = threading.RLock()
        self._execution_lock = threading.RLock()
        self._last_kb_sync_summary: Dict[str, Any] = {"mode": "init"}
        self._request_session_id_var = contextvars.ContextVar("request_session_id", default=None)
        self.file_workspace = FileWorkspace(root_dir="workspace")
        self.active_file_id: Optional[str] = None
        self.active_files: List[Dict[str, Any]] = []

        self.vector_store = VectorStore(
            model_name=DEFAULT_EMBEDDING_MODEL,
            index_path="vector_db"
        )
        self._sync_knowledge_base()

        logger.info(f"[Memory] 历史对话条数 = {self.db_manager.get_conversation_count()}")

        # Ensure at least one session exists
        sessions = self.db_manager.get_all_sessions()
        if not sessions:
            self.session_id = self.db_manager.create_session("默认对话")
        else:
            # Load the most recent session (ordered by updated_at DESC)
            self.session_id = sessions[0][0]

        # Load context for this session
        self.switch_session(self.session_id)

        # Initialize LangChain Chains
        self.planner = PlannerChain()
        self.decision = HeuristicDecisionChain(agent_core=self)
        self.retriever = RetrieverChain(vector_store=self.vector_store)
        self.synthesis = SynthesisChain(agent_core=self)

        self.small_talk = SmallTalkChain(agent_core=self)
        self.memory_query = MemoryQueryChain(agent_core=self)

        # Initialize Graph Agent
        self.graph_agent = GraphAgent(self)

    def _full_rebuild_knowledge_base(self, current_fp: Dict[str, Any], reason: str = "force_rebuild") -> Dict[str, Any]:
        logger.info("📚 执行全量重建向量库…")
        documents = load_documents_from_dir(DATA_DIR)
        chunks = build_knowledge_chunks(documents)
        self.vector_store.build_full(chunks)
        save_fingerprint(current_fp, FINGERPRINT_PATH)
        logger.info(f"✅ 全量重建完成，文档数={len(documents)}，切块数={len(chunks)}")
        return {
            "mode": "full",
            "reason": reason,
            "documents": len(documents),
            "chunks": len(chunks),
            "changes": {
                "added": len(current_fp.keys()),
                "updated": 0,
                "removed": 0
            }
        }

    def _incremental_update_knowledge_base(self, current_fp: Dict[str, Any], saved_fp: Dict[str, Any]) -> Dict[str, Any]:
        changes = diff_fingerprint(current_fp, saved_fp)
        if not changes["changed"]:
            logger.info("📚 文档无变化，跳过增量更新。")
            return {
                "mode": "no_change",
                "changes": {"added": 0, "updated": 0, "removed": 0},
                "documents": 0,
                "chunks": 0
            }

        changed_for_reload = sorted(changes["added"] + changes["updated"])
        docs_to_remove = sorted(changes["removed"] + changes["updated"])
        logger.info(
            f"📚 检测到文档变更：新增={len(changes['added'])}，修改={len(changes['updated'])}，删除={len(changes['removed'])}"
        )
        if docs_to_remove:
            self.vector_store.deactivate_by_docs(docs_to_remove)
        if changed_for_reload:
            changed_docs = load_documents_from_dir(DATA_DIR, file_names=changed_for_reload)
            changed_chunks = build_knowledge_chunks(changed_docs)
            self.vector_store.add_chunks(changed_chunks)
            logger.info(f"📚 增量写入完成：文档数={len(changed_docs)}，切块数={len(changed_chunks)}")
            touched_documents = len(changed_docs)
            touched_chunks = len(changed_chunks)
        else:
            touched_documents = 0
            touched_chunks = 0
        save_fingerprint(current_fp, FINGERPRINT_PATH)
        return {
            "mode": "incremental",
            "changes": {
                "added": len(changes["added"]),
                "updated": len(changes["updated"]),
                "removed": len(changes["removed"])
            },
            "documents": touched_documents,
            "chunks": touched_chunks
        }

    def _sync_knowledge_base(self):
        with self._kb_sync_lock:
            current_fp = generate_fingerprint(DATA_DIR)
            saved_fp = load_fingerprint(FINGERPRINT_PATH) or {}
            collection_count = 0

            force_rebuild = False
            try:
                collection_count = self.vector_store.collection.count()
                if collection_count == 0:
                    logger.info("📚 检测到向量库为空，准备重建...")
                    force_rebuild = True
            except Exception as e:
                logger.warning(f"[AgentCore] 检查向量库状态失败，按需重建: {e}")
                force_rebuild = True

            try:
                if force_rebuild:
                    summary = self._full_rebuild_knowledge_base(current_fp, reason="empty_collection")
                    self._last_kb_sync_summary = summary
                    return summary
                if not saved_fp and collection_count > 0:
                    save_fingerprint(current_fp, FINGERPRINT_PATH)
                    summary = {
                        "mode": "no_change",
                        "reason": "bootstrap_fingerprint",
                        "changes": {"added": 0, "updated": 0, "removed": 0},
                        "documents": 0,
                        "chunks": 0
                    }
                    self._last_kb_sync_summary = summary
                    return summary
                summary = self._incremental_update_knowledge_base(current_fp, saved_fp)
                if summary["mode"] == "no_change":
                    self.vector_store.load()
                self._last_kb_sync_summary = summary
                return summary
            except Exception as e:
                logger.exception(f"[AgentCore] 增量更新失败，回退全量重建: {e}")
                summary = self._full_rebuild_knowledge_base(current_fp, reason="fallback_after_incremental_error")
                self._last_kb_sync_summary = summary
                return summary

    def sync_knowledge_base_now(self) -> Dict[str, Any]:
        return self._sync_knowledge_base()

    def get_last_kb_sync_summary(self) -> Dict[str, Any]:
        return dict(self._last_kb_sync_summary)

    def get_knowledge_base_status(self) -> Dict[str, Any]:
        collection_count = 0
        collection_metadata = {}
        runtime_stats = {}
        try:
            collection = getattr(self.vector_store, "collection", None)
            if collection is not None:
                collection_count = int(collection.count())
                collection_metadata = dict(getattr(collection, "metadata", None) or {})
        except Exception as e:
            logger.warning(f"[AgentCore] 获取知识库 collection 状态失败: {e}")
        try:
            runtime_stats = self.vector_store.get_runtime_stats()
        except Exception as e:
            logger.warning(f"[AgentCore] 获取向量库运行状态失败: {e}")
        current_fp = generate_fingerprint(DATA_DIR)
        saved_fp = load_fingerprint(FINGERPRINT_PATH) or {}
        return {
            "data_dir": DATA_DIR,
            "collection_name": VECTOR_COLLECTION_NAME,
            "collection_count": collection_count,
            "collection_metadata": collection_metadata,
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "embedding_backend": EMBEDDING_BACKEND,
            "rerank_strategy": RERANK_STRATEGY,
            "rerank_model": RERANK_MODEL_NAME,
            "last_sync": dict(self._last_kb_sync_summary),
            "runtime": runtime_stats,
            "fingerprint": {
                "current_count": len(current_fp),
                "saved_count": len(saved_fp),
                "changed": diff_fingerprint(current_fp, saved_fp).get("changed", [])
            }
        }

    def get_document_index_stats(self) -> List[Dict[str, Any]]:
        current_fp = generate_fingerprint(DATA_DIR)
        saved_fp = load_fingerprint(FINGERPRINT_PATH) or {}
        changes = diff_fingerprint(current_fp, saved_fp)
        changed = set(changes.get("changed", []))
        docs: List[Dict[str, Any]] = []
        collection = getattr(self.vector_store, "collection", None)
        for name, fp in sorted(current_fp.items()):
            path = os.path.join(DATA_DIR, name)
            chunk_count = 0
            try:
                if collection is not None:
                    data = collection.get(where={"doc_name": name}, include=[])
                    chunk_count = len(data.get("ids", []) or [])
            except Exception as e:
                logger.warning(f"[AgentCore] 获取文档切片数失败 {name}: {e}")
            docs.append({
                "name": name,
                "path": path,
                "type": os.path.splitext(name)[1].lower().lstrip(".") or "file",
                "size": int(fp.get("size", 0) or 0),
                "mtime": float(fp.get("mtime", 0) or 0),
                "indexed_chunks": chunk_count,
                "fingerprint_status": "changed" if name in changed else "synced",
                "saved": name in saved_fp
            })
        for name in sorted(set(saved_fp.keys()) - set(current_fp.keys())):
            docs.append({
                "name": name,
                "path": os.path.join(DATA_DIR, name),
                "type": os.path.splitext(name)[1].lower().lstrip(".") or "file",
                "size": int((saved_fp.get(name) or {}).get("size", 0) or 0),
                "mtime": float((saved_fp.get(name) or {}).get("mtime", 0) or 0),
                "indexed_chunks": 0,
                "fingerprint_status": "removed",
                "saved": True
            })
        return docs

    def rebuild_knowledge_base_now(self) -> Dict[str, Any]:
        current_fp = generate_fingerprint(DATA_DIR)
        with self._kb_sync_lock:
            summary = self._full_rebuild_knowledge_base(current_fp, reason="manual_web_reindex")
            self._last_kb_sync_summary = summary
            return summary

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
            vector_runtime = self.vector_store.get_runtime_stats()
        except Exception:
            vector_runtime = {}
        return {
            "metrics": metrics,
            "last_search": dict(getattr(self.vector_store, "last_search_meta", {}) or {}),
            "vector_runtime": vector_runtime,
            "metrics_path": RETRIEVAL_METRICS_LOG_PATH,
            "metrics_enabled": RETRIEVAL_METRICS_ENABLED,
            "window": RETRIEVAL_METRICS_WINDOW
        }

    # >>>>>> 会话管理 <<<<<<
    def create_new_session(self, title: str = "新对话") -> int:
        self.session_id = self.db_manager.create_session(title)
        self.short_memory = []
        self.summary_memory = ""
        logger.info(f"[Session] Created new session {self.session_id}")
        return self.session_id

    def delete_session(self, session_id: int):
        self.db_manager.delete_session(session_id)
        # If deleting current session, switch to another or create new
        if self.session_id == session_id:
            sessions = self.db_manager.get_all_sessions()
            if sessions:
                self.switch_session(sessions[0][0])
            else:
                self.create_new_session()

    def rename_session(self, session_id: int, new_title: str):
        self.db_manager.update_session_title(session_id, new_title)

    def switch_session(self, session_id: int):
        self.session_id = session_id
        # Reset context for new session
        self.short_memory = []
        self.summary_memory = ""
        # Reload context from DB if needed
        recent = self.db_manager.get_recent_conversations(self.user_id, limit=4, session_id=session_id)
        for q, a in recent:
            self.short_memory.append(f"用户：{q}")
            self.short_memory.append(f"助手：{a}")
        logger.info(f"[Session] Switched to session {session_id}, loaded {len(recent)} rounds of context")

    # >>>>>> Tool 执行器 <<<<<<
    def execute_tool_step(self, step: dict) -> str:
        """
        Sync execution of a tool.
        If called from an async context, this should be wrapped in run_in_executor.
        """
        tool_name = step["tool"].upper()
        task = step["task"]
        tool_fn = TOOL_REGISTRY.get(tool_name)
        if not tool_fn:
            return f"[错误] 未知工具：{tool_name}"

        try:
            result = tool_fn(task, self)
            if hasattr(result, "to_legacy_text"):
                return result.to_legacy_text()
            return str(result)
        except Exception as e:
            logger.error(f"[ToolError] {tool_name} 执行失败: {e}")
            return f"[系统错误] 工具 {tool_name} 执行异常: {str(e)}"

    # -------------------------
    async def _fix_terminology_async(self, answer: str, question: str = "") -> str:
        final_answer = answer

        # 1. Check for English words (Optimized: Max 1 retry)
        if re.search(r"[A-Za-z]{3,}", final_answer):
             words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", final_answer)
             disallowed = [w for w in words if w not in ALLOWED_ENGLISH_WORDS]
             if disallowed:
                 rewrite_prompt = prompts.REWRITE_PROMPT.format(text=final_answer)
                 try:
                     final_answer = (await ask_ollama_async(rewrite_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_REWRITE)).strip()
                 except Exception as e:
                     logger.warning(f"[Terminology] 英文术语润色失败，保留原回答: {e}")

        # 2. Hard replacements
        for old, new in TERMINOLOGY_REPLACEMENTS:
            final_answer = final_answer.replace(old, new)

        # 3. Fix InSAR if needed
        if "InSAR" in question:
            if ("干涉合成孔径雷达" not in final_answer) or any(p in final_answer for p in INSAR_BAD_PHRASES):
                fix_prompt = prompts.FIX_INSAR_PROMPT.format(question=question, answer=final_answer)
                try:
                    final_answer = (await ask_ollama_async(fix_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR)).strip()
                except Exception as e:
                    logger.warning(f"[Terminology] InSAR 术语修正失败，保留当前回答: {e}")
                    return final_answer

                # Re-check English after fix
                for _ in range(2):
                    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", final_answer)
                    disallowed = [w for w in words if w not in ALLOWED_ENGLISH_WORDS]
                    if not disallowed:
                        break
                    rewrite_prompt = prompts.REWRITE_PROMPT.format(text=final_answer)
                    try:
                        final_answer = (await ask_ollama_async(rewrite_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR)).strip()
                    except Exception as e:
                        logger.warning(f"[Terminology] InSAR 二次英文润色失败，保留当前回答: {e}")
                        break

                for old, new in TERMINOLOGY_REPLACEMENTS:
                    final_answer = final_answer.replace(old, new)

        # 4. Clean up meta-text
        if not any(k in question for k in ("翻译", "英文", "中文")):
            lines = [line for line in final_answer.splitlines() if line.strip()]
            if lines and ("允许保留 InSAR" in lines[0] or "以下是英文单词" in lines[0]):
                lines = [
                    line
                    for line in lines
                    if "允许保留 InSAR" not in line and "以下是英文单词" not in line
                ]
                final_answer = "\n".join(lines).strip()

        return final_answer

    def _fix_terminology(self, answer: str, question: str = "") -> str:
        final_answer = answer

        # 1. Check for English words (Optimized: Max 1 retry)
        if re.search(r"[A-Za-z]{3,}", final_answer):
             words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", final_answer)
             disallowed = [w for w in words if w not in ALLOWED_ENGLISH_WORDS]
             if disallowed:
                 rewrite_prompt = prompts.REWRITE_PROMPT.format(text=final_answer)
                 try:
                     final_answer = ask_ollama(rewrite_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_REWRITE).strip()
                 except Exception as e:
                     logger.warning(f"[Terminology] 英文术语润色失败，保留原回答: {e}")

        # 2. Hard replacements
        for old, new in TERMINOLOGY_REPLACEMENTS:
            final_answer = final_answer.replace(old, new)

        # 3. Fix InSAR if needed
        if "InSAR" in question:
            if ("干涉合成孔径雷达" not in final_answer) or any(p in final_answer for p in INSAR_BAD_PHRASES):
                fix_prompt = prompts.FIX_INSAR_PROMPT.format(question=question, answer=final_answer)
                try:
                    final_answer = ask_ollama(fix_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR).strip()
                except Exception as e:
                    logger.warning(f"[Terminology] InSAR 术语修正失败，保留当前回答: {e}")
                    return final_answer

                # Re-check English after fix
                for _ in range(2):
                    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", final_answer)
                    disallowed = [w for w in words if w not in ALLOWED_ENGLISH_WORDS]
                    if not disallowed:
                        break
                    rewrite_prompt = prompts.REWRITE_PROMPT.format(text=final_answer)
                    try:
                        final_answer = ask_ollama(rewrite_prompt, temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR).strip()
                    except Exception as e:
                        logger.warning(f"[Terminology] InSAR 二次英文润色失败，保留当前回答: {e}")
                        break

                for old, new in TERMINOLOGY_REPLACEMENTS:
                    final_answer = final_answer.replace(old, new)

        # 4. Clean up meta-text
        if not any(k in question for k in ("翻译", "英文", "中文")):
            lines = [line for line in final_answer.splitlines() if line.strip()]
            if lines and ("允许保留 InSAR" in lines[0] or "以下是英文单词" in lines[0]):
                lines = [
                    line
                    for line in lines
                    if "允许保留 InSAR" not in line and "以下是英文单词" not in line
                ]
                final_answer = "\n".join(lines).strip()

        return final_answer

    def _build_fallback_session_title(self, first_question: str) -> str:
        text = (first_question or "").strip()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[\"'《》“”‘’`]", "", text)
        text = re.sub(r"[，,。！？!?:：；;（）()【】\[\]{}<>]", "", text)
        if not text:
            return "新对话"
        return text[:10]

    async def _auto_rename_session_async(self, session_id: int, first_question: str):
        try:
            # Short prompt to generate title
            prompt = f"请为以下用户问题生成一个简短的会话标题（不超过10个字），直接输出标题，不要包含引号或其他文字：\n{first_question}"
            title = await ask_ollama_async(prompt)
            title = title.strip()
            # Cleanup title
            title = re.sub(r'["\'《》]', '', title)
            if len(title) > 15:
                title = title[:15]

            if not title:
                title = self._build_fallback_session_title(first_question)

            logger.info(f"[Session] Auto-renaming session {session_id} to '{title}'")
            self.rename_session(session_id, title)
        except Exception as e:
            fallback_title = self._build_fallback_session_title(first_question)
            try:
                self.rename_session(session_id, fallback_title)
                logger.warning(f"[Session] Auto-rename failed: {e}；已使用兜底标题 '{fallback_title}'")
            except Exception as rename_error:
                logger.warning(f"[Session] Auto-rename failed: {e}；兜底重命名也失败: {rename_error}")

    def get_active_session_id(self) -> Optional[int]:
        sid = self._request_session_id_var.get()
        if sid is not None:
            return sid
        sid = getattr(self, "_active_chat_session_id", None)
        if sid is not None:
            return sid
        return self.session_id

    async def chat_async(
        self,
        question: str,
        cancel_event=None,
        stream_callback=None,
        file_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
        run_mode: str = "sync",
        resumed_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Async version of chat
        """
        if cancel_event is not None and getattr(cancel_event, "is_set", None) and cancel_event.is_set():
            return {"answer": "已取消本轮生成", "confidence": 0.0, "sources": []}

        request_session_id = self.session_id
        token = self._request_session_id_var.set(request_session_id)
        self._active_chat_session_id = request_session_id
        self._active_cancel_event = cancel_event
        self.active_file_id = (file_id or "").strip() or None
        self.active_files = list(files or [])

        try:
            with self._execution_lock:
                if request_session_id:
                    try:
                        if len(self.short_memory) == 0:
                             asyncio.create_task(self._auto_rename_session_async(request_session_id, question))
                    except Exception as e:
                        logger.warning(f"[Session] 异步自动重命名任务创建失败: {e}")

                if is_small_talk(question):
                    return await self.small_talk.ainvoke({"question": question})
                if is_memory_query(question):
                    return await self.memory_query.ainvoke({"question": question})

                if self.pending_tool_call:
                    judge_prompt = prompts.CONFIRMATION_JUDGE_PROMPT.format(question=question)
                    intent = (await ask_ollama_async(judge_prompt)).strip().upper()

                    if "YES" in intent:
                        tool_step = self.pending_tool_call
                        logger.info(f"[Agent] 用户批准执行: {tool_step['tool']}")
                        if stream_callback:
                            stream_callback(f"\n> [系统] 用户已批准，正在执行 {tool_step['tool']}...\n")

                        loop = asyncio.get_running_loop()
                        result_text = await loop.run_in_executor(None, lambda: self.execute_tool_step(tool_step))

                        self.pending_tool_call = None
                        return {"answer": f"已执行操作。结果：{result_text}", "confidence": 1.0, "sources": []}

                    elif "NO" in intent:
                        self.pending_tool_call = None
                        return {"answer": "已取消执行。", "confidence": 0.0, "sources": []}
                    else:
                        self.pending_tool_call = None

                self._current_stream_callback = stream_callback
                result = await self.graph_agent.run_async(
                    question,
                    file_id=self.active_file_id,
                    files=self.active_files,
                    task_id=task_id or "",
                    run_mode=run_mode or "sync",
                    resumed_from=resumed_from,
                )
                return result
        except Exception as e:
            logger.exception("系统运行出错")
            return {"answer": f"系统运行出错: {str(e)}", "confidence": 0.0, "sources": []}
        finally:
            self._request_session_id_var.reset(token)
            self._current_stream_callback = None
            self._active_chat_session_id = None
            self._active_cancel_event = None
            self.active_file_id = None
            self.active_files = []

    # --------------------------------------------------
    def load_history_to_ui(self, limit: int = 10, session_id: Optional[int] = None) -> str:
        sid = session_id if session_id is not None else self.get_active_session_id()
        if sid is not None:
            rows = self.db_manager.get_conversations_by_session(sid, limit)
        else:
            rows = self.db_manager.get_recent_conversations(self.user_id, limit)
        return "\n".join([f"用户：{q}\n助手：{a}" for q, a in rows])

    def factory_reset(self):
        self.db_manager.clear_conversations()
        try:
            if hasattr(self.vector_store, "close"):
                self.vector_store.close()
        except Exception as e:
            logger.warning(f"[Reset] 关闭向量库句柄失败: {e}")

        # 标记为待重置
        from core.reset_handler import mark_for_reset
        mark_for_reset()

        self.summary_memory = ""
        self.user_preferences = {}
        self.short_memory.clear()
        self.session_id = None
        logger.warning("🧨 已标记重置，下次启动将彻底清理 vector_db")
