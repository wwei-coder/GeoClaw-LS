from __future__ import annotations

from typing import Any, Dict, Optional

def normalize_remediation_stats(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = dict(raw or {})
    return {
        "tool_failure_streak": dict(data.get("tool_failure_streak") or {}),
        "issue_counts": dict(data.get("issue_counts") or {}),
        "step_remediation_counts": dict(data.get("step_remediation_counts") or {}),
        "llm_empty_retry_count": int(data.get("llm_empty_retry_count", 0) or 0),
    }

def advance_remediation_stats(stats: Dict[str, Any], tool: str, issue_type: str) -> Dict[str, Any]:
    next_stats = normalize_remediation_stats(stats)
    tool_key = str(tool or "").upper().strip() or "UNKNOWN"
    issue = str(issue_type or "unknown")
    tool_streak = dict(next_stats.get("tool_failure_streak") or {})
    if issue == "none":
        tool_streak[tool_key] = 0
    else:
        tool_streak[tool_key] = int(tool_streak.get(tool_key, 0) or 0) + 1
        issue_counts = dict(next_stats.get("issue_counts") or {})
        issue_counts[issue] = int(issue_counts.get(issue, 0) or 0) + 1
        next_stats["issue_counts"] = issue_counts
    next_stats["tool_failure_streak"] = tool_streak
    return next_stats


def format_outcome_feedback(outcome: Dict[str, Any]) -> str:
    summary = str(outcome.get("summary") or "").strip()
    action = str(outcome.get("suggested_action") or "").strip()
    if summary and action:
        return f"{summary} 建议：{action}"
    return summary or action
