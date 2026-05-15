from __future__ import annotations
from contextvars import ContextVar
from .schemas import AgentRequestContext

def get_request_context(context_var: ContextVar[object | None]) -> AgentRequestContext | None:
    req_ctx = context_var.get()
    if isinstance(req_ctx, AgentRequestContext):
        return req_ctx
    return None
