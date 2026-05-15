from __future__ import annotations
from typing import Any, Dict
from .synthesis_factory import get_synthesis_service

class SynthesisAdapter:
    """Minimal async-compatible wrapper for LLMBrain synthesis defaults."""

    def __init__(self, *, agent_core: Any):
        self.agent_core = agent_core

    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        service = get_synthesis_service(self.agent_core)
        payload = dict(inputs or {})
        kwargs = {
            "question": payload["question"],
            "step_results": list(payload.get("step_results", []) or []),
            "kb_chunks": list(payload.get("kb_chunks", []) or []),
            "sources": list(payload.get("sources", []) or []),
            "stream_callback": payload.get("stream_callback"),
            "canceled": bool(payload.get("canceled", False)),
        }
        if "persist_memory" in payload:
            kwargs["persist_memory"] = bool(payload.get("persist_memory", True))
        return await service.synthesize_async(**kwargs)
