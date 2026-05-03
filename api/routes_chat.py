import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from api.context import ChatRequest, STATIC_DIR, bridge, parse_history_text

router = APIRouter()

@router.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))

@router.get("/api/bootstrap")
def bootstrap():
    def _inner(agent: Any):
        sessions = agent.db_manager.get_all_sessions()
        current_id = agent.get_active_session_id()
        history_text = agent.load_history_to_ui(limit=60, session_id=current_id) if current_id else ""
        return {
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": current_id,
            "history_messages": parse_history_text(history_text),
            "status": "就绪",
        }

    return bridge.with_agent(_inner)

@router.post("/api/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    def _inner(agent: Any):
        if req.session_id:
            agent.switch_session(req.session_id)
        result = asyncio.run(
            agent.chat_async(
                question,
                file_id=(req.file_id or "").strip() or None,
                files=req.files or [],
            )
        )
        return {
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "trace": result.get("trace", ""),
            "session_id": agent.get_active_session_id(),
            "task_id": result.get("task_id", ""),
            "execution_trace": result.get("execution_trace", []),
            "steps": result.get("steps", []),
            "artifacts": result.get("artifacts", []),
        }

    return bridge.with_agent(_inner)
