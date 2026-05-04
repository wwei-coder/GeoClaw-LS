import operator
import json
import re
import uuid
from typing import TypedDict, Annotated, List, Dict, Any, Union, Optional
from langgraph.graph import StateGraph, END
from agent.executor import (
    AgentExecutor,
    assess_evidence_quality,
    build_remediation_decision,
    collect_remediation_metrics,
)
from agent.state import AgentTask, AgentStep, Artifact
from agent.runtime import RuntimePersistence
from core import prompts
from tools.registry import get_tool_registry
from utils.ollama_client import ask_ollama_async
from utils.logger import logger
from core.config import (
    GRAPH_REPLAN_MAX_ATTEMPTS,
    GRAPH_REPLAN_ON_LOW_QUALITY,
    GRAPH_REPLAN_LOW_QUALITY_THRESHOLD,
    GRAPH_REPLAN_REQUIRE_EXPANSION,
    GRAPH_STEP_RESULT_MAX_CHARS,
    ANSWER_CONFIDENCE_HIGH_THRESHOLD,
    ANSWER_CONFIDENCE_MEDIUM_THRESHOLD,
    ANSWER_CONFIDENCE_NO_KB_FLOOR,
    ANSWER_CONFIDENCE_NEED_KB_RETRIEVAL_WEIGHT,
    ANSWER_CONFIDENCE_NEED_KB_CONTEXT_WEIGHT,
    ANSWER_CONFIDENCE_REPLAN_PENALTY_STEP,
    ANSWER_CONFIDENCE_REPLAN_PENALTY_CAP
)
# 定义 Agent 状态
class AgentState(TypedDict):
    question: str
    file_id: str
    files: List[Dict[str, Any]]
    plan: Dict[str, Any]
    steps: List[Dict[str, Any]]
    task: Dict[str, Any]
    task_id: str
    run_mode: str
    resumed_from: str
    cancel_requested: bool
    current_step_index: int
    step_results: Annotated[List[str], operator.add]
    final_answer: str
    tool_results_v2: Annotated[List[Dict[str, Any]], operator.add]
    execution_trace: Annotated[List[Dict[str, Any]], operator.add]
    artifacts: Annotated[List[Dict[str, Any]], operator.add]
    sources: Annotated[List[str], lambda x, y: list(set(x) | set(y))]
    context_score: float
    force_tool: Union[str, None]
    need_kb: bool
    trace: Annotated[List[str], operator.add]
    error: str
    replanning_needed: bool
    # 新增字段：用于反思逻辑
    review_count: int 
    feedback: str
    is_satisfactory: bool
    retrieval_quality_score: float
    retrieval_quality_detail: Dict[str, Any]
    retrieval_chunks: Annotated[List[Dict[str, Any]], operator.add]
    execution_replan_count: int
    answer_confidence_score: float
    answer_confidence_label: str
    remediation_count: int
    remediation_stats: Dict[str, Any]
    unresolved_outcomes: Annotated[List[Dict[str, Any]], operator.add]
    remediation_metrics: Dict[str, Any]
    evidence_quality_assessment: Dict[str, Any]

