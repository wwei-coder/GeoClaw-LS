import os
import json
import asyncio
import threading
import contextvars
from typing import Dict, List, Any, Optional
from loguru import logger
from utils.ollama_client import ask_ollama_async
from storage.sqlite.database_manager import DatabaseManager
from storage.vector.vector_store import VectorStore
from tools.registry import get_tool_registry
from core.agent_core_facades import AgentKnowledgeBaseFacade, AgentSessionFacade
from core.graph_agent import GraphAgent
from agent.brain import LLMBrain
from agent.brain.terminology import fix_terminology, fix_terminology_async
from agent.brain.prompt_catalog import get_prompt_catalog
from agent.runtime import AgentRequestContext, GraphRuntime, get_request_context
from agent.task_store import TaskStore
from agent.task_runner import TaskRunner
from core.file_workspace import FileWorkspace
from capabilities.rag import RagService
from capabilities.rag.indexing.fingerprint import diff_fingerprint, generate_fingerprint, load_fingerprint, save_fingerprint
from capabilities.rag.rerank.rerank import get_reranker
from config_runtime import (
    DB_PATH,
    DATA_DIR,
    FINGERPRINT_PATH,
    DEFAULT_EMBEDDING_MODEL,
    OLLAMA_TEMPERATURE,
    RETRIEVAL_METRICS_ENABLED,
    RETRIEVAL_METRICS_WINDOW,
    RETRIEVAL_METRICS_LOG_PATH,
    VECTOR_COLLECTION_NAME,
    EMBEDDING_BACKEND,
    RERANK_STRATEGY,
    RERANK_MODEL_NAME
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
        self._request_context_var = contextvars.ContextVar("request_context", default=None)
        self.file_workspace = FileWorkspace(root_dir="workspace")
        self.active_file_id: Optional[str] = None
        self.active_files: List[Dict[str, Any]] = []

        reranker = get_reranker(RERANK_STRATEGY, RERANK_MODEL_NAME)
        try:
            self.vector_store = VectorStore(
                model_name=DEFAULT_EMBEDDING_MODEL,
                index_path="vector_db",
                reranker=reranker,
            )
        except TypeError:
            # Backward-compatible fallback for tests/mocks with legacy constructor signature.
            self.vector_store = VectorStore(
                model_name=DEFAULT_EMBEDDING_MODEL,
                index_path="vector_db",
            )
            try:
                if hasattr(self.vector_store, "set_reranker"):
                    self.vector_store.set_reranker(reranker)
            except Exception:
                pass
        self.rag_service = RagService(
            vector_store=self.vector_store,
            data_dir=DATA_DIR,
            fingerprint_path=FINGERPRINT_PATH,
            collection_name=VECTOR_COLLECTION_NAME,
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_backend=EMBEDDING_BACKEND,
            rerank_strategy=RERANK_STRATEGY,
            rerank_model=RERANK_MODEL_NAME,
        )
        self._sync_knowledge_base()
        self.session_facade = AgentSessionFacade(self)
        self.knowledge_base_facade = AgentKnowledgeBaseFacade(self)

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

        self.brain = LLMBrain(self)

        # Initialize Graph Agent
        graph_agent = GraphAgent(self)
        self.runtime = GraphRuntime(graph_agent)

    def _get_session_facade(self) -> AgentSessionFacade:
        facade = getattr(self, "session_facade", None)
        if facade is None:
            facade = AgentSessionFacade(self)
            self.session_facade = facade
        return facade

    def _get_knowledge_base_facade(self) -> AgentKnowledgeBaseFacade:
        facade = getattr(self, "knowledge_base_facade", None)
        if facade is None:
            facade = AgentKnowledgeBaseFacade(self)
            self.knowledge_base_facade = facade
        return facade

    def _full_rebuild_knowledge_base(self, current_fp: Dict[str, Any], reason: str = "force_rebuild") -> Dict[str, Any]:
        return self.rag_service.full_rebuild(current_fp, reason=reason)

    def _incremental_update_knowledge_base(self, current_fp: Dict[str, Any], saved_fp: Dict[str, Any]) -> Dict[str, Any]:
        return self.rag_service.incremental_update(current_fp, saved_fp)

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
        return self._get_knowledge_base_facade().sync_knowledge_base_now()

    def get_last_kb_sync_summary(self) -> Dict[str, Any]:
        return self._get_knowledge_base_facade().get_last_kb_sync_summary()

    def get_knowledge_base_status(self) -> Dict[str, Any]:
        return self._get_knowledge_base_facade().get_knowledge_base_status()

    def get_document_index_stats(self) -> List[Dict[str, Any]]:
        return self._get_knowledge_base_facade().get_document_index_stats()

    def rebuild_knowledge_base_now(self) -> Dict[str, Any]:
        return self._get_knowledge_base_facade().rebuild_knowledge_base_now()

    def get_retrieval_diagnostics(self, limit: int = 20) -> Dict[str, Any]:
        return self._get_knowledge_base_facade().get_retrieval_diagnostics(limit=limit)

    # 会话管理
    def create_new_session(self, title: str = "新对话") -> int:
        return self._get_session_facade().create_new_session(title)

    def delete_session(self, session_id: int):
        return self._get_session_facade().delete_session(session_id)

    def rename_session(self, session_id: int, new_title: str):
        return self._get_session_facade().rename_session(session_id, new_title)

    def switch_session(self, session_id: int):
        return self._get_session_facade().switch_session(session_id)

    # Tool 执行
    def execute_tool_step(self, step: dict) -> str:
        """
        Sync execution of a tool.
        If called from an async context, this should be wrapped in run_in_executor.
        """
        tool_name = step["tool"].upper()
        task = step["task"]
        tool_fn = get_tool_registry().get(tool_name)
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

    async def _fix_terminology_async(self, answer: str, question: str = "") -> str:
        return await fix_terminology_async(answer, question)

    def _fix_terminology(self, answer: str, question: str = "") -> str:
        return fix_terminology(answer, question)

    def _build_fallback_session_title(self, first_question: str) -> str:
        return self._get_session_facade().build_fallback_session_title(first_question)

    async def _auto_rename_session_async(self, session_id: int, first_question: str):
        await self._get_session_facade().auto_rename_session_async(session_id, first_question)

    def get_active_session_id(self) -> Optional[int]:
        return self._get_session_facade().get_active_session_id()

    def get_active_request_context(self) -> Optional[AgentRequestContext]:
        return get_request_context(self._request_context_var)

    async def chat_async(
        self,
        question: str,
        request_context: Optional[AgentRequestContext] = None,
        session_id: Optional[int] = None,
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

        if request_context is not None:
            req_ctx = AgentRequestContext(
                session_id=request_context.session_id,
                file_id=(request_context.file_id or "").strip() or None,
                files=list(request_context.files or []),
                run_mode=str(request_context.run_mode or run_mode or "sync"),
                task_id=(request_context.task_id or "").strip() or None,
                cancel_event=request_context.cancel_event if request_context.cancel_event is not None else cancel_event,
                metadata=dict(request_context.metadata or {}),
            )
        else:
            req_ctx = AgentRequestContext(
                session_id=session_id if session_id is not None else self.session_id,
                file_id=(file_id or "").strip() or None,
                files=list(files or []),
                run_mode=str(run_mode or "sync"),
                task_id=(task_id or "").strip() or None,
                cancel_event=cancel_event,
                metadata={},
            )

        request_session_id = req_ctx.session_id
        token = self._request_session_id_var.set(request_session_id)
        ctx_token = self._request_context_var.set(req_ctx)
        self._active_chat_session_id = request_session_id
        self._active_cancel_event = req_ctx.cancel_event
        # Compatibility fallback for tools that still read these legacy fields.
        self.active_file_id = req_ctx.file_id
        self.active_files = list(req_ctx.files or [])

        try:
            with self._execution_lock:
                if request_session_id:
                    try:
                        if len(self.short_memory) == 0:
                             asyncio.create_task(self._auto_rename_session_async(request_session_id, question))
                    except Exception as e:
                        logger.warning(f"[Session] 异步自动重命名任务创建失败: {e}")

                if self.brain.is_small_talk(question):
                    return await self.brain.answer_small_talk(question)
                if self.brain.is_memory_query(question):
                    return await self.brain.answer_memory_query(question)

                if self.pending_tool_call:
                    judge_prompt = get_prompt_catalog().render("confirmation_judge", question=question)
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
                result = await self.runtime.run_async(
                    question,
                    file_id=req_ctx.file_id or "",
                    files=req_ctx.files,
                    task_id=req_ctx.task_id or "",
                    run_mode=req_ctx.run_mode or "sync",
                    resumed_from=resumed_from,
                )
                return result
        except Exception as e:
            logger.exception("系统运行出错")
            return {"answer": f"系统运行出错: {str(e)}", "confidence": 0.0, "sources": []}
        finally:
            self._request_session_id_var.reset(token)
            self._request_context_var.reset(ctx_token)
            self._current_stream_callback = None
            self._active_chat_session_id = None
            self._active_cancel_event = None
            self.active_file_id = None
            self.active_files = []

    # -----------
    def load_history_to_ui(self, limit: int = 10, session_id: Optional[int] = None) -> str:
        return self._get_session_facade().load_history_to_ui(limit=limit, session_id=session_id)

    def factory_reset(self):
        self.db_manager.clear_conversations()
        try:
            if hasattr(self.vector_store, "close"):
                self.vector_store.close()
        except Exception as e:
            logger.warning(f"[Reset] 关闭向量库句柄失败: {e}")

        # 标记重置
        from core.reset_handler import mark_for_reset
        mark_for_reset()

        self.summary_memory = ""
        self.user_preferences = {}
        self.short_memory.clear()
        self.session_id = None
        logger.warning("🧨 已标记重置，下次启动将彻底清理 vector_db")
