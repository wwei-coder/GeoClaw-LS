from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from api.context import ChatRequest, STATIC_DIR, bridge
from services.agent_service import AgentService

router = APIRouter()
service = AgentService()

@router.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))

@router.get("/api/bootstrap")
def bootstrap():
    def _inner(agent: Any):
        return service.bootstrap(agent)

    return bridge.with_agent(_inner)

@router.post("/api/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    def _inner(agent: Any):
        return service.chat(
            agent,
            question=question,
            session_id=req.session_id,
            file_id=req.file_id,
            files=req.files or [],
        )

    return bridge.with_agent(_inner)
