from __future__ import annotations

from typing import Any, Dict, Optional


def collect_agent_memory(agent: Any, *, recent_limit: int = 6) -> Dict[str, str]:
    summary = getattr(agent, "summary_memory", "") or ""
    try:
        sid = agent.get_active_session_id() if hasattr(agent, "get_active_session_id") else getattr(agent, "session_id", None)
        recent = agent.load_history_to_ui(limit=recent_limit, session_id=sid)
    except Exception:
        recent = ""
    short = "\n".join(getattr(agent, "short_memory", []) or [])
    return {"summary": summary, "recent": recent, "short": short}


def render_memory_context(memory: Dict[str, str], labels: Optional[Dict[str, str]] = None) -> str:
    labels = labels or {"summary": "摘要记忆", "recent": "最近对话", "short": "短期记忆"}
    parts = []
    for key in ("summary", "recent", "short"):
        value = (memory.get(key) or "").strip()
        if value:
            parts.append(f"【{labels.get(key, key)}】\n{value}")
    return "\n\n".join(parts)
