from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, List, Optional
from agent.runtime import AgentRequestContext
from services.serializers import load_history_messages
from utils.logger import logger

class AgentService:
    def bootstrap(self, agent: Any) -> Dict[str, Any]:
        sessions = agent.db_manager.get_all_sessions()
        current_id = agent.get_active_session_id()
        return {
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": current_id,
            "history_messages": load_history_messages(agent, session_id=current_id, limit=60),
            "status": "就绪",
        }

    def chat(
        self,
        agent: Any,
        *,
        question: str,
        session_id: Optional[int] = None,
        file_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        req_ctx = AgentRequestContext(
            session_id=session_id if session_id is not None else agent.get_active_session_id(),
            file_id=(file_id or "").strip() or None,
            files=list(files or []),
            run_mode="sync",
            metadata={"entrypoint": "api.chat"},
        )
        logger.info(
            "[Chat] request start session_id={} file_id={} question_len={}",
            req_ctx.session_id,
            req_ctx.file_id or "",
            len(question or ""),
        )
        result = asyncio.run(
            agent.chat_async(
                question,
                request_context=req_ctx,
            )
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "[Chat] request end session_id={} task_id={} answer_len={} duration_ms={}",
            req_ctx.session_id,
            result.get("task_id", ""),
            len(result.get("answer", "") or ""),
            duration_ms,
        )
        return {
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "trace": result.get("trace", ""),
            "session_id": req_ctx.session_id if req_ctx.session_id is not None else agent.get_active_session_id(),
            "task_id": result.get("task_id", ""),
            "execution_trace": result.get("execution_trace", []),
            "steps": result.get("steps", []),
            "artifacts": result.get("artifacts", []),
        }
