from typing import Any

from fastapi import APIRouter, HTTPException

from api.context import CreateSessionRequest, RenameSessionRequest, bridge
from services.session_service import SessionService

router = APIRouter()
service = SessionService()


@router.get("/api/sessions")
def list_sessions():
    def _inner(agent: Any):
        return service.list_sessions(agent)

    return bridge.with_agent(_inner)


@router.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    def _inner(agent: Any):
        return service.create_session(agent, title=req.title)

    return bridge.with_agent(_inner)


@router.post("/api/sessions/{session_id}/switch")
def switch_session(session_id: int):
    def _inner(agent: Any):
        return service.switch_session(agent, session_id=session_id)

    return bridge.with_agent(_inner)


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: int, req: RenameSessionRequest):
    def _inner(agent: Any):
        return service.rename_session(agent, session_id=session_id, title=req.title)

    try:
        return bridge.with_agent(_inner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    def _inner(agent: Any):
        return service.delete_session(agent, session_id=session_id)

    return bridge.with_agent(_inner)
