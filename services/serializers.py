from __future__ import annotations
from datetime import datetime
import re
from pathlib import Path
from typing import Any, Dict, List

def parse_history_text(history_text: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    lines = (history_text or "").split("\n")
    role = None
    buf = ""
    for line in lines:
        if line.startswith("用户："):
            if role and buf.strip():
                messages.append({"role": role, "text": buf.strip()})
            role = "user"
            buf = line[3:]
        elif line.startswith("助手："):
            if role and buf.strip():
                messages.append({"role": role, "text": buf.strip()})
            role = "assistant"
            buf = line[3:]
        else:
            buf = f"{buf}\n{line}" if buf else line
    if role and buf.strip():
        messages.append({"role": role, "text": buf.strip()})
    return messages

def conversation_rows_to_messages(rows: Any) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for row in rows or []:
        if isinstance(row, dict):
            question = row.get("question", "")
            answer = row.get("answer", "")
        else:
            try:
                question, answer = row[0], row[1]
            except Exception:
                continue
        if str(question or "").strip():
            messages.append({"role": "user", "text": str(question)})
        if str(answer or "").strip():
            messages.append({"role": "assistant", "text": str(answer)})
    return messages

def _parse_db_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None

def _is_same_question_draft(previous: Dict[str, Any], current: Dict[str, Any]) -> bool:
    if str(previous.get("question") or "").strip() != str(current.get("question") or "").strip():
        return False
    prev_ts = _parse_db_timestamp(previous.get("timestamp"))
    curr_ts = _parse_db_timestamp(current.get("timestamp"))
    if prev_ts is None or curr_ts is None:
        return True
    return abs((curr_ts - prev_ts).total_seconds()) <= 180

def conversation_records_to_messages(records: Any) -> List[Dict[str, str]]:
    compacted: List[Dict[str, Any]] = []
    for record in records or []:
        row = dict(record or {}) if isinstance(record, dict) else {}
        if not str(row.get("question") or "").strip():
            continue
        if compacted and _is_same_question_draft(compacted[-1], row):
            compacted[-1] = row
        else:
            compacted.append(row)
    return conversation_rows_to_messages(compacted)

def load_history_messages(
    agent: Any,
    *,
    session_id: Any,
    limit: int = 60,
    history_api: Any = None,
) -> List[Dict[str, str]]:
    db_manager = getattr(agent, "db_manager", None)
    if db_manager is not None and session_id is not None:
        record_getter = getattr(db_manager, "get_conversation_records_by_session", None)
        if callable(record_getter):
            return conversation_records_to_messages(record_getter(session_id, limit))
        getter = getattr(db_manager, "get_conversations_by_session", None)
        if callable(getter):
            return conversation_rows_to_messages(getter(session_id, limit))
    source = history_api or agent
    history_text = source.load_history_to_ui(limit=limit, session_id=session_id) if session_id else ""
    return parse_history_text(history_text)

def serialize_task(task: Any) -> Dict[str, Any]:
    if task is None:
        return {}
    if hasattr(task, "to_dict"):
        payload = task.to_dict()
    elif isinstance(task, dict):
        payload = dict(task)
    else:
        payload = {}
    payload["answer_preview"] = str(payload.get("final_answer", "") or "")[:200]
    return payload

def _extract_confidence_label(text: str) -> str:
    raw = str(text or "")
    matched = re.search(r"【证据支撑强度：([^】]+)】", raw)
    if matched:
        return str(matched.group(1) or "").strip()
    matched = re.search(r"【系统可信度（证据）：([^】]+)】", raw)
    if matched:
        return str(matched.group(1) or "").strip()
    return ""

def _normalize_step_status(value: Any) -> str:
    return str(value or "pending").strip().lower()

def compute_progress(task: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_status = str((task or {}).get("status") or "pending").lower()
    total = len(steps or [])
    completed = 0
    failed = 0
    running = 0
    for s in steps or []:
        status = str((s or {}).get("status") or "pending").lower()
        if status == "success":
            completed += 1
        elif status == "failed":
            failed += 1
        elif status == "running":
            running += 1
    if task_status == "pending":
        percent = 0
    elif task_status == "success":
        percent = 100
    elif total <= 0:
        percent = 0 if task_status in {"pending", "running"} else 100
    else:
        percent = int(max(0.0, min(100.0, ((completed + failed) / float(total)) * 100.0)))
        if task_status == "running":
            percent = max(1, min(99, percent))
    return {
        "total_steps": total,
        "completed_steps": completed,
        "failed_steps": failed,
        "running_steps": running,
        "percent": percent,
    }

def compute_task_actionability(
    task: Dict[str, Any],
    *,
    is_running: bool = False,
    cancel_requested: bool = False,
) -> Dict[str, Any]:
    status = str((task or {}).get("status") or "pending").strip().lower()
    active = bool(is_running or status in {"running", "pending"})
    can_cancel = bool(active and not cancel_requested)
    can_retry = bool((not active) and status in {"failed", "partial"})
    can_resume = bool((not active) and status in {"failed", "partial", "canceled"})
    if cancel_requested:
        status_reason = "已发送取消请求，等待当前步骤安全退出"
        next_action = "wait"
    elif can_cancel:
        status_reason = "任务正在执行，可请求取消"
        next_action = "cancel"
    elif can_retry:
        status_reason = "任务未完全成功，可重新提交执行"
        next_action = "retry"
    elif can_resume:
        status_reason = "任务已中断或取消，可继续执行"
        next_action = "resume"
    elif status == "success":
        status_reason = "任务已成功完成"
        next_action = "none"
    else:
        status_reason = "暂无可用操作"
        next_action = "none"
    return {
        "can_cancel": can_cancel,
        "can_retry": can_retry,
        "can_resume": can_resume,
        "next_action": next_action,
        "status_reason": status_reason,
    }

def build_task_audit(
    task: Dict[str, Any],
    steps: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    task_payload = dict(task or {})
    task_meta = dict(task_payload.get("metadata") or {})
    step_rows = list(steps or [])
    artifact_rows = list(artifacts or [])
    total_steps = len(step_rows)
    success_steps = 0
    failed_steps = 0
    skipped_steps = 0
    running_steps = 0
    remediated_steps = 0
    remediation_actions: List[Dict[str, Any]] = []
    unresolved_outcomes: List[Dict[str, Any]] = []
    execution_events: List[Dict[str, Any]] = []
    replan_happened = False

    for idx, step in enumerate(step_rows):
        row = dict(step or {})
        status = _normalize_step_status(row.get("status"))
        if status == "success":
            success_steps += 1
        elif status == "failed":
            failed_steps += 1
        elif status == "skipped":
            skipped_steps += 1
        elif status == "running":
            running_steps += 1

        metadata = dict(row.get("metadata") or {})
        outcome = dict(metadata.get("outcome_assessment") or {})
        decision = dict(metadata.get("remediation_decision") or {})
        action = dict(decision.get("action") or {})
        action_type = str(action.get("action_type") or "none").strip().lower()
        remediation_attempt = int(metadata.get("remediation_attempt") or 0)
        if remediation_attempt > 0 or action_type != "none":
            remediated_steps += 1

        if action_type and action_type != "none":
            action_row = {
                "step_id": row.get("id"),
                "step_index": idx + 1,
                "tool_name": row.get("tool_name") or row.get("tool") or "",
                "action_type": action_type,
                "allowed": bool(action.get("allowed", False)),
                "reason": str(action.get("reason") or ""),
                "trace_summary": str(decision.get("trace_summary") or action.get("trace_summary") or ""),
                "stop_reason": str(decision.get("stop_reason") or metadata.get("stop_reason") or ""),
                "issue_type": str(outcome.get("issue_type") or "none"),
                "retryable": bool(outcome.get("retryable", False)),
                "retry_of": row.get("retry_of") or metadata.get("retry_of"),
                "remediation_attempt": remediation_attempt,
            }
            remediation_actions.append(action_row)
            if action_type == "replan":
                replan_happened = True
            if action_type in {"ask_user", "degrade_answer"}:
                unresolved_outcomes.append(
                    {
                        "step_id": row.get("id"),
                        "tool_name": action_row["tool_name"],
                        "issue_type": action_row["issue_type"],
                        "suggested_action": str(outcome.get("suggested_action") or ""),
                        "summary": str(outcome.get("summary") or action_row["trace_summary"] or action_row["stop_reason"]),
                        "action_type": action_type,
                        "stop_reason": action_row["stop_reason"],
                    }
                )

        execution_events.append(
            {
                "phase": "executor",
                "type": "step_finished",
                "step_id": row.get("id"),
                "step_index": idx + 1,
                "tool_name": row.get("tool_name") or row.get("tool") or "",
                "status": status,
                "summary": str(
                    outcome.get("trace_summary")
                    or outcome.get("summary")
                    or metadata.get("trace_summary")
                    or row.get("instruction")
                    or ""
                ),
                "error": row.get("error") or "",
                "started_at": row.get("started_at") or "",
                "finished_at": row.get("finished_at") or "",
                "remediation": decision if decision else {},
            }
        )

    # 优先透传持久化 metadata 中的结构化审计结果
    remediation_metrics = dict(task_meta.get("remediation_metrics") or {})
    evidence_assessment = dict(task_meta.get("evidence_quality_assessment") or {})
    metadata_unresolved = task_meta.get("unresolved_outcomes")
    if isinstance(metadata_unresolved, list) and metadata_unresolved:
        unresolved_outcomes = [dict(item or {}) for item in metadata_unresolved]

    metadata_trace = task_meta.get("execution_trace")
    if isinstance(metadata_trace, list) and metadata_trace:
        execution_events = [dict(item or {}) for item in metadata_trace]

    confidence_label = (
        str(task_payload.get("answer_confidence_label") or "").strip()
        or str(task_meta.get("answer_confidence_label") or "").strip()
        or _extract_confidence_label(str(task_payload.get("final_answer") or ""))
    )

    return {
        "overview": {
            "task_status": str(task_payload.get("status") or "pending"),
            "total_steps": total_steps,
            "success_steps": success_steps,
            "failed_steps": failed_steps,
            "skipped_steps": skipped_steps,
            "running_steps": running_steps,
            "remediated_steps": remediated_steps,
            "replan_happened": bool(replan_happened),
            "final_confidence_label": confidence_label,
            "artifact_count": len(artifact_rows),
        },
        "remediation_metrics": remediation_metrics,
        "evidence_quality_assessment": evidence_assessment,
        "unresolved_outcomes": unresolved_outcomes,
        "remediation_actions": remediation_actions,
        "execution_events": execution_events,
    }


def serialize_step(step: Any) -> Dict[str, Any]:
    if step is None:
        return {}
    if hasattr(step, "to_dict"):
        return step.to_dict()
    if isinstance(step, dict):
        return dict(step)
    return {}

def serialize_artifact(artifact: Any) -> Dict[str, Any]:
    if artifact is None:
        return {}
    if hasattr(artifact, "to_dict"):
        payload = artifact.to_dict()
    elif isinstance(artifact, dict):
        payload = dict(artifact)
    else:
        payload = {}
    artifact_id = str(payload.get("id") or "")
    url = str(payload.get("url") or f"/api/artifacts/{artifact_id}" if artifact_id else "")
    payload["url"] = url
    payload["download_url"] = url
    raw_path = str(payload.get("path") or "")
    if ":" in raw_path or raw_path.startswith("/"):
        payload["path"] = Path(raw_path).name
    return payload
