from __future__ import annotations
import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from core.config import RAG_MAX_CHUNK_LENGTH, GRAPH_REPLAN_LOW_QUALITY_THRESHOLD
from .state import AgentStep, AgentTask, Artifact
from tools.base import ToolInput, ToolResult
from tools.registry import execute_tool

ToolCallable = Callable[[str, Any], str]
OUTCOME_ISSUES = {
    "none",
    "empty_result",
    "low_evidence",
    "missing_file",
    "invalid_input",
    "tool_error",
    "unsupported",
    "unknown",
}
REMEDIATION_ACTIONS = {
    "none",
    "retry_same_tool",
    "switch_tool",
    "ask_user",
    "degrade_answer",
    "replan",
}

def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

@dataclass
class ToolOutcomeAssessment:
    tool_name: str
    success: bool
    usable: bool
    issue_type: str = "none"
    summary: str = ""
    suggested_action: str = ""
    retryable: bool = False
    fallback_tool: str = ""
    trace_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": bool(self.success),
            "usable": bool(self.usable),
            "issue_type": self.issue_type if self.issue_type in OUTCOME_ISSUES else "unknown",
            "summary": self.summary,
            "suggested_action": self.suggested_action,
            "retryable": bool(self.retryable),
            "fallback_tool": self.fallback_tool,
            "trace_summary": self.trace_summary,
        }

@dataclass
class RemediationAction:
    action_type: str = "none"
    reason: str = ""
    tool_name: str = ""
    retry_tool: str = ""
    retry_task: str = ""
    max_attempts: int = 0
    current_attempt: int = 0
    allowed: bool = False
    trace_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        action_type = self.action_type if self.action_type in REMEDIATION_ACTIONS else "none"
        return {
            "action_type": action_type,
            "reason": self.reason,
            "tool_name": self.tool_name,
            "retry_tool": self.retry_tool,
            "retry_task": self.retry_task,
            "max_attempts": int(self.max_attempts or 0),
            "current_attempt": int(self.current_attempt or 0),
            "allowed": bool(self.allowed),
            "trace_summary": self.trace_summary,
        }

@dataclass
class RemediationDecision:
    should_remediate: bool = False
    action: RemediationAction = field(default_factory=RemediationAction)
    stop_reason: str = ""
    trace_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_remediate": bool(self.should_remediate),
            "action": self.action.to_dict(),
            "stop_reason": self.stop_reason,
            "trace_summary": self.trace_summary,
        }

@dataclass
class RemediationMetrics:
    total_steps: int = 0
    remediated_steps: int = 0
    remediation_triggered: int = 0
    remediation_succeeded: int = 0
    remediation_failed: int = 0
    remediation_fused: int = 0
    degraded_answers: int = 0
    issue_counts: Dict[str, int] = field(default_factory=dict)
    tool_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_steps": int(self.total_steps or 0),
            "remediated_steps": int(self.remediated_steps or 0),
            "remediation_triggered": int(self.remediation_triggered or 0),
            "remediation_succeeded": int(self.remediation_succeeded or 0),
            "remediation_failed": int(self.remediation_failed or 0),
            "remediation_fused": int(self.remediation_fused or 0),
            "degraded_answers": int(self.degraded_answers or 0),
            "issue_counts": dict(self.issue_counts or {}),
            "tool_counts": dict(self.tool_counts or {}),
        }

@dataclass
class EvidenceQualityAssessment:
    need_evidence: bool = False
    has_sources: bool = False
    source_count: int = 0
    retrieved_chunk_count: int = 0
    evidence_coverage: float = 0.0
    citation_present: bool = False
    separates_supported_and_inferred: bool = False
    issue_type: str = "none"
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "need_evidence": bool(self.need_evidence),
            "has_sources": bool(self.has_sources),
            "source_count": int(self.source_count or 0),
            "retrieved_chunk_count": int(self.retrieved_chunk_count or 0),
            "evidence_coverage": round(float(self.evidence_coverage or 0.0), 3),
            "citation_present": bool(self.citation_present),
            "separates_supported_and_inferred": bool(self.separates_supported_and_inferred),
            "issue_type": self.issue_type,
            "summary": self.summary,
        }