class GraphAgent:
    """LangGraph workflow runtime implementation (phase-5 keeps structure stable)."""

    def __init__(self, agent_core: Any):
        self.core = agent_core
        self.executor = AgentExecutor(get_tool_registry())
        self.persistence = RuntimePersistence(agent_core)
        self.app_async = self._build_async_graph()

    def _task_from_state(self, state: AgentState) -> AgentTask:
        task_payload = state.get("task") or {}
        steps: List[AgentStep] = []
        for item in task_payload.get("steps", []) or []:
            if isinstance(item, AgentStep):
                steps.append(item)
                continue
            steps.append(
                AgentStep(
                    id=str(item.get("id", "")),
                    tool_name=str(item.get("tool_name", "LLM")),
                    instruction=str(item.get("instruction", "")),
                    status=str(item.get("status", "pending")),
                    retry_of=item.get("retry_of"),
                    attempts=int(item.get("attempts") or 1),
                    cancel_requested=bool(item.get("cancel_requested", False)),
                    input=dict(item.get("input", {}) or {}),
                    result=dict(item.get("result", {}) or {}),
                    error=item.get("error"),
                    started_at=item.get("started_at"),
                    finished_at=item.get("finished_at"),
                    metadata=dict(item.get("metadata", {}) or {}),
                    artifacts=[
                        Artifact.from_dict(a)
                        for a in (item.get("artifacts", []) or [])
                    ],
                )
            )
        task_artifacts = [Artifact.from_dict(a) for a in (task_payload.get("artifacts", []) or [])]
        return AgentTask(
            id=str(task_payload.get("id") or state.get("task_id") or ""),
            user_query=str(task_payload.get("user_query") or state.get("question") or ""),
            status=str(task_payload.get("status", "running")),
            run_mode=str(task_payload.get("run_mode") or state.get("run_mode") or "sync"),
            cancel_requested=bool(task_payload.get("cancel_requested", state.get("cancel_requested", False))),
            resumed_from=task_payload.get("resumed_from") or state.get("resumed_from") or None,
            steps=steps,
            final_answer=str(task_payload.get("final_answer", "")),
            artifacts=task_artifacts,
            metadata=dict(task_payload.get("metadata", {}) or {}),
            created_at=str(task_payload.get("created_at", "")),
            updated_at=str(task_payload.get("updated_at", "")),
        )

    def _safe_save_task(self, task: AgentTask) -> None:
        self.persistence.save_task(task)

    def _safe_save_step(self, task_id: str, step: AgentStep, position: int) -> None:
        self.persistence.save_step(task_id=task_id, step=step, position=position)

    def _safe_save_artifact(self, task_id: str, artifact: Artifact) -> None:
        self.persistence.save_artifact(task_id=task_id, artifact=artifact)

    def _normalize_artifacts_with_task(self, task_id: str, artifacts: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in artifacts or []:
            if isinstance(item, Artifact):
                artifact = item
                artifact.task_id = task_id
            else:
                payload = dict(item or {})
                payload["task_id"] = task_id
                artifact = Artifact.from_dict(payload)
            normalized.append(artifact.to_dict())
        return normalized

    def _derive_task_status(self, task: AgentTask, final_answer: str) -> str:
        if task.cancel_requested:
            return "canceled"
        if not final_answer.strip():
            return "failed"
        step_statuses = {str((s.status or "")).lower() for s in (task.steps or [])}
        if "failed" in step_statuses:
            return "partial"
        return "success"

    def _is_cancel_requested(self) -> bool:
        event = getattr(self.core, "_active_cancel_event", None)
        if event is None:
            return False
        checker = getattr(event, "is_set", None)
        if checker is None:
            return False
        return bool(checker())

    def _sync_legacy_steps(self, task: AgentTask) -> List[Dict[str, Any]]:
        return [step.to_legacy_step() for step in (task.steps or [])]

    def _build_async_graph(self):
        return self._create_workflow(
            planner=self._node_planner_async,
            decision=self._node_decision_async,
            executor=self._node_executor_async,
            solver=self._node_solver_async,
            reviewer=self._node_reviewer_async
        )

    def _is_data_analysis_request(self, question: str, file_id: str) -> bool:
        text = (question or "").lower()
        if file_id:
            if "分析这个文件" in question or "分析文件" in question:
                return True
            if any(k in text for k in ("csv", "excel", "xlsx", "xls", "json", "txt", "file_id", "表格", "数据文件")):
                return True
        return any(k in question for k in ("分析这个文件", "分析数据", "分析表格"))

    def _create_workflow(self, planner, decision, executor, solver, reviewer):
        workflow = StateGraph(AgentState)

        # 定义节点
        workflow.add_node("planner", planner)
        workflow.add_node("decision", decision)
        workflow.add_node("executor", executor)
        workflow.add_node("solver", solver)
        workflow.add_node("reviewer", reviewer)

        # 定义边
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "decision")
        workflow.add_edge("decision", "executor")
        
        # 循环逻辑
        workflow.add_conditional_edges(
            "executor",
            self._check_next_step,
            {
                "continue": "executor",
                "done": "solver",
                "replan": "planner"
            }
        )
        
        # Solver -> Reviewer -> (End or Planner)
        workflow.add_edge("solver", "reviewer")
        workflow.add_conditional_edges(
            "reviewer",
            self._check_review_result,
            {
                "pass": END,
                "fail": "planner"
            }
        )

        return workflow.compile()

    # ---------- Nodes (Async) ----------

    async def _node_planner_async(self, state: AgentState) -> Dict[str, Any]:
        question = state["question"]
        feedback = state.get("feedback", "")
        review_count = state.get("review_count", 0)
        
        if feedback:
             if state.get("replanning_needed", False):
                 self._stream_thought(f"\n> [动态调整] 执行受阻，重新规划，原因：{feedback}...\n")
                 question = f"用户问题：{question}\n\n执行过程中遇到问题：{feedback}\n请重新规划任务，尝试其他方法。"
             else:
                 self._stream_thought(f"\n> [反思] 第 {review_count} 次修正，原因：{feedback}...\n")
                 question = f"用户问题：{question}\n\n之前的回答未通过审核，建议：{feedback}\n请重新规划任务。"
        else:
             self._stream_thought("\n> [思考] 正在规划任务步骤...\n")

        try:
            planner_execution_trace: List[Dict[str, Any]] = []
            planner_text_trace: List[str] = []
            brain = getattr(self.core, "brain", None)
            if brain is not None:
                brain_plan = await brain.plan(question)
                plan = dict(brain_plan.raw_plan or {})
                plan["steps"] = list(brain_plan.steps or plan.get("steps", []) or [])
                plan["intent"] = str(brain_plan.intent or plan.get("intent") or "mixed")
                plan["need_evidence"] = bool(brain_plan.need_evidence)
                plan["risk_level"] = str(brain_plan.risk_level or plan.get("risk_level") or "low")
                plan["answer_requirements"] = list(brain_plan.answer_requirements or plan.get("answer_requirements", []) or [])
                plan["reasoning_trace"] = list(brain_plan.reasoning_trace or plan.get("reasoning_trace", []) or [])
                trace_text = brain_plan.trace or f"Planner: {len(plan.get('steps', []))} steps"
                for item in (brain_plan.reasoning_trace or []):
                    if not isinstance(item, dict):
                        continue
                    trace_summary = str(item.get("summary") or "").strip()
                    if not trace_summary:
                        continue
                    trace_type = str(item.get("type") or "review_summary").strip()
                    planner_execution_trace.append(
                        {"phase": "planner", "type": trace_type, "summary": trace_summary}
                    )
                    planner_text_trace.append(trace_summary)
                for step in (plan.get("steps", []) or []):
                    if not isinstance(step, dict):
                        continue
                    planner_text_trace.extend(self._summarize_step_trace(step))
            else:
                res = await self.core.planner.ainvoke({"question": question})
                plan = res["plan"]
                trace_text = res.get("trace", "Planner: Done")
            task = self.executor.build_task(
                user_query=state["question"],
                plan_steps=plan.get("steps", []),
                task_id=(state.get("task_id") or ""),
                run_mode=str(state.get("run_mode") or "sync"),
                resumed_from=state.get("resumed_from") or None,
            )
            task.metadata["answer_requirements"] = list(plan.get("answer_requirements", []) or [])
            task.status = "running"
            task.touch()
            self._safe_save_task(task)
            return {
                "plan": plan,
                "task": task.to_dict(),
                "task_id": task.id,
                "steps": self._sync_legacy_steps(task),
                "current_step_index": 0,
                "step_results": [],
                "tool_results_v2": [],
                "execution_trace": planner_execution_trace,
                "artifacts": [],
                "cancel_requested": False,
                "replanning_needed": False,
                "feedback": "",
                "trace": [trace_text] + planner_text_trace,
            }
        except Exception as e:
            return {"error": str(e), "trace": [f"Planner Error: {e}"]}

    async def _node_decision_async(self, state: AgentState) -> Dict[str, Any]:
        self._stream_thought("\n> [思考] 正在评估上下文和决策...\n")
        brain = getattr(self.core, "brain", None)
        if brain is not None:
            brain_decision = await brain.decide(question=state["question"], plan=state["plan"])
            force_tool = brain_decision.force_tool
            final_use_kb = brain_decision.need_kb
            context_score = brain_decision.context_score
            trace_text = brain_decision.reason or f"Decision: use_kb={final_use_kb}, force={force_tool}"
        else:
            res = await self.core.decision.ainvoke({
                "question": state["question"],
                "plan": state["plan"]
            })
            force_tool = res["force_tool"]
            final_use_kb = res["final_use_kb"]
            context_score = res["context_score"]
            trace_text = res.get("trace", "Decision: Done")
        current_steps = list(state["steps"])

        if force_tool == "CALCULATOR":
             if not any(s["tool"] == "CALCULATOR" for s in current_steps):
                 current_steps = [{"tool": "CALCULATOR", "task": state["question"]}]
        elif final_use_kb and not any(s["tool"] == "RAG" for s in current_steps):
             current_steps.insert(0, {"tool": "RAG", "task": state["question"]}) 

        if self._is_data_analysis_request(state["question"], state.get("file_id", "")):
            has_data_tool = any(str(s.get("tool", "")).upper() in {"DATA_PROFILE", "FILE_INSPECTOR"} for s in current_steps)
            if not has_data_tool:
                data_task = state["question"]
                if state.get("file_id"):
                    data_task = f"{data_task}\nfile_id: {state['file_id']}"
                current_steps = [
                    {"tool": "FILE_INSPECTOR", "task": data_task},
                    {"tool": "DATA_PROFILE", "task": data_task},
                ]

        task = self._task_from_state(state)
        task = self.executor.sync_task_steps(task, current_steps)
        self._safe_save_task(task)
        for pos, step in enumerate(task.steps):
            self._safe_save_step(task.id, step, pos)
        return {
            "context_score": context_score,
            "force_tool": force_tool,
            "need_kb": final_use_kb,
            "steps": self._sync_legacy_steps(task),
            "task": task.to_dict(),
            "trace": [trace_text]
        }

    async def _node_executor_async(self, state: AgentState) -> Dict[str, Any]:
        idx = state["current_step_index"]
        task = self._task_from_state(state)
        steps = task.steps
        cancel_now = self._is_cancel_requested()
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
                    self._safe_save_step(task.id, remain, pos)
            task.status = "canceled"
            task.final_answer = "任务已取消。"
            task.touch()
            self._safe_save_task(task)
            return {
                "task": task.to_dict(),
                "current_step_index": len(steps),
                "cancel_requested": True,
                "trace": ["Task canceled"],
            }

        step = steps[idx]
        tool = step.tool_name
        instruction = step.instruction
        
        self._stream_thought(f"\n> [思考] 步骤 {idx+1}: 使用 {tool}...\n")

        result_text = ""
        new_sources = []
        chunks = []
        quality = {}
        quality_score = state.get("retrieval_quality_score", 0.0)
        remediation_count = int(state.get("remediation_count", 0) or 0)
        remediation_stats = self._normalize_remediation_stats(state.get("remediation_stats"))
        unresolved_outcomes = list(state.get("unresolved_outcomes", []) or [])
        
        if tool == "RAG":
            self._stream_thought("> [执行] 正在检索知识库...\n")
        else:
            self._stream_thought(f"> [执行] 正在运行 {tool}...\n")

        updated_step, tool_result, trace_item = await self.executor.execute_step(
            step,
            self.core,
            cancellation_event=getattr(self.core, "_active_cancel_event", None),
            fail_fast=False,
        )
        task.steps[idx] = updated_step
        if updated_step.cancel_requested:
            task.cancel_requested = True
        task.touch()
        self._safe_save_task(task)
        self._safe_save_step(task.id, updated_step, idx)
        normalized_artifacts = self._normalize_artifacts_with_task(task.id, list(tool_result.artifacts or []))
        if normalized_artifacts:
            for item in normalized_artifacts:
                artifact = Artifact.from_dict(item)
                task.artifacts.append(artifact)
                self._safe_save_artifact(task.id, artifact)
        self._safe_save_task(task)

        result_text = tool_result.content or ""
        outcome = dict((tool_result.metadata or {}).get("outcome_assessment") or {})
        issue_type = str(outcome.get("issue_type") or "none")
        retryable = bool(outcome.get("retryable", False))
        outcome_feedback = self._format_outcome_feedback(outcome)
        remediation_stats = self._advance_remediation_stats(remediation_stats, tool, issue_type)
        remediation_decision = build_remediation_decision(
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
        self._safe_save_step(task.id, updated_step, idx)

        action = dict(decision_payload.get("action") or {})
        action_type = str(action.get("action_type") or "none")
        action_allowed = bool(action.get("allowed", False))
        suppress_default_replan = False
        if remediation_decision.should_remediate:
            if action_allowed and action_type in {"retry_same_tool", "switch_tool"}:
                retry_tool = str(action.get("retry_tool") or tool).upper().strip() or tool
                retry_task = str(action.get("retry_task") or instruction).strip() or instruction
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
                self._safe_save_task(task)
                for pos in range(idx + 1, len(task.steps)):
                    self._safe_save_step(task.id, task.steps[pos], pos)
                self._stream_thought(f"> [补救] 已创建自动重试步骤：{retry_tool}\n")
                return {
                    "task": task.to_dict(),
                    "steps": self._sync_legacy_steps(task),
                    "step_results": [f"[{tool}] {instruction}：\n{self._truncate_step_result(result_text)}"],
                    "current_step_index": idx + 1,
                    "sources": new_sources,
                    "retrieval_quality_score": quality_score if tool == "RAG" else state.get("retrieval_quality_score", 0.0),
                    "retrieval_quality_detail": quality if tool == "RAG" else state.get("retrieval_quality_detail", {}),
                    "retrieval_chunks": chunks if tool == "RAG" else [],
                    "tool_results_v2": [tool_result.to_dict()],
                    "execution_trace": [trace_item] if trace_item else [],
                    "artifacts": normalized_artifacts,
                    "trace": [remediation_decision.trace_summary or f"{tool} remediation retry scheduled"],
                    "remediation_count": remediation_count,
                    "remediation_stats": remediation_stats,
                    "unresolved_outcomes": unresolved_outcomes,
                }
            if action_allowed and action_type == "replan":
                step_counts = dict(remediation_stats.get("step_remediation_counts") or {})
                step_counts[updated_step.id] = int(step_counts.get(updated_step.id, 0) or 0) + 1
                remediation_stats["step_remediation_counts"] = step_counts
                remediation_count += 1
                self._stream_thought("> [补救] 触发受控重规划。\n")
                return {
                    "task": task.to_dict(),
                    "execution_trace": [trace_item] if trace_item else [],
                    "tool_results_v2": [tool_result.to_dict()],
                    "artifacts": normalized_artifacts,
                    "replanning_needed": True,
                    "execution_replan_count": state.get("execution_replan_count", 0) + 1,
                    "feedback": remediation_decision.trace_summary or f"步骤 {idx+1} [{tool}] 触发受控重规划。",
                    "trace": ["controlled remediation replan"],
                    "remediation_count": remediation_count,
                    "remediation_stats": remediation_stats,
                    "unresolved_outcomes": unresolved_outcomes,
                }
            if action_type in {"ask_user", "degrade_answer"}:
                suppress_default_replan = True
                unresolved_outcomes.append(
                    {
                        "tool_name": tool,
                        "issue_type": issue_type,
                        "summary": outcome.get("summary", ""),
                        "suggested_action": action.get("trace_summary") or outcome.get("suggested_action", ""),
                    }
                )
                result_text = outcome_feedback or remediation_decision.trace_summary or result_text
                self._stream_thought(f"> [补救] {action.get('trace_summary') or remediation_decision.trace_summary}\n")
        if retryable and issue_type != "none":
            self._stream_thought(f"> [闭环] {tool} 可重试：{outcome_feedback}\n")
        if tool == "RAG":
            quality = dict((tool_result.metadata or {}).get("retrieval_quality", {}) or {})
            chunks = list((tool_result.metadata or {}).get("kb_chunks", []) or [])
            quality_score = float(quality.get("score", 0.0) or 0.0)
            for c in chunks:
                if c.get("doc_name"):
                    new_sources.append(c["doc_name"])
            if chunks and not suppress_default_replan:
                self._stream_thought(f"> [结果] 找到 {len(chunks)} 条相关资料\n")
                allow_low_quality_replan = (
                    GRAPH_REPLAN_ON_LOW_QUALITY
                    and quality_score < GRAPH_REPLAN_LOW_QUALITY_THRESHOLD
                    and (
                        (not GRAPH_REPLAN_REQUIRE_EXPANSION)
                        or bool(quality.get("expanded", False))
                    )
                )
                if allow_low_quality_replan:
                    replan_count = state.get("execution_replan_count", 0)
                    if replan_count < GRAPH_REPLAN_MAX_ATTEMPTS:
                        self._stream_thought("> [结果] 检索质量偏低，正在触发重新规划...\n")
                        return {
                            "task": task.to_dict(),
                            "execution_trace": [trace_item] if trace_item else [],
                            "tool_results_v2": [tool_result.to_dict()],
                            "artifacts": normalized_artifacts,
                            "replanning_needed": True,
                            "execution_replan_count": replan_count + 1,
                            "retrieval_quality_score": quality_score,
                            "retrieval_quality_detail": quality,
                            "feedback": (
                                f"步骤 {idx+1} [RAG] 检索质量偏低："
                                f"score={quality_score:.2f}, hits={quality.get('hit_count', 0)}, "
                                f"avg_similarity={quality.get('avg_similarity', 0)}。请改用其他检索策略或工具。"
                            ),
                            "trace": ["RAG low-quality, triggering replan"],
                        }
            elif not suppress_default_replan:
                self._stream_thought("> [结果] 未找到资料，正在触发重新规划...\n")
                return {
                    "task": task.to_dict(),
                    "execution_trace": [trace_item] if trace_item else [],
                    "tool_results_v2": [tool_result.to_dict()],
                    "artifacts": normalized_artifacts,
                    "replanning_needed": True,
                    "execution_replan_count": state.get("execution_replan_count", 0) + 1,
                    "retrieval_quality_score": quality_score,
                    "retrieval_quality_detail": quality,
                    "feedback": f"步骤 {idx+1} [RAG] 未找到任何相关资料，请尝试使用搜索引擎或其他工具。",
                    "trace": ["RAG failed, triggering replan"],
                }
        else:
            if issue_type == "missing_file":
                self._stream_thought("> [闭环] 文件上下文不足，保留提示并继续汇总回答。\n")
                result_text = outcome_feedback or "缺少可用文件，请先上传文件并提供 file_id。"
            elif issue_type == "invalid_input":
                self._stream_thought("> [闭环] 计算输入不合法，保留提示并继续汇总回答。\n")
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
                self._stream_thought("> [结果] 执行失败或为空，正在触发重新规划...\n")
                return {
                    "task": task.to_dict(),
                    "execution_trace": [trace_item] if trace_item else [],
                    "tool_results_v2": [tool_result.to_dict()],
                    "artifacts": normalized_artifacts,
                    "replanning_needed": True,
                    "execution_replan_count": state.get("execution_replan_count", 0) + 1,
                    "feedback": f"步骤 {idx+1} [{tool}] 执行失败：{result_text or tool_result.error}。请尝试其他方法。",
                    "trace": [f"{tool} failed, triggering replan"],
                }
            self._stream_thought("> [结果] 执行完成\n")

        if task.cancel_requested:
            for pos in range(idx + 1, len(steps)):
                remain = steps[pos]
                if str(remain.status or "pending") == "pending":
                    remain.status = "skipped"
                    remain.cancel_requested = True
                    remain.error = "任务已取消"
                    self._safe_save_step(task.id, remain, pos)
            task.status = "canceled"
            task.final_answer = "任务已取消。"
            task.touch()
            self._safe_save_task(task)
            return {
                "task": task.to_dict(),
                "current_step_index": len(steps),
                "execution_trace": [trace_item] if trace_item else [],
                "tool_results_v2": [tool_result.to_dict()],
                "artifacts": normalized_artifacts,
                "cancel_requested": True,
                "trace": ["Task canceled"],
            }

        step_record = f"[{tool}] {instruction}：\n{self._truncate_step_result(result_text)}"
        
        return {
            "task": task.to_dict(),
            "step_results": [step_record],
            "current_step_index": idx + 1,
            "sources": new_sources,
            "retrieval_quality_score": quality_score if tool == "RAG" else state.get("retrieval_quality_score", 0.0),
            "retrieval_quality_detail": quality if tool == "RAG" else state.get("retrieval_quality_detail", {}),
            "retrieval_chunks": chunks if tool == "RAG" else [],
            "tool_results_v2": [tool_result.to_dict()],
            "execution_trace": [trace_item] if trace_item else [],
            "artifacts": normalized_artifacts,
            "trace": [f"Executed {tool}"],
            "remediation_count": remediation_count,
            "remediation_stats": remediation_stats,
            "unresolved_outcomes": unresolved_outcomes,
        }

    async def _node_solver_async(self, state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            task = self._task_from_state(state)
            task.status = "failed"
            task.final_answer = f"系统运行出错：{state['error']}"
            task.touch()
            self._safe_save_task(task)
            return {
                "task": task.to_dict(),
                "task_id": task.id,
                "final_answer": task.final_answer
            }
        if state.get("cancel_requested", False):
            task = self._task_from_state(state)
            task.cancel_requested = True
            task.status = "canceled"
            if not task.final_answer:
                task.final_answer = "任务已取消。"
            task.touch()
            self._safe_save_task(task)
            store = getattr(self.core, "task_store", None)
            if store:
                try:
                    store.update_task_status(task.id, task.status, final_answer=task.final_answer)
                except Exception as exc:
                    logger.warning(f"[TaskStore] 更新取消状态失败（已忽略）: {exc}")
            return {
                "task": task.to_dict(),
                "task_id": task.id,
                "final_answer": task.final_answer,
                "answer_confidence_score": 0.0,
                "answer_confidence_label": "低",
            }
        
        self._stream_thought("\n> [思考] 正在汇总回答...\n")
        
        cb = getattr(self.core, "_current_stream_callback", None)
        
        brain = getattr(self.core, "brain", None)
        if brain is not None:
            brain_answer = await brain.synthesize(
                question=state["question"],
                step_results=state["step_results"],
                kb_chunks=[],
                sources=state["sources"],
                canceled=False,
                stream_callback=cb,
            )
            synthesized_answer = brain_answer.answer
        else:
            syn_res = await self.core.synthesis.ainvoke({
                "question": state["question"],
                "step_results": state["step_results"],
                "kb_chunks": [],
                "sources": state["sources"],
                "canceled": False,
                "stream_callback": cb
            })
            synthesized_answer = syn_res["final_answer"]
        confidence_score, confidence_label = self._grade_answer_confidence(state)
        final_answer = f"【系统可信度（证据）：{confidence_label}】\n{synthesized_answer}"
        if confidence_label == "低":
            final_answer += "\n\n【需补充信息】当前证据支撑较弱，建议补充更具体的问题条件、关键词或权威资料来源。"
        unresolved = list(state.get("unresolved_outcomes", []) or [])
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
        
        task = self._task_from_state(state)
        remediation_metrics = collect_remediation_metrics(
            task=task,
            state=state,
            execution_trace=list(state.get("execution_trace", []) or []),
            steps=task.steps,
        )
        evidence_assessment = assess_evidence_quality(
            answer=synthesized_answer,
            sources=list(state.get("sources", []) or []),
            retrieval_chunks=list(state.get("retrieval_chunks", []) or []),
            need_evidence=bool((state.get("plan") or {}).get("need_evidence", state.get("need_kb", False))),
            confidence_label=confidence_label,
        )
        task.metadata["remediation_metrics"] = remediation_metrics
        task.metadata["evidence_quality_assessment"] = evidence_assessment
        if evidence_assessment.get("issue_type") not in {"none", ""}:
            final_answer += (
                "\n\n【证据校验摘要】"
                f"{evidence_assessment.get('summary', '')}"
            )
        task.final_answer = final_answer
        task.status = self._derive_task_status(task, final_answer)
        task.touch()
        self._safe_save_task(task)
        store = getattr(self.core, "task_store", None)
        if store:
            try:
                store.update_task_status(task.id, task.status, final_answer=final_answer)
            except Exception as exc:
                logger.warning(f"[TaskStore] 更新任务最终状态失败（已忽略）: {exc}")
        return {
            "task": task.to_dict(),
            "task_id": task.id,
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

    async def _node_reviewer_async(self, state: AgentState) -> Dict[str, Any]:
        count = state.get("review_count", 0)
        evidence_assessment = dict(state.get("evidence_quality_assessment") or {})
        evidence_issue = str(evidence_assessment.get("issue_type") or "none")
        if evidence_issue not in {"none", ""} and bool(evidence_assessment.get("need_evidence", False)):
            if count >= 2:
                return {"is_satisfactory": True}
            return {
                "is_satisfactory": False,
                "feedback": f"证据校验提示：{evidence_assessment.get('summary', '证据不足。')}",
                "review_count": count + 1,
            }
        missing_requirements = self._check_answer_requirements(state)
        if missing_requirements:
            if count >= 2:
                return {"is_satisfactory": True}
            return {
                "is_satisfactory": False,
                "feedback": f"回答未满足要求：{'; '.join(missing_requirements)}",
                "review_count": count + 1,
            }
        brain = getattr(self.core, "brain", None)
        if brain is not None:
            self._stream_thought("\n> [思考] 正在审核回答质量...\n")
            brain_review = await brain.review(
                question=state["question"],
                answer=state["final_answer"],
                review_count=count,
            )
            if not brain_review.is_satisfactory:
                self._stream_thought(f"> [审核未通过] -> {brain_review.feedback}\n")
                return {
                    "is_satisfactory": False,
                    "feedback": brain_review.feedback,
                    "review_count": brain_review.review_count,
                }
            self._stream_thought("> [审核通过] 回答质量达标\n")
            return {"is_satisfactory": True}

        if count >= 2:
            return {"is_satisfactory": True}

        self._stream_thought("\n> [思考] 正在审核回答质量...\n")
        prompt = prompts.REVIEW_PROMPT.format(
            question=state["question"],
            answer=state["final_answer"]
        )
        try:
            raw = (await ask_ollama_async(prompt)).strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            res = json.loads(raw)
            is_ok = (res.get("status") == "PASS")
            if not is_ok:
                self._stream_thought(f"> [审核未通过] {res.get('reason')} -> {res.get('suggestion')}\n")
                return {
                    "is_satisfactory": False,
                    "feedback": res.get("suggestion"),
                    "review_count": count + 1
                }
            self._stream_thought("> [审核通过] 回答质量达标\n")
            return {"is_satisfactory": True}
        except Exception as e:
            err_text = str(e)
            match = re.search(r"状态码\s+(\d+)", err_text)
            status_code = int(match.group(1)) if match else None
            if status_code in {408, 429, 500, 502, 503, 504}:
                logger.info(f"[Reviewer] 审核请求临时失败（HTTP {status_code}），已降级放行")
            else:
                logger.warning(f"[Reviewer] 异步审核异常，已降级放行: {e}")
            return {"is_satisfactory": True}

    def _check_next_step(self, state: AgentState) -> str:
        if state.get("replanning_needed", False):
            return "replan"
        if state["current_step_index"] < len(state["steps"]):
            return "continue"
        return "done"

    def _check_review_result(self, state: AgentState) -> str:
        if state.get("is_satisfactory", True):
            return "pass"
        return "fail"

    def _stream_thought(self, text: str):
        """Helper to stream thought trace to UI"""
        cb = getattr(self.core, "_current_stream_callback", None)
        if cb:
            cb(text)

    def _truncate_step_result(self, text: str) -> str:
        if not text:
            return ""
        if len(text) <= GRAPH_STEP_RESULT_MAX_CHARS:
            return text
        keep = max(1, GRAPH_STEP_RESULT_MAX_CHARS // 2)
        return text[:keep] + "\n...（步骤结果已压缩）...\n" + text[-keep:]

    def _normalize_remediation_stats(self, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = dict(raw or {})
        return {
            "tool_failure_streak": dict(data.get("tool_failure_streak") or {}),
            "issue_counts": dict(data.get("issue_counts") or {}),
            "step_remediation_counts": dict(data.get("step_remediation_counts") or {}),
            "llm_empty_retry_count": int(data.get("llm_empty_retry_count", 0) or 0),
        }

    def _advance_remediation_stats(self, stats: Dict[str, Any], tool: str, issue_type: str) -> Dict[str, Any]:
        next_stats = self._normalize_remediation_stats(stats)
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

    def _format_outcome_feedback(self, outcome: Dict[str, Any]) -> str:
        summary = str(outcome.get("summary") or "").strip()
        action = str(outcome.get("suggested_action") or "").strip()
        if summary and action:
            return f"{summary} 建议：{action}"
        return summary or action

    def _check_answer_requirements(self, state: AgentState) -> List[str]:
        plan = dict(state.get("plan") or {})
        requirements = [str(item).strip() for item in (plan.get("answer_requirements", []) or []) if str(item).strip()]
        if not requirements:
            return []
        answer = str(state.get("final_answer") or "")
        sources = list(state.get("sources", []) or [])
        missing: List[str] = []
        for req in requirements:
            if "中文" in req:
                has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in answer)
                if not has_chinese:
                    missing.append(req)
            elif "引用资料来源" in req:
                if not (("来源" in answer) or bool(sources)):
                    missing.append(req)
            elif "区分资料支持和模型推断" in req:
                has_split = ("资料支持" in answer and "推断" in answer) or ("资料未明确提及" in answer and "推断" in answer)
                if not has_split:
                    missing.append(req)
        return missing

    def _summarize_step_trace(self, step: Dict[str, Any]) -> List[str]:
        parts: List[str] = []
        tool = str(step.get("tool", "")).strip()
        reason = str(step.get("reason", "")).strip()
        expected_output = str(step.get("expected_output", "")).strip()
        fallback = str(step.get("fallback", "")).strip()
        if reason:
            parts.append(f"选择 {tool or '工具'}：{reason}")
        if expected_output:
            parts.append(f"预期输出：{expected_output}")
        if fallback:
            parts.append(f"回退策略：{fallback}")
        return parts

    def _grade_answer_confidence(self, state: AgentState):
        need_kb = bool(state.get("need_kb", False))
        context_score = float(state.get("context_score", 0.0) or 0.0)
        retrieval_quality = float(state.get("retrieval_quality_score", 0.0) or 0.0)
        replan_penalty = min(
            ANSWER_CONFIDENCE_REPLAN_PENALTY_CAP,
            ANSWER_CONFIDENCE_REPLAN_PENALTY_STEP * max(0, int(state.get("execution_replan_count", 0)))
        )

        if need_kb:
            score = (
                ANSWER_CONFIDENCE_NEED_KB_RETRIEVAL_WEIGHT * retrieval_quality
                + ANSWER_CONFIDENCE_NEED_KB_CONTEXT_WEIGHT * context_score
                - replan_penalty
            )
        else:
            score = max(ANSWER_CONFIDENCE_NO_KB_FLOOR, context_score) - replan_penalty
        score = max(0.0, min(1.0, score))

        if score >= ANSWER_CONFIDENCE_HIGH_THRESHOLD:
            label = "高"
        elif score >= ANSWER_CONFIDENCE_MEDIUM_THRESHOLD:
            label = "中"
        else:
            label = "低"
        return score, label

    #Public Interface
    async def run_async(
        self,
        question: str,
        file_id: str = "",
        files: Optional[List[Dict[str, Any]]] = None,
        task_id: str = "",
        run_mode: str = "sync",
        resumed_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        inputs = {
            "question": question,
            "file_id": file_id or "",
            "files": list(files or []),
            "plan": {},
            "steps": [],
            "task": {},
            "task_id": task_id or "",
            "run_mode": run_mode or "sync",
            "resumed_from": resumed_from or "",
            "cancel_requested": False,
            "current_step_index": 0,
            "step_results": [],
            "final_answer": "",
            "tool_results_v2": [],
            "execution_trace": [],
            "artifacts": [],
            "sources": [],
            "context_score": 0.0,
            "force_tool": None,
            "need_kb": False,
            "trace": [],
            "error": "",
            "replanning_needed": False,
            "review_count": 0,
            "feedback": "",
            "is_satisfactory": True,
            "retrieval_quality_score": 0.0,
            "retrieval_quality_detail": {},
            "retrieval_chunks": [],
            "execution_replan_count": 0,
            "answer_confidence_score": 0.0,
            "answer_confidence_label": "",
            "remediation_count": 0,
            "remediation_stats": {
                "tool_failure_streak": {},
                "issue_counts": {},
                "step_remediation_counts": {},
                "llm_empty_retry_count": 0,
            },
            "unresolved_outcomes": [],
            "remediation_metrics": {},
            "evidence_quality_assessment": {},
        }
        
        final_state = await self.app_async.ainvoke(inputs)
        
        return {
            "answer": final_state.get("final_answer", ""),
            "confidence": final_state.get("answer_confidence_score", final_state.get("context_score", 0.0)),
            "answer_confidence_label": final_state.get("answer_confidence_label", ""),
            "sources": final_state.get("sources", []),
            "retrieval_quality": final_state.get("retrieval_quality_detail", {}),
            "retrieval_chunks": final_state.get("retrieval_chunks", []),
            "task_id": final_state.get("task_id", (final_state.get("task", {}) or {}).get("id", "")),
            "task": final_state.get("task", {}),
            "steps": (final_state.get("task", {}) or {}).get("steps", []),
            "execution_trace": final_state.get("execution_trace", []),
            "tool_results_v2": final_state.get("tool_results_v2", []),
            "artifacts": final_state.get("artifacts", (final_state.get("task", {}) or {}).get("artifacts", [])),
            "trace": "\n".join(final_state.get("trace", [])),
        }
