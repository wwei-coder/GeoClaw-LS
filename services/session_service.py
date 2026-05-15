from __future__ import annotations
from typing import Any, Dict
from services.serializers import load_history_messages

class SessionService:
    def _get_session_api(self, agent: Any) -> Any:
        return getattr(agent, "session_facade", None) or agent

    def list_sessions(self, agent: Any) -> Dict[str, Any]:
        sessions = agent.db_manager.get_all_sessions()
        return {"sessions": [{"id": sid, "title": title} for sid, title, _ in sessions]}

    def create_session(self, agent: Any, *, title: str) -> Dict[str, Any]:
        session_api = self._get_session_api(agent)
        sid = session_api.create_new_session(title.strip() or "新对话")
        return {"session_id": sid}

    def switch_session(self, agent: Any, *, session_id: int) -> Dict[str, Any]:
        session_api = self._get_session_api(agent)
        session_api.switch_session(session_id)
        return {
            "session_id": session_id,
            "history_messages": load_history_messages(
                agent,
                session_id=session_id,
                limit=60,
                history_api=session_api,
            ),
        }

    def rename_session(self, agent: Any, *, session_id: int, title: str) -> Dict[str, Any]:
        if not title.strip():
            raise ValueError("标题不能为空")
        session_api = self._get_session_api(agent)
        session_api.rename_session(session_id, title.strip())
        return {"ok": True}

    def delete_session(self, agent: Any, *, session_id: int) -> Dict[str, Any]:
        session_api = self._get_session_api(agent)
        session_api.delete_session(session_id)
        sessions = agent.db_manager.get_all_sessions()
        return {
            "ok": True,
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": session_api.get_active_session_id(),
        }