def _extract_simple_expression(text: str) -> str:
    if not text:
        return ""
    pattern = r"[0-9\.\(\)\+\-\*\/\s]{3,}"
    candidates = [c.strip() for c in re.findall(pattern, text) if c and c.strip()]
    for expr in candidates:
        if any(op in expr for op in "+-*/") and not re.search(r"[A-Za-z_]", expr):
            return expr
    return ""

def build_remediation_decision(
    step: AgentStep,
    tool_result: ToolResult,
    outcome_assessment: Dict[str, Any],
    state: Dict[str, Any],
) -> RemediationDecision:
    tool = str(step.tool_name or "").upper().strip() or "UNKNOWN"
    issue = str(outcome_assessment.get("issue_type") or "none")
    retryable = bool(outcome_assessment.get("retryable", False))
    summary = str(outcome_assessment.get("summary") or "").strip()
    remediation_count = int(state.get("remediation_count", 0) or 0)
    stats = dict(state.get("remediation_stats") or {})
    tool_fail_streak = int(dict(stats.get("tool_failure_streak") or {}).get(tool, 0) or 0)
    issue_repeat = int(dict(stats.get("issue_counts") or {}).get(issue, 0) or 0)
    step_counts = dict(stats.get("step_remediation_counts") or {})
    step_attempt = int(step_counts.get(step.id, 0) or 0)
    llm_empty_retry_count = int(stats.get("llm_empty_retry_count", 0) or 0)

    if issue == "none":
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="none", tool_name=tool),
            trace_summary=f"{tool} 输出可用，无需补救。",
        )

    if remediation_count >= 2:
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="已达到任务级补救上限",
            trace_summary="已达到补救上限，转入降级回答。",
        )
    if step_attempt >= 1:
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="当前步骤已补救一次",
            trace_summary="当前步骤补救次数已达上限，转入降级回答。",
        )
    if tool_fail_streak >= 2:
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="同一工具连续失败触发熔断",
            trace_summary="同一工具连续失败达到阈值，触发熔断。",
        )
    if issue_repeat >= 3:
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="同一问题类型重复触发熔断",
            trace_summary="同一问题类型重复出现，触发熔断。",
        )

    if tool == "RAG" and issue == "low_evidence":
        action_type = "replan" if int(state.get("execution_replan_count", 0) or 0) >= 1 else "retry_same_tool"
        if action_type == "retry_same_tool":
            retry_task = f"{step.instruction}\n请扩展关键词、同义词、专业术语后重检索。"
            action = RemediationAction(
                action_type="retry_same_tool",
                reason=summary or "RAG 证据不足",
                tool_name=tool,
                retry_tool="RAG",
                retry_task=retry_task,
                max_attempts=1,
                current_attempt=step_attempt + 1,
                allowed=True,
                trace_summary="RAG 证据不足，自动补救：扩展关键词后重试一次。",
            )
            return RemediationDecision(True, action, "", action.trace_summary)
        action = RemediationAction(
            action_type="replan",
            reason=summary or "RAG 证据不足",
            tool_name=tool,
            max_attempts=1,
            current_attempt=step_attempt + 1,
            allowed=True,
            trace_summary="RAG 证据不足，触发受控重规划。",
        )
        return RemediationDecision(True, action, "", action.trace_summary)

    if tool == "DATA_PROFILE" and issue == "missing_file":
        action = RemediationAction(
            action_type="ask_user",
            reason=summary or "缺少 file_id",
            tool_name=tool,
            max_attempts=0,
            current_attempt=step_attempt,
            allowed=False,
            trace_summary="数据工具缺少文件上下文，请用户上传或选择文件。",
        )
        return RemediationDecision(True, action, "", action.trace_summary)

    if tool == "FILE_INSPECTOR" and issue == "missing_file":
        action = RemediationAction(
            action_type="ask_user",
            reason=summary or "缺少 file_id",
            tool_name=tool,
            max_attempts=0,
            current_attempt=step_attempt,
            allowed=False,
            trace_summary="文件检查缺少 file_id，请用户提供文件上下文。",
        )
        return RemediationDecision(True, action, "", action.trace_summary)

    if tool == "CALCULATOR" and issue == "invalid_input":
        expr = _extract_simple_expression(step.instruction)
        if expr:
            action = RemediationAction(
                action_type="retry_same_tool",
                reason=summary or "输入不规范",
                tool_name=tool,
                retry_tool="CALCULATOR",
                retry_task=expr,
                max_attempts=1,
                current_attempt=step_attempt + 1,
                allowed=True,
                trace_summary="计算输入不规范，自动提取表达式后重试一次。",
            )
            return RemediationDecision(True, action, "", action.trace_summary)
        action = RemediationAction(
            action_type="ask_user",
            reason=summary or "无法提取可计算表达式",
            tool_name=tool,
            max_attempts=0,
            current_attempt=step_attempt,
            allowed=False,
            trace_summary="计算表达式不明确，请用户补充可计算表达式。",
        )
        return RemediationDecision(True, action, "", action.trace_summary)

    if tool == "LLM" and issue == "empty_result":
        if llm_empty_retry_count < 1:
            action = RemediationAction(
                action_type="retry_same_tool",
                reason=summary or "LLM 输出为空",
                tool_name=tool,
                retry_tool="LLM",
                retry_task=step.instruction,
                max_attempts=1,
                current_attempt=step_attempt + 1,
                allowed=True,
                trace_summary="LLM 输出为空，自动重试一次。",
            )
            return RemediationDecision(True, action, "", action.trace_summary)
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="LLM 空输出重试已达上限",
            trace_summary="LLM 空输出补救已达上限，转入降级回答。",
        )

    if issue == "tool_error":
        if retryable:
            action = RemediationAction(
                action_type="retry_same_tool",
                reason=summary or "工具执行错误",
                tool_name=tool,
                retry_tool=tool,
                retry_task=step.instruction,
                max_attempts=1,
                current_attempt=step_attempt + 1,
                allowed=True,
                trace_summary=f"{tool} 执行错误，自动重试一次。",
            )
            return RemediationDecision(True, action, "", action.trace_summary)
        return RemediationDecision(
            should_remediate=False,
            action=RemediationAction(action_type="degrade_answer", tool_name=tool),
            stop_reason="工具错误且不允许重试",
            trace_summary=f"{tool} 执行错误，不自动重试，转入降级回答。",
        )

    return RemediationDecision(
        should_remediate=False,
        action=RemediationAction(action_type="degrade_answer", tool_name=tool),
        stop_reason=f"未命中自动补救规则：{issue}",
        trace_summary=f"{tool} 未命中自动补救规则，转入降级回答。",
    )

