from __future__ import annotations
from typing import Any, Callable, Dict, List
from agent.brain.planning import PlannerService
from utils.logger import logger as default_logger

class PlannerNode:
    def __init__(
        self,
        *,
        core: Any,
        build_task: Callable[..., Any],
        stream_thought: Callable[[str], None],
        summarize_step_trace: Callable[[Dict[str, Any]], List[str]],
        safe_save_task: Callable[[Any], None],
        safe_save_step: Callable[[str, Any, int], None],
        clear_saved_steps: Callable[[str], None],
        sync_legacy_steps: Callable[[Any], List[Dict[str, Any]]],
        logger=default_logger,
    ):
        self.core = core
        self.build_task = build_task
        self.stream_thought = stream_thought
        self.summarize_step_trace = summarize_step_trace
        self.safe_save_task = safe_save_task
        self.safe_save_step = safe_save_step
        self.clear_saved_steps = clear_saved_steps
        self.sync_legacy_steps = sync_legacy_steps
        self.logger = logger
        self._planner_fallback_service = None

    def _get_planner_fallback_service(self) -> PlannerService:
        service = self._planner_fallback_service
        if service is None:
            service = PlannerService()
            self._planner_fallback_service = service
        return service

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question = state["question"]
        feedback = state.get("feedback", "")
        review_count = state.get("review_count", 0)

        if feedback:
            if state.get("replanning_needed", False):
                self.stream_thought(f"\n> [动态调整] 执行受阻，重新规划，原因：{feedback}...\n")
                question = f"用户问题：{question}\n\n执行过程中遇到问题：{feedback}\n请重新规划任务，尝试其他方法。"
            else:
                self.stream_thought(f"\n> [反思] 第 {review_count} 次修正，原因：{feedback}...\n")
                question = f"用户问题：{question}\n\n之前的回答未通过审核，建议：{feedback}\n请重新规划任务。"
        else:
            self.stream_thought("\n> [思考] 正在规划任务步骤...\n")

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
                    planner_text_trace.extend(self.summarize_step_trace(step))
            else:
                res = await self._get_planner_fallback_service().handle_async(question)
                plan = res["plan"]
                trace_text = res.get("trace", "Planner: Done")
            task = self.build_task(
                user_query=state["question"],
                plan_steps=plan.get("steps", []),
                task_id=(state.get("task_id") or ""),
                run_mode=str(state.get("run_mode") or "sync"),
                resumed_from=state.get("resumed_from") or None,
            )
            task.metadata["answer_requirements"] = list(plan.get("answer_requirements", []) or [])
            task.status = "running"
            task.touch()
            if task.id and (state.get("replanning_needed", False) or feedback):
                self.clear_saved_steps(task.id)
            self.safe_save_task(task)
            return {
                "plan": plan,
                "task": task.to_dict(),
                "task_id": task.id,
                "steps": self.sync_legacy_steps(task),
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
