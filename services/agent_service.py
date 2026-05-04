from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
from agent.runtime import AgentRequestContext
from api.context import parse_history_text

class AgentService:
    def bootstrap(self, agent: Any) -> Dict[str, Any]:
        sessions = agent.db_manager.get_all_sessions()
        current_id = agent.get_active_session_id()
        history_text = agent.load_history_to_ui(limit=60, session_id=current_id) if current_id else ""
        return {
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": current_id,
            "history_messages": parse_history_text(history_text),
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
        req_ctx = AgentRequestContext(
            session_id=session_id if session_id is not None else agent.get_active_session_id(),
            file_id=(file_id or "").strip() or None,
            files=list(files or []),
            run_mode="sync",
            metadata={"entrypoint": "api.chat"},
        )
        result = asyncio.run(
            agent.chat_async(
                question,
                request_context=req_ctx,
            )
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
