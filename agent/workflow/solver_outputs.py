from __future__ import annotations
from typing import Any, Dict, List

def build_confidence_prefixed_answer(
    *,
    synthesized_answer: str,
    confidence_label: str,
    unresolved_outcomes: List[Dict[str, Any]],
) -> str:
    final_answer = f"【证据支撑强度：{confidence_label}】\n{synthesized_answer}"
    if confidence_label == "低":
        final_answer += "\n\n【需补充信息】当前证据支撑较弱，建议补充更具体的问题条件、关键词或权威资料来源。"
    unresolved = list(unresolved_outcomes or [])
    if unresolved:
        lines = []
        for item in unresolved[:3]:
            tool_name = str(item.get("tool_name") or "工具")
            issue = str(item.get("issue_type") or "unknown")
            suggestion = str(item.get("suggested_action") or "").strip()
            summary = str(item.get("summary") or "").strip()
            line = f"- {tool_name}：{issue}"
            if summary:
                line += f"，{summary}"
            if suggestion:
                line += f"。建议：{suggestion}"
            lines.append(line)
        final_answer += "\n\n【执行补救记录】\n" + "\n".join(lines)
    return final_answer

def append_evidence_summary_if_needed(final_answer: str, evidence_assessment: Dict[str, Any]) -> str:
    if (evidence_assessment or {}).get("issue_type") not in {"none", ""}:
        return final_answer + "\n\n【证据校验摘要】" + f"{(evidence_assessment or {}).get('summary', '')}"
    return final_answer


def build_task_metadata_update(
    *,
    remediation_metrics: Dict[str, Any],
    evidence_assessment: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "remediation_metrics": remediation_metrics,
        "evidence_quality_assessment": evidence_assessment,
    }

def build_solver_return_payload(
    *,
    task: Dict[str, Any],
    task_id: str,
    final_answer: str,
    confidence_score: float,
    confidence_label: str,
    remediation_metrics: Dict[str, Any],
    evidence_assessment: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "task": task,
        "task_id": task_id,
        "final_answer": final_answer,
        "answer_confidence_score": confidence_score,
        "answer_confidence_label": confidence_label,
        "remediation_metrics": remediation_metrics,
        "evidence_quality_assessment": evidence_assessment,
        "execution_trace": [
            {
                "phase": "solver",
                "type": "evidence_check",
                "summary": (
                    f"证据评估：{evidence_assessment.get('issue_type', 'none')}，"
                    f"coverage={evidence_assessment.get('evidence_coverage', 0)}。"
                ),
            }
        ],
    }
