from __future__ import annotations
import time
from typing import Any, Callable, Dict, List
from utils.logger import logger as default_logger

class ExecutorNode:
    def __init__(
        self,
        *,
        core: Any,
        executor: Any,
        task_from_state: Callable[[Dict[str, Any]], Any],
        safe_save_task: Callable[[Any], None],
        safe_save_step: Callable[[str, Any, int], None],
        safe_save_artifact: Callable[[str, Any], None],
        normalize_artifacts_with_task: Callable[[str, List[Any]], List[Dict[str, Any]]],
        artifact_from_dict: Callable[[Dict[str, Any]], Any],
        truncate_step_result: Callable[[str], str],
        is_cancel_requested: Callable[[], bool],
        advance_remediation_stats: Callable[[Dict[str, Any], str, str], Dict[str, Any]],
        format_outcome_feedback: Callable[[Dict[str, Any]], str],
        stream_thought: Callable[[str], None],
        sync_legacy_steps: Callable[[Any], List[Dict[str, Any]]],
        build_remediation_decision_fn: Callable[..., Any],
        build_step_execution_payload_fn: Callable[..., Dict[str, Any]],
        build_executor_return_payload_fn: Callable[..., Dict[str, Any]],
        build_replan_return_payload_fn: Callable[..., Dict[str, Any]],
        build_pre_execution_cancel_payload_fn: Callable[..., Dict[str, Any]],
        build_post_execution_cancel_payload_fn: Callable[..., Dict[str, Any]],
        build_cancelled_result_text_fn: Callable[[], str],
        build_retry_task_instruction_fn: Callable[[Dict[str, Any], str], str],
        build_retry_trace_text_fn: Callable[..., str],
        build_replan_feedback_fn: Callable[..., str],
        build_unresolved_outcome_payload_fn: Callable[..., Dict[str, Any]],
        build_ask_user_or_degrade_result_text_fn: Callable[..., str],
        build_remediation_stream_text_fn: Callable[..., str],
        graph_replan_on_low_quality: bool,
        graph_replan_low_quality_threshold: float,
        graph_replan_require_expansion: bool,
        graph_replan_max_attempts: int,
        logger=default_logger,
    ):
        self.core = core
        self.executor = executor
        self.task_from_state = task_from_state
        self.safe_save_task = safe_save_task
        self.safe_save_step = safe_save_step
        self.safe_save_artifact = safe_save_artifact
        self.normalize_artifacts_with_task = normalize_artifacts_with_task
        self.artifact_from_dict = artifact_from_dict
        self.truncate_step_result = truncate_step_result
        self.is_cancel_requested = is_cancel_requested
        self.advance_remediation_stats = advance_remediation_stats
        self.format_outcome_feedback = format_outcome_feedback
        self.stream_thought = stream_thought
        self.sync_legacy_steps = sync_legacy_steps
        self.build_remediation_decision_fn = build_remediation_decision_fn
        self.build_step_execution_payload_fn = build_step_execution_payload_fn
        self.build_executor_return_payload_fn = build_executor_return_payload_fn
        self.build_replan_return_payload_fn = build_replan_return_payload_fn
        self.build_pre_execution_cancel_payload_fn = build_pre_execution_cancel_payload_fn
        self.build_post_execution_cancel_payload_fn = build_post_execution_cancel_payload_fn
        self.build_cancelled_result_text_fn = build_cancelled_result_text_fn
        self.build_retry_task_instruction_fn = build_retry_task_instruction_fn
        self.build_retry_trace_text_fn = build_retry_trace_text_fn
        self.build_replan_feedback_fn = build_replan_feedback_fn
        self.build_unresolved_outcome_payload_fn = build_unresolved_outcome_payload_fn
        self.build_ask_user_or_degrade_result_text_fn = build_ask_user_or_degrade_result_text_fn
        self.build_remediation_stream_text_fn = build_remediation_stream_text_fn
        self.graph_replan_on_low_quality = graph_replan_on_low_quality
        self.graph_replan_low_quality_threshold = graph_replan_low_quality_threshold
        self.graph_replan_require_expansion = graph_replan_require_expansion
        self.graph_replan_max_attempts = graph_replan_max_attempts
        self.logger = logger

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        idx = state["current_step_index"]
        task = self.task_from_state(state)
        steps = task.steps
        cancel_now = self.is_cancel_requested()
        if cancel_now:
            task.cancel_requested = True

        if idx >= len(steps):
            return {"current_step_index": idx + 1}

        if task.cancel_requested:
            for pos in range(idx, len(steps)):
                remain = steps[pos]
                if str(remain.status or "pending") == "pending":
                    remain.status = "skipped"
                    remain.cancel_requested = True
                    remain.error = "任务已取消"
                    remain.finished_at = remain.finished_at or remain.started_at or None
                    self.safe_save_step(task.id, remain, pos)
            task.status = "canceled"
            task.final_answer = self.build_cancelled_result_text_fn()
            task.touch()
            self.safe_save_task(task)
            return self.build_pre_execution_cancel_payload_fn(
                task=task.to_dict(),
                current_step_index=len(steps),
            )

        step = steps[idx]
        tool = step.tool_name
        instruction = step.instruction
        started = time.monotonic()
        self.logger.info(
            "[Executor] step start task_id={} step_index={} tool={} instruction_len={}",
            task.id,
            idx,
            tool,
            len(instruction or ""),
        )

        self.stream_thought(f"\n> [思考] 步骤 {idx+1}: 使用 {tool}...\n")

        result_text = ""
        new_sources = []
        chunks = []
        quality = {}
        quality_score = state.get("retrieval_quality_score", 0.0)
        active_step_results = list(state.get("active_step_results", state.get("step_results", [])) or [])
        active_tool_results = list(state.get("active_tool_results_v2", []) or [])
        active_execution_trace = list(state.get("active_execution_trace", state.get("execution_trace", [])) or [])
        active_artifacts = list(state.get("active_artifacts", state.get("artifacts", [])) or [])
        active_sources = list(state.get("active_sources", state.get("sources", [])) or [])
        active_retrieval_chunks = list(state.get("active_retrieval_chunks", state.get("retrieval_chunks", [])) or [])
        remediation_count = int(state.get("remediation_count", 0) or 0)
        remediation_stats = dict(state.get("remediation_stats") or {})
        unresolved_outcomes = list(state.get("unresolved_outcomes", []) or [])

        if tool == "RAG":
            self.stream_thought("> [执行] 正在检索知识库...\n")
        else:
            self.stream_thought(f"> [执行] 正在运行 {tool}...\n")

        updated_step, tool_result, trace_item = await self.executor.execute_step(
            step,
            self.core,
            cancellation_event=getattr(self.core, "_active_cancel_event", None),
            fail_fast=False,
        )
        self.logger.info(
            "[Executor] step end task_id={} step_index={} tool={} status={} success={} content_len={} duration_ms={}",
            task.id,
            idx,
            tool,
            updated_step.status,
            bool(tool_result.success),
            len(tool_result.content or ""),
            int((time.monotonic() - started) * 1000),
        )
        task.steps[idx] = updated_step
        if updated_step.cancel_requested:
            task.cancel_requested = True
        task.touch()
        self.safe_save_task(task)
        self.safe_save_step(task.id, updated_step, idx)
        normalized_artifacts = self.normalize_artifacts_with_task(task.id, list(tool_result.artifacts or []))
        if normalized_artifacts:
            for item in normalized_artifacts:
                artifact = self.artifact_from_dict(item)
                task.artifacts.append(artifact)
                self.safe_save_artifact(task.id, artifact)
        self.safe_save_task(task)

        result_text = tool_result.content or ""
        outcome = dict((tool_result.metadata or {}).get("outcome_assessment") or {})
        issue_type = str(outcome.get("issue_type") or "none")
        retryable = bool(outcome.get("retryable", False))
        outcome_feedback = self.format_outcome_feedback(outcome)
        remediation_stats = self.advance_remediation_stats(remediation_stats, tool, issue_type)
        remediation_decision = self.build_remediation_decision_fn(
            updated_step,
            tool_result,
            outcome,
            {
                "remediation_count": remediation_count,
                "remediation_stats": remediation_stats,
                "execution_replan_count": state.get("execution_replan_count", 0),
            },
        )
        decision_payload = remediation_decision.to_dict()
        trace_item = dict(trace_item or {})
        trace_item["remediation"] = decision_payload
        if remediation_decision.trace_summary:
            trace_item["trace_summary"] = remediation_decision.trace_summary
        updated_step.metadata["remediation_decision"] = decision_payload
        updated_step.metadata["stop_reason"] = remediation_decision.stop_reason
        updated_step.metadata["retry_of"] = updated_step.retry_of
        updated_step.metadata["remediation_attempt"] = int(
            dict(remediation_stats.get("step_remediation_counts") or {}).get(updated_step.id, 0) or 0
        )
        task.steps[idx] = updated_step
        self.safe_save_step(task.id, updated_step, idx)
        step_payload = self.build_step_execution_payload_fn(
            trace_item=trace_item,
            tool_result=tool_result,
            artifacts=normalized_artifacts,
        )
        next_active_tool_results = active_tool_results + list(step_payload.get("tool_results_v2", []) or [])
        next_active_execution_trace = active_execution_trace + list(step_payload.get("execution_trace", []) or [])
        next_active_artifacts = active_artifacts + list(normalized_artifacts or [])

        action = dict(decision_payload.get("action") or {})
        action_type = str(action.get("action_type") or "none")
        action_allowed = bool(action.get("allowed", False))
        suppress_default_replan = False
        if remediation_decision.should_remediate:
            if action_allowed and action_type in {"retry_same_tool", "switch_tool"}:
                retry_tool = str(action.get("retry_tool") or tool).upper().strip() or tool
                retry_task = self.build_retry_task_instruction_fn(action, instruction)
                step_counts = dict(remediation_stats.get("step_remediation_counts") or {})
                step_counts[updated_step.id] = int(step_counts.get(updated_step.id, 0) or 0) + 1
                remediation_stats["step_remediation_counts"] = step_counts
                if tool == "LLM" and issue_type == "empty_result":
                    remediation_stats["llm_empty_retry_count"] = int(remediation_stats.get("llm_empty_retry_count", 0) or 0) + 1
                remediation_count += 1
                retry_payload = {
                    "tool": retry_tool,
                    "task": retry_task,
                    "retry_of": updated_step.id,
                    "attempts": 0,
                }
                retry_step = self.executor.build_steps([retry_payload])[0]
                retry_step.metadata.update(
                    {
                        "retry_of": updated_step.id,
                        "remediation_attempt": step_counts[updated_step.id],
                        "remediation_decision": decision_payload,
                        "remediation_source_issue": issue_type,
                    }
                )
                task.steps.insert(idx + 1, retry_step)
                task.touch()
                self.safe_save_task(task)
                for pos in range(idx + 1, len(task.steps)):
                    self.safe_save_step(task.id, task.steps[pos], pos)
                self.stream_thought(f"> [补救] 已创建自动重试步骤：{retry_tool}\n")
                return self.build_executor_return_payload_fn(
                    task=task.to_dict(),
                    steps=self.sync_legacy_steps(task),
                    step_results=[f"[{tool}] {instruction}：\n{self.truncate_step_result(result_text)}"],
                    current_step_index=idx + 1,
                    sources=new_sources,
                    retrieval_quality_score=quality_score if tool == "RAG" else state.get("retrieval_quality_score", 0.0),
                    retrieval_quality_detail=quality if tool == "RAG" else state.get("retrieval_quality_detail", {}),
                    retrieval_chunks=chunks if tool == "RAG" else [],
                    step_payload=step_payload,
                    trace=[self.build_retry_trace_text_fn(tool=tool, trace_summary=remediation_decision.trace_summary)],
                    remediation_count=remediation_count,
                    remediation_stats=remediation_stats,
                    unresolved_outcomes=unresolved_outcomes,
                    active_step_results=active_step_results + [
                        f"[{tool}] {instruction}：\n{self.truncate_step_result(result_text)}"
                    ],
                    active_tool_results_v2=next_active_tool_results,
                    active_execution_trace=next_active_execution_trace,
                    active_artifacts=next_active_artifacts,
                    active_sources=list(dict.fromkeys(active_sources + new_sources)),
                    active_retrieval_chunks=active_retrieval_chunks + (chunks if tool == "RAG" else []),
                )
            if action_allowed and action_type == "replan":
                step_counts = dict(remediation_stats.get("step_remediation_counts") or {})
                step_counts[updated_step.id] = int(step_counts.get(updated_step.id, 0) or 0) + 1
                remediation_stats["step_remediation_counts"] = step_counts
                remediation_count += 1
                self.stream_thought("> [补救] 触发受控重规划。\n")
                return self.build_replan_return_payload_fn(
                    task=task.to_dict(),
                    step_payload=step_payload,
                    execution_replan_count=state.get("execution_replan_count", 0) + 1,
                    feedback=self.build_replan_feedback_fn(
                        idx=idx,
                        tool=tool,
                        trace_summary=remediation_decision.trace_summary,
                    ),
                    trace=["controlled remediation replan"],
                    remediation_count=remediation_count,
                    remediation_stats=remediation_stats,
                    unresolved_outcomes=unresolved_outcomes,
                    active_step_results=[],
                    active_tool_results_v2=[],
                    active_execution_trace=[],
                    active_artifacts=[],
                    active_sources=[],
                    active_retrieval_chunks=[],
                )
            if action_type in {"ask_user", "degrade_answer"}:
                suppress_default_replan = True
                unresolved_outcomes.append(
                    self.build_unresolved_outcome_payload_fn(
                        tool=tool,
                        issue_type=issue_type,
                        outcome=outcome,
                        action=action,
                    )
                )
                result_text = self.build_ask_user_or_degrade_result_text_fn(
                    outcome_feedback=outcome_feedback,
                    trace_summary=remediation_decision.trace_summary,
                    fallback_result_text=result_text,
                )
                self.stream_thought(
                    f"> [补救] {self.build_remediation_stream_text_fn(action=action, trace_summary=remediation_decision.trace_summary)}\n"
                )
        if retryable and issue_type != "none":
            self.stream_thought(f"> [闭环] {tool} 可重试：{outcome_feedback}\n")
        if tool == "RAG":
            quality = dict((tool_result.metadata or {}).get("retrieval_quality", {}) or {})
            chunks = list((tool_result.metadata or {}).get("kb_chunks", []) or [])
            quality_score = float(quality.get("score", 0.0) or 0.0)
            has_rag_content = bool(result_text.strip()) and not result_text.strip().startswith("[RAG] 未检索到")
            for c in chunks:
                if c.get("doc_name"):
                    new_sources.append(c["doc_name"])
            if chunks and not suppress_default_replan:
                self.stream_thought(f"> [结果] 找到 {len(chunks)} 条相关资料\n")
                allow_low_quality_replan = (
                    self.graph_replan_on_low_quality
                    and quality_score < self.graph_replan_low_quality_threshold
                    and (
                        (not self.graph_replan_require_expansion)
                        or bool(quality.get("expanded", False))
                    )
                )
                if allow_low_quality_replan:
                    replan_count = state.get("execution_replan_count", 0)
                    if replan_count < self.graph_replan_max_attempts:
                        self.stream_thought("> [结果] 检索质量偏低，正在触发重新规划...\n")
                        return self.build_replan_return_payload_fn(
                            task=task.to_dict(),
                            step_payload=step_payload,
                            execution_replan_count=replan_count + 1,
                            retrieval_quality_score=quality_score,
                            retrieval_quality_detail=quality,
                            feedback=(
                                f"步骤 {idx+1} [RAG] 检索质量偏低："
                                f"score={quality_score:.2f}, hits={quality.get('hit_count', 0)}, "
                                f"avg_similarity={quality.get('avg_similarity', 0)}。请改用其他检索策略或工具。"
                            ),
                            trace=["RAG low-quality, triggering replan"],
                            active_step_results=[],
                            active_tool_results_v2=[],
                            active_execution_trace=[],
                            active_artifacts=[],
                            active_sources=[],
                            active_retrieval_chunks=[],
                        )
            elif has_rag_content:
                self.stream_thought("> [结果] 找到可用资料\n")
            elif not suppress_default_replan:
                self.stream_thought("> [结果] 未找到资料，正在触发重新规划...\n")
                return self.build_replan_return_payload_fn(
                    task=task.to_dict(),
                    step_payload=step_payload,
                    execution_replan_count=state.get("execution_replan_count", 0) + 1,
                    retrieval_quality_score=quality_score,
                    retrieval_quality_detail=quality,
                    feedback=f"步骤 {idx+1} [RAG] 未找到任何相关资料，请尝试使用搜索引擎或其他工具。",
                    trace=["RAG failed, triggering replan"],
                    active_step_results=[],
                    active_tool_results_v2=[],
                    active_execution_trace=[],
                    active_artifacts=[],
                    active_sources=[],
                    active_retrieval_chunks=[],
                )
        else:
            if issue_type == "missing_file":
                self.stream_thought("> [闭环] 文件上下文不足，保留提示并继续汇总回答。\n")
                result_text = outcome_feedback or "缺少可用文件，请先上传文件并提供 file_id。"
            elif issue_type == "invalid_input":
                self.stream_thought("> [闭环] 计算输入不合法，保留提示并继续汇总回答。\n")
                result_text = outcome_feedback or "输入表达式不明确，请补充可计算表达式。"
            elif (
                not suppress_default_replan
                and (
                    (not tool_result.success)
                    or (not result_text)
                    or result_text.strip().startswith("Error:")
                    or result_text.strip().startswith("[系统错误]")
                    or result_text.strip().startswith("[错误]")
                )
            ):
                self.stream_thought("> [结果] 执行失败或为空，正在触发重新规划...\n")
                return self.build_replan_return_payload_fn(
                    task=task.to_dict(),
                    step_payload=step_payload,
                    execution_replan_count=state.get("execution_replan_count", 0) + 1,
                    feedback=f"步骤 {idx+1} [{tool}] 执行失败：{result_text or tool_result.error}。请尝试其他方法。",
                    trace=[f"{tool} failed, triggering replan"],
                    active_step_results=[],
                    active_tool_results_v2=[],
                    active_execution_trace=[],
                    active_artifacts=[],
                    active_sources=[],
                    active_retrieval_chunks=[],
                )
            self.stream_thought("> [结果] 执行完成\n")

        if task.cancel_requested:
            for pos in range(idx + 1, len(steps)):
                remain = steps[pos]
                if str(remain.status or "pending") == "pending":
                    remain.status = "skipped"
                    remain.cancel_requested = True
                    remain.error = "任务已取消"
                    self.safe_save_step(task.id, remain, pos)
            task.status = "canceled"
            task.final_answer = self.build_cancelled_result_text_fn()
            task.touch()
            self.safe_save_task(task)
            return self.build_post_execution_cancel_payload_fn(
                task=task.to_dict(),
                current_step_index=len(steps),
                step_payload=step_payload,
            )

        step_record = f"[{tool}] {instruction}：\n{self.truncate_step_result(result_text)}"

        return self.build_executor_return_payload_fn(
            task=task.to_dict(),
            step_results=[step_record],
            current_step_index=idx + 1,
            sources=new_sources,
            retrieval_quality_score=quality_score if tool == "RAG" else state.get("retrieval_quality_score", 0.0),
            retrieval_quality_detail=quality if tool == "RAG" else state.get("retrieval_quality_detail", {}),
            retrieval_chunks=chunks if tool == "RAG" else [],
            step_payload=step_payload,
            trace=[f"Executed {tool}"],
            remediation_count=remediation_count,
            remediation_stats=remediation_stats,
            unresolved_outcomes=unresolved_outcomes,
            active_step_results=active_step_results + [step_record],
            active_tool_results_v2=next_active_tool_results,
            active_execution_trace=next_active_execution_trace,
            active_artifacts=next_active_artifacts,
            active_sources=list(dict.fromkeys(active_sources + new_sources)),
            active_retrieval_chunks=active_retrieval_chunks + (chunks if tool == "RAG" else []),
        )
