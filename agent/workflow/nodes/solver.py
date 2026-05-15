from __future__ import annotations
import time
from typing import Any, Callable, Dict
from agent.brain.synthesis_adapter import SynthesisAdapter
from utils.logger import logger as default_logger

class SolverNode:
    def __init__(
        self,
        *,
        core: Any,
        task_from_state: Callable[[Dict[str, Any]], Any],
        grade_answer_confidence: Callable[[Dict[str, Any]], Any],
        derive_task_status: Callable[[Any, str], str],
        safe_save_task: Callable[[Any], None],
        stream_thought: Callable[[str], None],
        safe_save_artifact: Callable[[str, Any], None] | None = None,
        normalize_artifacts_with_task: Callable[[str, list], list] | None = None,
        collect_remediation_metrics_fn: Callable[..., Dict[str, Any]],
        assess_evidence_quality_fn: Callable[..., Dict[str, Any]],
        build_confidence_prefixed_answer_fn: Callable[..., str],
        append_evidence_summary_if_needed_fn: Callable[[str, Dict[str, Any]], str],
        build_task_metadata_update_fn: Callable[..., Dict[str, Any]],
        build_solver_return_payload_fn: Callable[..., Dict[str, Any]],
        logger=default_logger,
    ):
        self.core = core
        self.task_from_state = task_from_state
        self.grade_answer_confidence = grade_answer_confidence
        self.derive_task_status = derive_task_status
        self.safe_save_task = safe_save_task
        self.safe_save_artifact = safe_save_artifact
        self.normalize_artifacts_with_task = normalize_artifacts_with_task
        self.stream_thought = stream_thought
        self.collect_remediation_metrics_fn = collect_remediation_metrics_fn
        self.assess_evidence_quality_fn = assess_evidence_quality_fn
        self.build_confidence_prefixed_answer_fn = build_confidence_prefixed_answer_fn
        self.append_evidence_summary_if_needed_fn = append_evidence_summary_if_needed_fn
        self.build_task_metadata_update_fn = build_task_metadata_update_fn
        self.build_solver_return_payload_fn = build_solver_return_payload_fn
        self.logger = logger
        self._synthesis_fallback_adapter = None

    def _get_synthesis_fallback_adapter(self) -> SynthesisAdapter:
        adapter = self._synthesis_fallback_adapter
        if adapter is None:
            adapter = SynthesisAdapter(agent_core=self.core)
            self._synthesis_fallback_adapter = adapter
        return adapter

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("error"):
            task = self.task_from_state(state)
            task.status = "failed"
            task.final_answer = f"系统运行出错：{state['error']}"
            task.touch()
            self.safe_save_task(task)
            return {
                "task": task.to_dict(),
                "task_id": task.id,
                "final_answer": task.final_answer,
            }

        if state.get("cancel_requested", False):
            task = self.task_from_state(state)
            task.cancel_requested = True
            task.status = "canceled"
            if not task.final_answer:
                task.final_answer = "任务已取消。"
            task.touch()
            self.safe_save_task(task)
            store = getattr(self.core, "task_store", None)
            if store:
                try:
                    store.update_task_status(task.id, task.status, final_answer=task.final_answer)
                except Exception as exc:
                    self.logger.warning(f"[TaskStore] 更新取消状态失败（已忽略）: {exc}")
            return {
                "task": task.to_dict(),
                "task_id": task.id,
                "final_answer": task.final_answer,
                "answer_confidence_score": 0.0,
                "answer_confidence_label": "低",
            }

        self.stream_thought("\n> [思考] 正在汇总回答...\n")
        started = time.monotonic()
        self.logger.info(
            "[Solver] synthesis start task_id={} step_results={} sources={}",
            (state.get("task") or {}).get("id", state.get("task_id", "")),
            len(state.get("step_results", []) or []),
            len(state.get("sources", []) or []),
        )
        cb = getattr(self.core, "_current_stream_callback", None)

        brain = getattr(self.core, "brain", None)
        if brain is not None:
            payload = {
                "question": state["question"],
                "step_results": state["step_results"],
                "kb_chunks": [],
                "sources": state["sources"],
                "canceled": False,
                "stream_callback": cb,
                "persist_memory": False,
            }
            try:
                brain_answer = await brain.synthesize(**payload)
            except TypeError as exc:
                if "persist_memory" not in str(exc):
                    raise
                payload.pop("persist_memory", None)
                brain_answer = await brain.synthesize(**payload)
            synthesized_answer = brain_answer.answer
        else:
            syn_res = await self._get_synthesis_fallback_adapter().ainvoke(
                {
                    "question": state["question"],
                    "step_results": state["step_results"],
                    "kb_chunks": [],
                    "sources": state["sources"],
                    "canceled": False,
                    "stream_callback": cb,
                    "persist_memory": False,
                }
            )
            synthesized_answer = syn_res["final_answer"]

        confidence_score, confidence_label = self.grade_answer_confidence(state)
        final_answer = self.build_confidence_prefixed_answer_fn(
            synthesized_answer=synthesized_answer,
            confidence_label=confidence_label,
            unresolved_outcomes=list(state.get("unresolved_outcomes", []) or []),
        )

        task = self.task_from_state(state)
        remediation_metrics = self.collect_remediation_metrics_fn(
            task=task,
            state=state,
            execution_trace=list(state.get("execution_trace", []) or []),
            steps=task.steps,
        )
        evidence_assessment = self.assess_evidence_quality_fn(
            answer=synthesized_answer,
            sources=list(state.get("sources", []) or []),
            retrieval_chunks=list(state.get("retrieval_chunks", []) or []),
            need_evidence=bool((state.get("plan") or {}).get("need_evidence", state.get("need_kb", False))),
            confidence_label=confidence_label,
        )
        metadata_update = self.build_task_metadata_update_fn(
            remediation_metrics=remediation_metrics,
            evidence_assessment=evidence_assessment,
        )
        task.metadata["remediation_metrics"] = metadata_update["remediation_metrics"]
        task.metadata["evidence_quality_assessment"] = metadata_update["evidence_quality_assessment"]
        final_answer = self.append_evidence_summary_if_needed_fn(final_answer, evidence_assessment)
        task.final_answer = final_answer
        task.status = self.derive_task_status(task, final_answer)
        task.touch()
        self.safe_save_task(task)
        self.logger.info(
            "[Solver] synthesis end task_id={} answer_len={} confidence={} duration_ms={}",
            task.id,
            len(final_answer or ""),
            confidence_label,
            int((time.monotonic() - started) * 1000),
        )

        store = getattr(self.core, "task_store", None)
        if store:
            try:
                store.update_task_status(task.id, task.status, final_answer=final_answer)
            except Exception as exc:
                self.logger.warning(f"[TaskStore] 更新任务最终状态失败（已忽略）: {exc}")

        return self.build_solver_return_payload_fn(
            task=task.to_dict(),
            task_id=task.id,
            final_answer=final_answer,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            remediation_metrics=remediation_metrics,
            evidence_assessment=evidence_assessment,
        )
