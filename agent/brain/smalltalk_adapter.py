from __future__ import annotations
from typing import Any, Dict
from .smalltalk import SmallTalkService

class SmallTalkAdapter:
    """Minimal async-compatible wrapper for LLMBrain small talk defaults."""

    def __init__(self, *, agent_core: Any):
        self._service = SmallTalkService(agent_core=agent_core)

    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = str((inputs or {}).get("question") or "")
        return self._service.handle(question)
