from typing import Any

from fastapi import APIRouter, HTTPException

from api.context import CreateSessionRequest, RenameSessionRequest, bridge, parse_history_text

router = APIRouter()


@router.get("/api/sessions")
def list_sessions():
    def _inner(agent: Any):
        sessions = agent.db_manager.get_all_sessions()
        return {"sessions": [{"id": sid, "title": title} for sid, title, _ in sessions]}

    return bridge.with_agent(_inner)


@router.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    def _inner(agent: Any):
        sid = agent.create_new_session(req.title.strip() or "新对话")
        return {"session_id": sid}

    return bridge.with_agent(_inner)


@router.post("/api/sessions/{session_id}/switch")
def switch_session(session_id: int):
    def _inner(agent: Any):
        agent.switch_session(session_id)
        history = agent.load_history_to_ui(limit=60, session_id=session_id)
        return {"session_id": session_id, "history_messages": parse_history_text(history)}

    return bridge.with_agent(_inner)


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: int, req: RenameSessionRequest):
    def _inner(agent: Any):
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        agent.rename_session(session_id, title)
        return {"ok": True}

    return bridge.with_agent(_inner)


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    def _inner(agent: Any):
        agent.delete_session(session_id)
        sessions = agent.db_manager.get_all_sessions()
        return {
            "ok": True,
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": agent.get_active_session_id(),
        }

    return bridge.with_agent(_inner)
