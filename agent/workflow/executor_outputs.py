from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_step_execution_trace(trace_item: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [trace_item] if trace_item else []


def build_tool_result_payload(tool_result: Any) -> List[Dict[str, Any]]:
    return [tool_result.to_dict()]


def build_step_execution_payload(
    *,
    trace_item: Optional[Dict[str, Any]],
    tool_result: Any,
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "execution_trace": build_step_execution_trace(trace_item),
        "tool_results_v2": build_tool_result_payload(tool_result),
        "artifacts": artifacts,
    }


def build_cancel_return_payload(
    *,
    task: Dict[str, Any],
    current_step_index: int,
    trace: List[str],
    cancel_requested: bool = True,
    step_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "task": task,
        "current_step_index": current_step_index,
        "cancel_requested": cancel_requested,
        "trace": trace,
    }
    if step_payload is not None:
        payload.update(step_payload)
    return payload


def build_replan_return_payload(
    *,
    task: Dict[str, Any],
    step_payload: Dict[str, Any],
    execution_replan_count: int,
    feedback: str,
    trace: List[str],
    retrieval_quality_score: Optional[float] = None,
    retrieval_quality_detail: Optional[Dict[str, Any]] = None,
    remediation_count: Optional[int] = None,
    remediation_stats: Optional[Dict[str, Any]] = None,
    unresolved_outcomes: Optional[List[Dict[str, Any]]] = None,
    active_step_results: Optional[List[str]] = None,
    active_tool_results_v2: Optional[List[Dict[str, Any]]] = None,
    active_execution_trace: Optional[List[Dict[str, Any]]] = None,
    active_artifacts: Optional[List[Dict[str, Any]]] = None,
    active_sources: Optional[List[str]] = None,
    active_retrieval_chunks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "task": task,
        **step_payload,
        "replanning_needed": True,
        "answer_revision_needed": False,
        "execution_replan_count": execution_replan_count,
        "feedback": feedback,
        "trace": trace,
    }
    if retrieval_quality_score is not None:
        payload["retrieval_quality_score"] = retrieval_quality_score
    if retrieval_quality_detail is not None:
        payload["retrieval_quality_detail"] = retrieval_quality_detail
    if remediation_count is not None:
        payload["remediation_count"] = remediation_count
    if remediation_stats is not None:
        payload["remediation_stats"] = remediation_stats
    if unresolved_outcomes is not None:
        payload["unresolved_outcomes"] = unresolved_outcomes
    if active_step_results is not None:
        payload["active_step_results"] = active_step_results
    if active_tool_results_v2 is not None:
        payload["active_tool_results_v2"] = active_tool_results_v2
    if active_execution_trace is not None:
        payload["active_execution_trace"] = active_execution_trace
    if active_artifacts is not None:
        payload["active_artifacts"] = active_artifacts
    if active_sources is not None:
        payload["active_sources"] = active_sources
    if active_retrieval_chunks is not None:
        payload["active_retrieval_chunks"] = active_retrieval_chunks
    return payload


def build_executor_return_payload(
    *,
    task: Dict[str, Any],
    step_results: List[str],
    current_step_index: int,
    sources: List[str],
    retrieval_quality_score: float,
    retrieval_quality_detail: Dict[str, Any],
    retrieval_chunks: List[Dict[str, Any]],
    trace: List[str],
    remediation_count: int,
    remediation_stats: Dict[str, Any],
    unresolved_outcomes: List[Dict[str, Any]],
    step_payload: Dict[str, Any],
    steps: Optional[List[Dict[str, Any]]] = None,
    active_step_results: Optional[List[str]] = None,
    active_tool_results_v2: Optional[List[Dict[str, Any]]] = None,
    active_execution_trace: Optional[List[Dict[str, Any]]] = None,
    active_artifacts: Optional[List[Dict[str, Any]]] = None,
    active_sources: Optional[List[str]] = None,
    active_retrieval_chunks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "task": task,
        "step_results": step_results,
        "current_step_index": current_step_index,
        "sources": sources,
        "retrieval_quality_score": retrieval_quality_score,
        "retrieval_quality_detail": retrieval_quality_detail,
        "retrieval_chunks": retrieval_chunks,
        **step_payload,
        "trace": trace,
        "remediation_count": remediation_count,
        "remediation_stats": remediation_stats,
        "unresolved_outcomes": unresolved_outcomes,
        "replanning_needed": False,
        "answer_revision_needed": False,
    }
    if steps is not None:
        payload["steps"] = steps
    if active_step_results is not None:
        payload["active_step_results"] = active_step_results
    if active_tool_results_v2 is not None:
        payload["active_tool_results_v2"] = active_tool_results_v2
    if active_execution_trace is not None:
        payload["active_execution_trace"] = active_execution_trace
    if active_artifacts is not None:
        payload["active_artifacts"] = active_artifacts
    if active_sources is not None:
        payload["active_sources"] = active_sources
    if active_retrieval_chunks is not None:
        payload["active_retrieval_chunks"] = active_retrieval_chunks
    return payload
