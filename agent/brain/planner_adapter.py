from __future__ import annotations
from typing import Any, Dict
from .planning import PlannerService

class PlannerAdapter:
    """Minimal async-compatible wrapper for LLMBrain planner defaults."""

    def __init__(self):
        self._service = PlannerService()

    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = str((inputs or {}).get("question") or "")
        return await self._service.handle_async(question)
