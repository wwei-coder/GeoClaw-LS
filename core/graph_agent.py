"""LangGraph wiring facade for the current transition stage.

Keep graph state, routing semantics and node business logic moving toward
``agent/workflow/*``. This module should stay focused on graph wiring,
composition and runtime bridging.
"""

import operator
import time
from typing import TypedDict, Annotated, List, Dict, Any, Union, Optional
from langgraph.graph import StateGraph, END
from agent.executor import (
    AgentExecutor,
    assess_evidence_quality,
    build_remediation_decision,
    collect_remediation_metrics,
)
from agent.policies import (
    advance_remediation_stats,
    check_answer_requirements,
    check_answer_relevance,
    derive_task_status,
    format_outcome_feedback,
    grade_answer_confidence,
    normalize_remediation_stats,
    summarize_step_trace,
)
from agent.state import AgentTask, AgentStep, Artifact
from agent.runtime import RuntimePersistence
from agent.brain.prompt_catalog import get_prompt_catalog
from agent.workflow.nodes import DecisionNode, ExecutorNode, PlannerNode, ReviewerNode, SolverNode
from agent.workflow import (
    build_ask_user_or_degrade_result_text,
    append_evidence_summary_if_needed,
    build_cancelled_result_text,
    build_initial_state,
    build_confidence_prefixed_answer,
    build_executor_return_payload,
    build_post_execution_cancel_payload,
    build_pre_execution_cancel_payload,
    build_remediation_stream_text,
    build_replan_return_payload,
    build_replan_feedback,
    build_retry_task_instruction,
    build_retry_trace_text,
    build_step_execution_payload,
    build_solver_return_payload,
    build_task_metadata_update,
    build_unresolved_outcome_payload,
    check_next_step,
    check_review_result,
    is_data_analysis_request,
    normalize_artifacts_with_task,
    sync_legacy_steps,
    task_from_state,
    truncate_step_result,
)
from tools.registry import get_tool_registry
from utils.ollama_client import ask_ollama_async
from utils.logger import logger
from config_runtime import (
    GRAPH_REPLAN_MAX_ATTEMPTS,
    GRAPH_REPLAN_ON_LOW_QUALITY,
    GRAPH_REPLAN_LOW_QUALITY_THRESHOLD,
    GRAPH_REPLAN_REQUIRE_EXPANSION,
    GRAPH_REVIEW_REPLAN_MAX_ATTEMPTS,

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
    answer_revision_needed: bool
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
    active_step_results: List[str]
    active_tool_results_v2: List[Dict[str, Any]]
    active_execution_trace: List[Dict[str, Any]]
    active_artifacts: List[Dict[str, Any]]
    active_sources: List[str]
    active_retrieval_chunks: List[Dict[str, Any]]

class GraphAgent:
    """LangGraph workflow runtime implementation (phase-5 keeps structure stable)."""

    def __init__(self, agent_core: Any):
        self.core = agent_core
        self.executor = AgentExecutor(get_tool_registry())
        self.persistence = RuntimePersistence(agent_core)
        self.planner_node = PlannerNode(
            core=self.core,
            build_task=self.executor.build_task,
            stream_thought=self._stream_thought,
            summarize_step_trace=self._summarize_step_trace,
            safe_save_task=self._safe_save_task,
            safe_save_step=self._safe_save_step,
            clear_saved_steps=self._clear_saved_steps,
            sync_legacy_steps=self._sync_legacy_steps,
            logger=logger,
        )
        self.decision_node = DecisionNode(
            core=self.core,
            is_data_analysis_request=self._is_data_analysis_request,
            stream_thought=self._stream_thought,
            task_from_state=self._task_from_state,
            sync_task_steps=self.executor.sync_task_steps,
            safe_save_task=self._safe_save_task,
            safe_save_step=self._safe_save_step,
            sync_legacy_steps=self._sync_legacy_steps,
            logger=logger,
        )
        self.executor_node = ExecutorNode(
            core=self.core,
            executor=self.executor,
            task_from_state=self._task_from_state,
            safe_save_task=self._safe_save_task,
            safe_save_step=self._safe_save_step,
            safe_save_artifact=self._safe_save_artifact,
            normalize_artifacts_with_task=self._normalize_artifacts_with_task,
            artifact_from_dict=Artifact.from_dict,
            truncate_step_result=self._truncate_step_result,
            is_cancel_requested=self._is_cancel_requested,
            advance_remediation_stats=self._advance_remediation_stats,
            format_outcome_feedback=self._format_outcome_feedback,
            stream_thought=self._stream_thought,
            sync_legacy_steps=self._sync_legacy_steps,
            build_remediation_decision_fn=build_remediation_decision,
            build_step_execution_payload_fn=build_step_execution_payload,
            build_executor_return_payload_fn=build_executor_return_payload,
            build_replan_return_payload_fn=build_replan_return_payload,
            build_pre_execution_cancel_payload_fn=build_pre_execution_cancel_payload,
            build_post_execution_cancel_payload_fn=build_post_execution_cancel_payload,
            build_cancelled_result_text_fn=build_cancelled_result_text,
            build_retry_task_instruction_fn=build_retry_task_instruction,
            build_retry_trace_text_fn=build_retry_trace_text,
            build_replan_feedback_fn=build_replan_feedback,
            build_unresolved_outcome_payload_fn=build_unresolved_outcome_payload,
            build_ask_user_or_degrade_result_text_fn=build_ask_user_or_degrade_result_text,
            build_remediation_stream_text_fn=build_remediation_stream_text,
            graph_replan_on_low_quality=GRAPH_REPLAN_ON_LOW_QUALITY,
            graph_replan_low_quality_threshold=GRAPH_REPLAN_LOW_QUALITY_THRESHOLD,
            graph_replan_require_expansion=GRAPH_REPLAN_REQUIRE_EXPANSION,
            graph_replan_max_attempts=GRAPH_REPLAN_MAX_ATTEMPTS,
            logger=logger,
        )
        self.solver_node = SolverNode(
            core=self.core,
            task_from_state=self._task_from_state,
            grade_answer_confidence=self._grade_answer_confidence,
            derive_task_status=self._derive_task_status,
            safe_save_task=self._safe_save_task,
            safe_save_artifact=self._safe_save_artifact,
            normalize_artifacts_with_task=self._normalize_artifacts_with_task,
            stream_thought=self._stream_thought,
            collect_remediation_metrics_fn=collect_remediation_metrics,
            assess_evidence_quality_fn=assess_evidence_quality,
            build_confidence_prefixed_answer_fn=build_confidence_prefixed_answer,
            append_evidence_summary_if_needed_fn=append_evidence_summary_if_needed,
            build_task_metadata_update_fn=build_task_metadata_update,
            build_solver_return_payload_fn=build_solver_return_payload,
            logger=logger,
        )
        self.reviewer_node = ReviewerNode(
            core=self.core,
            task_from_state=self._task_from_state,
            safe_save_task=self._safe_save_task,
            check_answer_requirements=self._check_answer_requirements,
            check_answer_relevance=self._check_answer_relevance,
            stream_thought=self._stream_thought,
            review_prompt_template=get_prompt_catalog().get_review_prompt_template(),
            ask_async_fn=ask_ollama_async,
            review_replan_max_attempts=GRAPH_REVIEW_REPLAN_MAX_ATTEMPTS,
        )
        self.app_async = self._build_async_graph()

    def _task_from_state(self, state: AgentState) -> AgentTask:
        return task_from_state(state)

    def _safe_save_task(self, task: AgentTask) -> None:
        self.persistence.save_task(task)

    def _safe_save_step(self, task_id: str, step: AgentStep, position: int) -> None:
        self.persistence.save_step(task_id=task_id, step=step, position=position)

    def _safe_save_artifact(self, task_id: str, artifact: Artifact) -> None:
        self.persistence.save_artifact(task_id=task_id, artifact=artifact)

    def _clear_saved_steps(self, task_id: str) -> None:
        clear_fn = getattr(self.persistence, "clear_steps_for_task", None)
        if callable(clear_fn):
            clear_fn(task_id)

    def _normalize_artifacts_with_task(self, task_id: str, artifacts: List[Any]) -> List[Dict[str, Any]]:
        return normalize_artifacts_with_task(task_id, artifacts)

    def _derive_task_status(self, task: AgentTask, final_answer: str) -> str:
        return derive_task_status(
            cancel_requested=bool(task.cancel_requested),
            final_answer=final_answer,
            step_statuses=[str((s.status or "")) for s in (task.steps or [])],
        )

    def _is_cancel_requested(self) -> bool:
        event = getattr(self.core, "_active_cancel_event", None)
        if event is None:
            return False
        checker = getattr(event, "is_set", None)
        if checker is None:
            return False
        return bool(checker())

    def _sync_legacy_steps(self, task: AgentTask) -> List[Dict[str, Any]]:
        return sync_legacy_steps(task)

    def _build_async_graph(self):
        return self._create_workflow(
            planner=self._node_planner_async,
            decision=self._node_decision_async,
            executor=self._node_executor_async,
            solver=self._node_solver_async,
            reviewer=self._node_reviewer_async
        )

    def _is_data_analysis_request(self, question: str, file_id: str) -> bool:
        return is_data_analysis_request(question, file_id)

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
                "revise": "solver",
                "replan": "planner",
            }
        )

        return workflow.compile()

    # ---------- Nodes (Async) ----------

    async def _node_planner_async(self, state: AgentState) -> Dict[str, Any]:
        return await self.planner_node.run(state)

    async def _node_decision_async(self, state: AgentState) -> Dict[str, Any]:
        return await self.decision_node.run(state)

    async def _node_executor_async(self, state: AgentState) -> Dict[str, Any]:
        return await self.executor_node.run(state)

    async def _node_solver_async(self, state: AgentState) -> Dict[str, Any]:
        return await self.solver_node.run(state)

    async def _node_reviewer_async(self, state: AgentState) -> Dict[str, Any]:
        return await self.reviewer_node.run(state)

    def _check_next_step(self, state: AgentState) -> str:
        return check_next_step(state)

    def _check_review_result(self, state: AgentState) -> str:
        return check_review_result(state)

    def _stream_thought(self, text: str):
        """Helper to stream thought trace to UI"""
        cb = getattr(self.core, "_current_stream_callback", None)
        if cb:
            cb(text)

    def _truncate_step_result(self, text: str) -> str:
        return truncate_step_result(text)

    def _normalize_remediation_stats(self, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return normalize_remediation_stats(raw)

    def _advance_remediation_stats(self, stats: Dict[str, Any], tool: str, issue_type: str) -> Dict[str, Any]:
        return advance_remediation_stats(stats, tool, issue_type)

    def _format_outcome_feedback(self, outcome: Dict[str, Any]) -> str:
        return format_outcome_feedback(outcome)

    def _check_answer_requirements(self, state: AgentState) -> List[str]:
        return check_answer_requirements(
            plan=dict(state.get("plan") or {}),
            answer=str(state.get("final_answer") or ""),
            sources=list(state.get("active_sources", state.get("sources", [])) or []),
        )

    def _check_answer_relevance(self, state: AgentState) -> List[str]:
        return check_answer_relevance(
            question=str(state.get("question") or ""),
            answer=str(state.get("final_answer") or ""),
        )

    async def _apply_final_answer_memory_effects(self, question: str, final_state: Dict[str, Any]) -> None:
        final_answer = str(final_state.get("final_answer") or "").strip()
        if not final_answer or bool(final_state.get("cancel_requested", False)):
            return
        try:
            from agent.brain.synthesis_factory import get_memory_service

            await get_memory_service(self.core).apply_post_answer_effects_async(question, final_answer)
        except Exception as exc:
            logger.error(f"[Graph] final answer memory update failed: {exc}")

    def _summarize_step_trace(self, step: Dict[str, Any]) -> List[str]:
        return summarize_step_trace(step)

    def _grade_answer_confidence(self, state: AgentState):
        return grade_answer_confidence(
            need_kb=bool(state.get("need_kb", False)),
            context_score=float(state.get("context_score", 0.0) or 0.0),
            retrieval_quality=float(state.get("retrieval_quality_score", 0.0) or 0.0),
            execution_replan_count=int(state.get("execution_replan_count", 0) or 0),
        )

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
        started = time.monotonic()
        logger.info(
            "[Graph] run start task_id={} mode={} question_len={}",
            task_id or "",
            run_mode,
            len(question or ""),
        )
        inputs = build_initial_state(
            question=question,
            file_id=file_id,
            files=files,
            task_id=task_id,
            run_mode=run_mode,
            resumed_from=resumed_from,
        )
        
        final_state = await self.app_async.ainvoke(inputs)
        await self._apply_final_answer_memory_effects(question, final_state)
        logger.info(
            "[Graph] run end task_id={} answer_len={} steps={} duration_ms={}",
            final_state.get("task_id", (final_state.get("task", {}) or {}).get("id", "")),
            len(final_state.get("final_answer", "") or ""),
            len((final_state.get("task", {}) or {}).get("steps", []) or []),
            int((time.monotonic() - started) * 1000),
        )
        
        return {
            "answer": final_state.get("final_answer", ""),
            "confidence": final_state.get("answer_confidence_score", final_state.get("context_score", 0.0)),
            "answer_confidence_label": final_state.get("answer_confidence_label", ""),
            "sources": final_state.get("active_sources", final_state.get("sources", [])),
            "retrieval_quality": final_state.get("retrieval_quality_detail", {}),
            "retrieval_chunks": final_state.get("active_retrieval_chunks", final_state.get("retrieval_chunks", [])),
            "task_id": final_state.get("task_id", (final_state.get("task", {}) or {}).get("id", "")),
            "task": final_state.get("task", {}),
            "steps": (final_state.get("task", {}) or {}).get("steps", []),
            "execution_trace": final_state.get("active_execution_trace", final_state.get("execution_trace", [])),
            "tool_results_v2": final_state.get("active_tool_results_v2", final_state.get("tool_results_v2", [])),
            "artifacts": final_state.get(
                "active_artifacts",
                final_state.get("artifacts", (final_state.get("task", {}) or {}).get("artifacts", [])),
            ),
            "trace": "\n".join(final_state.get("trace", [])),
        }
