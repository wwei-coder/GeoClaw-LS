from __future__ import annotations

from typing import Any, Dict, List, Optional


class GraphRuntime:
    """Thin runtime facade; delegates to existing GraphAgent."""

    def __init__(self, graph_agent: Any):
        self.graph_agent = graph_agent

    async def run_async(
        self,
        question: str,
        *,
        file_id: str = "",
        files: Optional[List[Dict[str, Any]]] = None,
        task_id: str = "",
        run_mode: str = "sync",
        resumed_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.graph_agent.run_async(
            question=question,
            file_id=file_id,
            files=files,
            task_id=task_id,
            run_mode=run_mode,
            resumed_from=resumed_from,
        )

