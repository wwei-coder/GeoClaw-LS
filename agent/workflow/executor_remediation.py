from __future__ import annotations

from typing import Any, Dict


def build_retry_task_instruction(action: Dict[str, Any], instruction: str) -> str:
    return str(action.get("retry_task") or instruction).strip() or instruction


def build_retry_trace_text(*, tool: str, trace_summary: str) -> str:
    return trace_summary or f"{tool} remediation retry scheduled"


def build_replan_feedback(*, idx: int, tool: str, trace_summary: str) -> str:
    return trace_summary or f"步骤 {idx+1} [{tool}] 触发受控重规划。"


def build_remediation_stream_text(*, action: Dict[str, Any], trace_summary: str) -> str:
    return action.get("trace_summary") or trace_summary


def build_unresolved_outcome_payload(
    *,
    tool: str,
    issue_type: str,
    outcome: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "tool_name": tool,
        "issue_type": issue_type,
        "summary": outcome.get("summary", ""),
        "suggested_action": action.get("trace_summary") or outcome.get("suggested_action", ""),
    }


def build_ask_user_or_degrade_result_text(
    *,
    outcome_feedback: str,
    trace_summary: str,
    fallback_result_text: str,
) -> str:
    return outcome_feedback or trace_summary or fallback_result_text
