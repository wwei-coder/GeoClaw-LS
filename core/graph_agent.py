import operator
import json
import re
from typing import TypedDict, Annotated, List, Dict, Any, Union, Optional
from langgraph.graph import StateGraph, END
from agent.executor import AgentExecutor
from agent.state import AgentTask, AgentStep, Artifact
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

class GraphAgent:
    def __init__(self, agent_core: Any):
        self.core = agent_core
        self.executor = AgentExecutor(get_tool_registry())
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
        store = getattr(self.core, "task_store", None)
        if not store:
            return
        try:
            store.save_task(task, session_id=self.core.get_active_session_id())
        except Exception as exc:
            logger.warning(f"[TaskStore] 保存任务失败（已忽略）: {exc}")

    def _safe_save_step(self, task_id: str, step: AgentStep, position: int) -> None:
        store = getattr(self.core, "task_store", None)
        if not store:
            return
        try:
            store.save_step(task_id=task_id, step=step, position=position)
        except Exception as exc:
            logger.warning(f"[TaskStore] 保存步骤失败（已忽略）: {exc}")

    def _safe_save_artifact(self, task_id: str, artifact: Artifact) -> None:
        store = getattr(self.core, "task_store", None)
        if not store:
            return
        try:
            store.save_artifact(task_id=task_id, artifact=artifact)
        except Exception as exc:
            logger.warning(f"[TaskStore] 保存产物失败（已忽略）: {exc}")

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
            res = await self.core.planner.ainvoke({"question": question})
            plan = res["plan"]
            task = self.executor.build_task(
                user_query=state["question"],
                plan_steps=plan.get("steps", []),
                task_id=(state.get("task_id") or ""),
                run_mode=str(state.get("run_mode") or "sync"),
                resumed_from=state.get("resumed_from") or None,
            )
            task.status = "running"
            task.touch()
            self._safe_save_task(task)
            return {
                "plan": plan,
                "task": task.to_dict(),
                "task_id": task.id,
                "steps": self._sync_legacy_steps(task),
                "trace": [res.get("trace", "Planner: Done")],
                "current_step_index": 0,
                "step_results": [],
                "tool_results_v2": [],
                "execution_trace": [],
                "artifacts": [],
                "cancel_requested": False,
                "replanning_needed": False,
                "feedback": ""
            }
        except Exception as e:
            return {"error": str(e), "trace": [f"Planner Error: {e}"]}

    async def _node_decision_async(self, state: AgentState) -> Dict[str, Any]:
        self._stream_thought("\n> [思考] 正在评估上下文和决策...\n")
        res = await self.core.decision.ainvoke({
            "question": state["question"],
            "plan": state["plan"]
        })
        
        force_tool = res["force_tool"]
        final_use_kb = res["final_use_kb"]
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
            "context_score": res["context_score"],
            "force_tool": force_tool,
            "need_kb": final_use_kb,
            "steps": self._sync_legacy_steps(task),
            "task": task.to_dict(),
            "trace": [res.get("trace", "Decision: Done")]
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
        if tool == "RAG":
            quality = dict((tool_result.metadata or {}).get("retrieval_quality", {}) or {})
            chunks = list((tool_result.metadata or {}).get("kb_chunks", []) or [])
            quality_score = float(quality.get("score", 0.0) or 0.0)
            for c in chunks:
                if c.get("doc_name"):
                    new_sources.append(c["doc_name"])
            if chunks:
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
            else:
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
            if (
                not tool_result.success
                or not result_text
                or result_text.strip().startswith("Error:")
                or result_text.strip().startswith("[系统错误]")
                or result_text.strip().startswith("[错误]")
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
            "trace": [f"Executed {tool}"]
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
        
        syn_res = await self.core.synthesis.ainvoke({
            "question": state["question"],
            "step_results": state["step_results"],
            "kb_chunks": [], 
            "sources": state["sources"],
            "canceled": False,
            "stream_callback": cb
        })
        confidence_score, confidence_label = self._grade_answer_confidence(state)
        final_answer = f"【系统可信度（证据）：{confidence_label}】\n{syn_res['final_answer']}"
        if confidence_label == "低":
            final_answer += "\n\n【需补充信息】当前证据支撑较弱，建议补充更具体的问题条件、关键词或权威资料来源。"
        
        task = self._task_from_state(state)
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
            "answer_confidence_label": confidence_label
        }

    async def _node_reviewer_async(self, state: AgentState) -> Dict[str, Any]:
        count = state.get("review_count", 0)
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
            else:
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
            "answer_confidence_label": ""
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
