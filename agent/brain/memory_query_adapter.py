from __future__ import annotations
from typing import Any, Dict
from capabilities.memory.query import MemoryQueryService

class MemoryQueryAdapter:
    """Minimal async-compatible wrapper for LLMBrain memory query defaults."""

    def __init__(self, *, agent_core: Any):
        self._service = MemoryQueryService(agent_core=agent_core)

    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = str((inputs or {}).get("question") or "")
        return self._service.handle(question)
