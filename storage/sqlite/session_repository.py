from __future__ import annotations

from typing import Any, List

from storage.schemas import StoredSession


class SessionRepository:
    """Thin adapter for session persistence backed by DatabaseManager."""

    def __init__(self, db_manager: Any):
        self.db_manager = db_manager

    def list_sessions(self) -> List[StoredSession]:
        rows = self.db_manager.get_all_sessions() or []
        items: List[StoredSession] = []
        for row in rows:
            sid = int(row[0]) if len(row) > 0 else 0
            title = str(row[1]) if len(row) > 1 else ""
            created_at = str(row[2]) if len(row) > 2 else ""
            updated_at = str(row[3]) if len(row) > 3 else ""
            items.append(StoredSession(session_id=sid, title=title, created_at=created_at, updated_at=updated_at))
        return items

    def create_session(self, title: str = "新对话") -> int:
        return int(self.db_manager.create_session(title))

    def rename_session(self, session_id: int, title: str) -> None:
        self.db_manager.update_session_title(int(session_id), title)

    def delete_session(self, session_id: int) -> None:
        self.db_manager.delete_session(int(session_id))

