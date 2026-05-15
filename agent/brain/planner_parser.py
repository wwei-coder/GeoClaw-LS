from __future__ import annotations
import json
import re
from tools.registry import get_enabled_tool_names
from utils.logger import logger

DATA_TOOLS = {"DATA_PROFILE", "FILE_INSPECTOR"}
HARD_BLOCKED_TOOLS = {"KG_RAG", "AUTOML"}
FORBIDDEN_TRACE_KEYS = {"chain_of_thought", "full_reasoning", "hidden_thoughts", "详细思考过程"}
ALLOWED_TRACE_TYPES = {
    "intent",
    "tool_reason",
    "evidence_check",
    "expected_output",
    "fallback",
    "review_summary",
}

def _has_file_signal(text: str) -> bool:
    q = (text or "").lower()
    keywords = [
        "file_id",
        "上传",
        "已上传",
        "这个文件",
        "该文件",
        "数据文件",
        "csv",
        "excel",
        "xlsx",
        "xls",
        "json",
        "txt",
        "表格",
    ]
    if any(k in q for k in keywords):
        return True
    return bool(re.search(r"\bfile[_-]?id\b", q, flags=re.IGNORECASE))

def get_planner_allowed_tools() -> set[str]:
    return {str(name).upper() for name in get_enabled_tool_names()}

def process_planner_response(raw_response: str, question: str) -> dict:
    """Process and sanitize LLM response for planning."""
    raw = raw_response.strip()

    if "```json" in raw:
        raw = raw.split("```json")[-1]
    if "```" in raw:
        raw = raw.split("```")[0]

    text = raw.strip()
    sanitized = "".join(ch for ch in text if (ord(ch) >= 32) or ch in "\n\r\t")
    sanitized = sanitized.replace("\u2028", "").replace("\u2029", "").strip()

    plan = {}
    try:
        plan = json.loads(sanitized)
    except Exception as e:
        logger.warning(f"[Planner] 首次 JSON 解析失败: {e}")
        start = sanitized.find("{")
        end = sanitized.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                plan = json.loads(sanitized[start:end + 1])
            except Exception as e:
                logger.warning(f"[Planner] 二次 JSON 解析失败: {e}")

    if not plan:
        return {
            "intent": "mixed",
            "need_kb": False,
            "need_evidence": False,
            "risk_level": "low",
            "reasoning_trace": [{"type": "review_summary", "summary": "Planner 输出解析失败，降级为 LLM 单步。"}],
            "steps": [{"task": question, "tool": "LLM"}],
            "answer_requirements": [],
        }

    intent = str(plan.get("intent") or "mixed").strip() or "mixed"
    need_kb = bool(plan.get("need_kb", False))
    need_evidence = bool(plan.get("need_evidence", need_kb))
    risk_level = str(plan.get("risk_level") or "low").strip().lower() or "low"
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    if "need_kb" not in plan:
        need_kb = False

    steps = plan.get("steps")
    if not isinstance(steps, list):
        steps = []

    reasoning_trace = []
    raw_trace = plan.get("reasoning_trace", [])
    if isinstance(raw_trace, list):
        for item in raw_trace:
            if not isinstance(item, dict):
                continue
            if any(k in item for k in FORBIDDEN_TRACE_KEYS):
                continue
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            if any(flag in summary for flag in ("完整思考过程", "逐字链式思考", "chain of thought", "hidden thoughts")):
                summary = "已省略详细内部推理，仅保留结构化摘要。"
            trace_type = str(item.get("type") or "review_summary").strip()
            if trace_type not in ALLOWED_TRACE_TYPES:
                trace_type = "review_summary"
            reasoning_trace.append({"type": trace_type, "summary": summary[:120]})

    answer_requirements = []
    raw_answer_requirements = plan.get("answer_requirements", [])
    if isinstance(raw_answer_requirements, list):
        for item in raw_answer_requirements:
            text = str(item).strip()
            if text:
                answer_requirements.append(text[:80])

    cleaned = []
    allowed_tools = get_planner_allowed_tools()
    file_signal = _has_file_signal(question)
    for s in steps:
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool", "LLM")).upper().strip()
        task = str(s.get("task", "")).strip()

        if "CALC" in tool or "MATH" in tool:
            tool = "CALCULATOR"
        elif "MEM" in tool or "HIST" in tool:
            tool = "MEMORY"
        elif "RAG" in tool or "SEARCH" in tool or "KB" in tool:
            tool = "RAG"
        elif "DISC" in tool or "ANALY" in tool:
            tool = "DISCOVERY"

        if not task or "要做什么" in task or "给工具的输入" in task:
            task = question

        original_tool = tool
        if tool in HARD_BLOCKED_TOOLS:
            tool = "RAG" if need_kb else "LLM"
            reasoning_trace.append(
                {
                    "type": "tool_reason",
                    "summary": f"检测到禁用工具 {original_tool}，已安全降级为 {tool}。",
                }
            )
        elif tool not in allowed_tools:
            tool = "LLM"
            reasoning_trace.append(
                {
                    "type": "tool_reason",
                    "summary": f"检测到未启用工具 {original_tool}，已降级为 LLM。",
                }
            )
        if tool in DATA_TOOLS and not file_signal:
            logger.info("[Planner] 数据工具缺少文件意图信号，降级为 LLM")
            reasoning_trace.append(
                {
                    "type": "evidence_check",
                    "summary": f"{tool} 缺少文件意图信号，已降级为 LLM。",
                }
            )
            tool = "LLM"
        step_payload = {"tool": tool, "task": task}
        reason = str(s.get("reason") or "").strip()
        expected_output = str(s.get("expected_output") or "").strip()
        fallback = str(s.get("fallback") or "").strip()
        if reason:
            step_payload["reason"] = reason
        if expected_output:
            step_payload["expected_output"] = expected_output
        if fallback:
            step_payload["fallback"] = fallback
        cleaned.append(step_payload)

    if not cleaned:
        cleaned = [{"task": question, "tool": "LLM"}]

    return {
        "intent": intent,
        "need_kb": need_kb,
        "need_evidence": need_evidence,
        "risk_level": risk_level,
        "reasoning_trace": reasoning_trace,
        "steps": cleaned,
        "answer_requirements": answer_requirements,
    }
