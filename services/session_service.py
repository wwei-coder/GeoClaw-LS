from __future__ import annotations

from typing import Any, Dict

from api.context import parse_history_text


class SessionService:
    def list_sessions(self, agent: Any) -> Dict[str, Any]:
        sessions = agent.db_manager.get_all_sessions()
        return {"sessions": [{"id": sid, "title": title} for sid, title, _ in sessions]}

    def create_session(self, agent: Any, *, title: str) -> Dict[str, Any]:
        sid = agent.create_new_session(title.strip() or "新对话")
        return {"session_id": sid}

    def switch_session(self, agent: Any, *, session_id: int) -> Dict[str, Any]:
        agent.switch_session(session_id)
        history = agent.load_history_to_ui(limit=60, session_id=session_id)
        return {"session_id": session_id, "history_messages": parse_history_text(history)}

    def rename_session(self, agent: Any, *, session_id: int, title: str) -> Dict[str, Any]:
        if not title.strip():
            raise ValueError("标题不能为空")
        agent.rename_session(session_id, title.strip())
        return {"ok": True}

    def delete_session(self, agent: Any, *, session_id: int) -> Dict[str, Any]:
        agent.delete_session(session_id)
        sessions = agent.db_manager.get_all_sessions()
        return {
            "ok": True,
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": agent.get_active_session_id(),
        }
