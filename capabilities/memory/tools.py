from __future__ import annotations

from typing import Any

from .conversation import collect_agent_memory, render_memory_context


def build_memory_tool_content(agent: Any, *, recent_limit: int = 6) -> str:
    memory = collect_agent_memory(agent, recent_limit=recent_limit)
    return render_memory_context(memory)