def collect_remediation_metrics(
    *,
    task: Optional[Any] = None,
    state: Optional[Dict[str, Any]] = None,
    execution_trace: Optional[List[Dict[str, Any]]] = None,
    steps: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    task_payload = task.to_dict() if hasattr(task, "to_dict") else dict(task or {})
    state_payload = dict(state or {})
    raw_steps = steps or task_payload.get("steps") or state_payload.get("steps") or []
    raw_trace = execution_trace or state_payload.get("execution_trace") or []
    metrics = RemediationMetrics()

    for item in raw_steps:
        if hasattr(item, "to_dict"):
            step = item.to_dict()
        else:
            step = dict(item or {})
        metrics.total_steps += 1
        tool_name = str(step.get("tool_name") or step.get("tool") or "UNKNOWN").upper()
        metrics.tool_counts[tool_name] = int(metrics.tool_counts.get(tool_name, 0) or 0) + 1

        metadata = dict(step.get("metadata") or {})
        outcome = dict(metadata.get("outcome_assessment") or {})
        issue = str(outcome.get("issue_type") or "none")
        if issue and issue != "none":
            metrics.issue_counts[issue] = int(metrics.issue_counts.get(issue, 0) or 0) + 1

        decision = dict(metadata.get("remediation_decision") or {})
        action = dict(decision.get("action") or {})
        action_type = str(action.get("action_type") or "none")
        should_remediate = bool(decision.get("should_remediate")) or action_type != "none"
        rem_attempt = int(metadata.get("remediation_attempt", 0) or 0)
        status = str(step.get("status") or "").lower()
        stop_reason = str(metadata.get("stop_reason") or decision.get("stop_reason") or "")

        if should_remediate:
            metrics.remediation_triggered += 1
        if rem_attempt > 0:
            metrics.remediated_steps += 1
            if status == "success":
                metrics.remediation_succeeded += 1
        if action_type == "degrade_answer":
            metrics.degraded_answers += 1
        if ("熔断" in stop_reason) or ("上限" in stop_reason):
            metrics.remediation_fused += 1

    for item in raw_trace:
        trace = dict(item or {})
        remediation = dict(trace.get("remediation") or {})
        action = dict(remediation.get("action") or {})
        action_type = str(action.get("action_type") or "none")
        if action_type == "degrade_answer":
            metrics.degraded_answers += 1

    metrics.remediation_failed = max(0, metrics.remediation_triggered - metrics.remediation_succeeded)
    return metrics.to_dict()

def assess_evidence_quality(
    *,
    answer: str,
    sources: Optional[List[str]],
    retrieval_chunks: Optional[List[Dict[str, Any]]],
    need_evidence: bool,
    confidence_label: str = "",
) -> Dict[str, Any]:
    text = str(answer or "")
    src_list = [str(s).strip() for s in (sources or []) if str(s).strip()]
    chunk_list = list(retrieval_chunks or [])
    source_count = len(set(src_list))
    chunk_count = len(chunk_list)
    has_sources = source_count > 0
    citation_present = any(token in text for token in ("来源", "资料显示", "根据", "【", "文献", "出处"))
    separates = (
        ("资料支持" in text and "推断" in text)
        or ("资料未明确提及" in text and "推断" in text)
        or ("资料支持" in text and "模型推断" in text)
    )

    coverage = 0.0
    if need_evidence:
        coverage = min(1.0, source_count * 0.5 + min(chunk_count, 4) * 0.1)
    else:
        coverage = min(1.0, 0.6 + source_count * 0.2 + min(chunk_count, 2) * 0.1)

    issue_type = "none"
    summary = "证据质量正常。"
    if need_evidence and not has_sources:
        issue_type = "missing_sources"
        coverage = 0.0
        summary = "需要证据但未提供来源。"
    elif need_evidence and chunk_count <= 1:
        issue_type = "weak_coverage"
        summary = "检索片段较少，证据覆盖偏弱。"
    elif need_evidence and not citation_present:
        issue_type = "no_citation"
        summary = "回答缺少明显引用标记。"
    elif need_evidence and not separates:
        issue_type = "unclear_support_boundary"
        summary = "未清晰区分资料支持与模型推断。"

    if need_evidence and str(confidence_label or "").strip() == "低" and issue_type == "none":
        issue_type = "unsupported_claim_risk"
        summary = "可信度较低，存在结论支撑不足风险。"

    assessment = EvidenceQualityAssessment(
        need_evidence=bool(need_evidence),
        has_sources=has_sources,
        source_count=source_count,
        retrieved_chunk_count=chunk_count,
        evidence_coverage=coverage,
        citation_present=bool(citation_present),
        separates_supported_and_inferred=bool(separates),
        issue_type=issue_type,
        summary=summary,
    )
    return assessment.to_dict()

def _build_assessment(
    *,
    tool_name: str,
    success: bool,
    usable: bool,
    issue_type: str,
    summary: str,
    suggested_action: str = "",
    retryable: bool = False,
    fallback_tool: str = "",
) -> ToolOutcomeAssessment:
    issue = issue_type if issue_type in OUTCOME_ISSUES else "unknown"
    trace = f"{tool_name} 执行可用。" if issue == "none" else f"{tool_name} 评估：{issue}，{summary}"
    return ToolOutcomeAssessment(
        tool_name=tool_name,
        success=success,
        usable=usable,
        issue_type=issue,
        summary=summary,
        suggested_action=suggested_action,
        retryable=retryable,
        fallback_tool=fallback_tool,
        trace_summary=trace[:160],
    )

def assess_tool_outcome(
    tool_name: str,
    result: ToolResult,
    *,
    instruction: str = "",
) -> ToolOutcomeAssessment:
    tool_key = str(tool_name or "").upper().strip() or "UNKNOWN"
    metadata = dict(result.metadata or {})
    content = (result.content or "").strip()
    error_text = (result.error or "").strip()

    if tool_key == "RAG":
        chunk_count = int(metadata.get("retrieved_chunk_count") or 0)
        quality = dict(metadata.get("retrieval_quality") or {})
        quality_score = float(quality.get("score", 0.0) or 0.0)
        if chunk_count <= 0:
            return _build_assessment(
                tool_name=tool_key,
                success=bool(result.success),
                usable=False,
                issue_type="low_evidence",
                summary="未检索到有效证据片段。",
                suggested_action="建议扩展关键词重检索，或切换 DISCOVERY 进行交叉分析。",
                retryable=True,
                fallback_tool="DISCOVERY",
            )
        if quality_score < GRAPH_REPLAN_LOW_QUALITY_THRESHOLD:
            return _build_assessment(
                tool_name=tool_key,
                success=bool(result.success),
                usable=True,
                issue_type="low_evidence",
                summary=f"检索质量偏低（score={quality_score:.2f}）。",
                suggested_action="建议扩展关键词并重检索，必要时补充 DISCOVERY。",
                retryable=True,
                fallback_tool="DISCOVERY",
            )
        return _build_assessment(
            tool_name=tool_key,
            success=bool(result.success),
            usable=bool(result.success and content),
            issue_type="none",
            summary="RAG 证据可用。",
        )

    if tool_key in {"DATA_PROFILE", "FILE_INSPECTOR"}:
        has_file_id = bool(re.search(r"\bfile[_-]?id\s*[:=]\s*[\w\-]+", instruction or "", flags=re.IGNORECASE))
        missing_file = (
            (not has_file_id)
            or ("file_id" in error_text.lower())
            or ("未上传" in error_text)
            or ("文件" in error_text and "不存在" in error_text)
        )
        if missing_file:
            return _build_assessment(
                tool_name=tool_key,
                success=bool(result.success),
                usable=False,
                issue_type="missing_file",
                summary="缺少可用 file_id 或文件不可访问。",
                suggested_action="请先上传文件并提供 file_id，再执行数据工具。",
                retryable=False,
                fallback_tool="FILE_INSPECTOR" if tool_key == "DATA_PROFILE" else "",
            )
        if not result.success:
            return _build_assessment(
                tool_name=tool_key,
                success=False,
                usable=False,
                issue_type="tool_error",
                summary=error_text or "数据工具执行失败。",
                suggested_action="建议先用 FILE_INSPECTOR 校验文件可读性，再重试。",
                retryable=True,
                fallback_tool="FILE_INSPECTOR",
            )
        if not content:
            return _build_assessment(
                tool_name=tool_key,
                success=True,
                usable=False,
                issue_type="empty_result",
                summary="数据工具返回为空。",
                suggested_action="建议检查文件内容或字段后重试。",
                retryable=True,
                fallback_tool="FILE_INSPECTOR",
            )
        return _build_assessment(
            tool_name=tool_key,
            success=True,
            usable=True,
            issue_type="none",
            summary="数据工具输出可用。",
        )

    if tool_key == "CALCULATOR":
        if not result.success:
            issue = "invalid_input" if ("表达式" in error_text or "parse" in error_text.lower()) else "tool_error"
            return _build_assessment(
                tool_name=tool_key,
                success=False,
                usable=False,
                issue_type=issue,
                summary=error_text or "计算失败。",
                suggested_action="建议用户明确表达式，或先用 LLM 提取表达式后再计算。",
                retryable=False,
                fallback_tool="LLM",
            )
        if not content:
            return _build_assessment(
                tool_name=tool_key,
                success=True,
                usable=False,
                issue_type="empty_result",
                summary="计算结果为空。",
                suggested_action="建议用户明确表达式后重试。",
                retryable=True,
                fallback_tool="LLM",
            )
        return _build_assessment(
            tool_name=tool_key,
            success=True,
            usable=True,
            issue_type="none",
            summary="计算结果可用。",
        )

    if tool_key == "LLM":
        if not result.success:
            return _build_assessment(
                tool_name=tool_key,
                success=False,
                usable=False,
                issue_type="tool_error",
                summary=error_text or "LLM 执行失败。",
                suggested_action="可重试 LLM，或降级为保守回答。",
                retryable=True,
                fallback_tool="LLM",
            )
        if not content:
            return _build_assessment(
                tool_name=tool_key,
                success=True,
                usable=False,
                issue_type="empty_result",
                summary="LLM 输出为空。",
                suggested_action="建议重试 LLM。",
                retryable=True,
                fallback_tool="LLM",
            )
        return _build_assessment(
            tool_name=tool_key,
            success=True,
            usable=True,
            issue_type="none",
            summary="LLM 输出可用。",
        )

    if not result.success:
        return _build_assessment(
            tool_name=tool_key,
            success=False,
            usable=False,
            issue_type="tool_error",
            summary=error_text or "工具执行失败。",
            suggested_action="建议切换工具或降级回答并说明失败原因。",
            retryable=True,
            fallback_tool="LLM",
        )
    if not content:
        return _build_assessment(
            tool_name=tool_key,
            success=True,
            usable=False,
            issue_type="empty_result",
            summary="工具输出为空。",
            suggested_action="建议重试或改用其他工具。",
            retryable=True,
            fallback_tool="LLM",
        )
    return _build_assessment(
        tool_name=tool_key,
        success=True,
        usable=True,
        issue_type="none",
        summary="工具输出可用。",
    )

class AgentExecutor:
    """标准化的步骤执行器：负责状态推进、异常隔离与执行轨迹。"""

    def __init__(self, registry: Dict[str, ToolCallable]):
        self.registry = registry

    def build_steps(self, plan_steps: List[Dict[str, Any]]) -> List[AgentStep]:
        steps: List[AgentStep] = []
        for idx, item in enumerate(plan_steps or []):
            tool_name = str((item or {}).get("tool", "LLM")).upper().strip() or "LLM"
            instruction = str((item or {}).get("task", "")).strip()
            reason = str((item or {}).get("reason", "")).strip()
            expected_output = str((item or {}).get("expected_output", "")).strip()
            fallback = str((item or {}).get("fallback", "")).strip()
            step_metadata: Dict[str, Any] = {}
            if reason:
                step_metadata["reason"] = reason
            if expected_output:
                step_metadata["expected_output"] = expected_output
            if fallback:
                step_metadata["fallback"] = fallback
            step = AgentStep(
                id=f"step_{idx + 1}_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name,
                instruction=instruction,
                retry_of=(item or {}).get("retry_of"),
                attempts=int((item or {}).get("attempts") or 1),
                input={"tool_name": tool_name, "instruction": instruction},
                metadata=step_metadata,
            )
            steps.append(step)
        return steps

    def build_task(
        self,
        user_query: str,
        plan_steps: List[Dict[str, Any]],
        task_id: Optional[str] = None,
        run_mode: str = "sync",
        resumed_from: Optional[str] = None,
    ) -> AgentTask:
        task = AgentTask(
            id=str(task_id or f"task_{uuid.uuid4().hex}"),
            user_query=user_query,
            status="pending",
            run_mode=run_mode or "sync",
            resumed_from=resumed_from,
            steps=self.build_steps(plan_steps),
            metadata={"step_count": len(plan_steps or [])},
        )
        return task

    def sync_task_steps(self, task: AgentTask, plan_steps: List[Dict[str, Any]]) -> AgentTask:
        task.steps = self.build_steps(plan_steps)
        task.metadata["step_count"] = len(plan_steps or [])
        task.touch()
        return task

    def execute(self, tool_name: str, task: str, agent: Any) -> ToolResult:
        tool_key = (tool_name or "").upper()
        tool_fn = self.registry.get(tool_key)
        if not tool_fn:
            return ToolResult(success=False, content="", error=f"unknown tool: {tool_key}")

        request = ToolInput(task=task, tool=tool_key)
        try:
            raw = tool_fn(request.task, agent)
            if isinstance(raw, ToolResult):
                merged = dict(raw.metadata or {})
                merged.setdefault("tool", tool_key)
                raw.metadata = merged
                return raw
            return ToolResult(success=True, content=str(raw), metadata={"tool": tool_key})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, content="", metadata={"tool": tool_key}, error=str(exc))

    async def _execute_rag(self, instruction: str, agent: Any) -> ToolResult:
        retriever = getattr(agent, "retriever", None)
        if retriever is None:
            # fallback to legacy RAG tool output
            return execute_tool("RAG", instruction, agent, registry=self.registry)

        ret_res = await retriever.ainvoke({"question": instruction, "final_use_kb": True})
        chunks = ret_res.get("kb_chunks", []) or []
        quality = ret_res.get("retrieval_quality", {}) or {}
        sources = [c.get("doc_name", "") for c in chunks if c.get("doc_name")]
        if chunks:
            lines = []
            for c in chunks:
                content = c.get("content", "") or ""
                if len(content) > RAG_MAX_CHUNK_LENGTH:
                    content = content[:RAG_MAX_CHUNK_LENGTH] + "…"
                lines.append(f"【{c.get('doc_name', '未知来源')}】\n{content}")
            content = "\n\n".join(lines)
        else:
            content = "[RAG] 未检索到相关资料"

        artifacts: List[Dict[str, Any]] = []
        for idx, c in enumerate(chunks[:8]):
            artifacts.append(
                Artifact(
                    id=f"artifact_rag_{idx}_{uuid.uuid4().hex[:6]}",
                    name=c.get("doc_name", f"文档{idx + 1}"),
                    type="retrieval_chunk",
                    content=c.get("content", ""),
                    metadata={"doc_name": c.get("doc_name", ""), "chunk_id": c.get("id", "")},
                ).to_dict()
            )

        metadata = {
            "tool": "RAG",
            "source_count": len(set(sources)),
            "retrieved_docs": sorted(set(sources)),
            "retrieved_chunk_count": len(chunks),
            "retrieval_quality": quality,
            "kb_chunks": chunks,
        }
        return ToolResult(success=True, content=content, metadata=metadata, artifacts=artifacts, error=None)

    def _enrich_result_metadata(self, tool_key: str, instruction: str, result: ToolResult) -> ToolResult:
        metadata = dict(result.metadata or {})
        metadata.setdefault("tool", tool_key)
        if tool_key == "CALCULATOR":
            metadata.setdefault("calculator_expression", instruction)
        elif tool_key == "MEMORY":
            text = result.content or ""
            memory_hits = sum(1 for tag in ("【摘要记忆】", "【最近对话】", "【短期记忆】") if tag in text)
            metadata.setdefault("memory_hit_count", memory_hits)
        elif tool_key == "DISCOVERY":
            metadata.setdefault("discovery_mode", "deep_insight")
        result.metadata = metadata
        return result

    async def execute_step(
        self,
        step: AgentStep,
        agent: Any,
        cancellation_event: Optional[Any] = None,
        fail_fast: bool = False,
    ) -> Tuple[AgentStep, ToolResult, Optional[Dict[str, Any]]]:
        if cancellation_event is not None and getattr(cancellation_event, "is_set", None) and cancellation_event.is_set():
            step.cancel_requested = True
            step.status = "skipped"
            step.error = "任务已取消"
            step.started_at = _iso_now()
            step.finished_at = step.started_at
            result = ToolResult(success=False, content="", metadata={"tool": step.tool_name}, error="task_canceled")
            trace_item = {
                "step_id": step.id,
                "tool_name": step.tool_name,
                "instruction": step.instruction,
                "status": "canceled",
                "error": "任务已取消",
                "started_at": step.started_at,
                "finished_at": step.finished_at,
            }
            return step, result, trace_item

        step.attempts = int(step.attempts or 0) + 1
        step.status = "running"
        step.started_at = _iso_now()
        step.finished_at = None
        step.error = None
        step.result = {}

        tool_key = (step.tool_name or "").upper()
        try:
            if tool_key == "RAG":
                result = await self._execute_rag(step.instruction, agent)
            else:
                result = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: execute_tool(tool_key, step.instruction, agent, registry=self.registry)
                )
            result = self._enrich_result_metadata(tool_key, step.instruction, result)
            outcome = assess_tool_outcome(tool_key, result, instruction=step.instruction)
            result_metadata = dict(result.metadata or {})
            result_metadata["outcome_assessment"] = outcome.to_dict()
            result.metadata = result_metadata
            step.result = result.to_dict()
            step.artifacts = []
            for item in result.artifacts or []:
                if isinstance(item, dict):
                    normalized = dict(item)
                    normalized.setdefault("id", f"artifact_{uuid.uuid4().hex[:8]}")
                    normalized.setdefault("created_at", _iso_now())
                    step.artifacts.append(Artifact.from_dict(normalized))
            step.metadata.update(result.metadata or {})
            step.metadata["outcome_assessment"] = outcome.to_dict()
            step.status = "success" if result.success else "failed"
            step.error = result.error
            if cancellation_event is not None and getattr(cancellation_event, "is_set", None) and cancellation_event.is_set():
                step.cancel_requested = True
                step.status = "skipped"
                step.error = "任务已取消"
        except Exception as exc:  # pragma: no cover
            result = ToolResult(success=False, content="", metadata={"tool": tool_key}, error=str(exc))
            outcome = assess_tool_outcome(tool_key, result, instruction=step.instruction)
            result.metadata["outcome_assessment"] = outcome.to_dict()
            step.status = "failed"
            step.error = str(exc)
            step.result = result.to_dict()
            step.metadata.update({"tool": tool_key})
            step.metadata["outcome_assessment"] = outcome.to_dict()
            if fail_fast:
                raise
        finally:
            step.finished_at = _iso_now()

        outcome_payload = dict((result.metadata or {}).get("outcome_assessment") or {})
        trace_item = {
            "step_id": step.id,
            "tool_name": step.tool_name,
            "instruction": step.instruction,
            "status": step.status,
            "error": step.error,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
            "outcome": outcome_payload,
            "trace_summary": str(outcome_payload.get("trace_summary") or ""),
        }
        return step, result, trace_item

    async def aexecute(self, tool_name: str, task: str, agent: Any) -> ToolResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.execute(tool_name, task, agent))
