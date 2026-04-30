import operator
import json
import re
from typing import TypedDict, Annotated, List, Dict, Any, Union
from langgraph.graph import StateGraph, END
from core import prompts
from utils.ollama_client import ask_ollama_async
from utils.logger import logger
from core.config import (
    RAG_MAX_CHUNK_LENGTH,
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
    plan: Dict[str, Any]
    steps: List[Dict[str, Any]]
    current_step_index: int
    step_results: Annotated[List[str], operator.add]
    final_answer: str
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
        self.app_async = self._build_async_graph()

    def _build_async_graph(self):
        return self._create_workflow(
            planner=self._node_planner_async,
            decision=self._node_decision_async,
            executor=self._node_executor_async,
            solver=self._node_solver_async,
            reviewer=self._node_reviewer_async
        )

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
            return {
                "plan": plan,
                "steps": plan.get("steps", []),
                "trace": [res.get("trace", "Planner: Done")],
                "current_step_index": 0,
                "step_results": [],
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
        current_steps = state["steps"]

        if force_tool == "CALCULATOR":
             if not any(s["tool"] == "CALCULATOR" for s in current_steps):
                 current_steps = [{"tool": "CALCULATOR", "task": state["question"]}]
        elif final_use_kb and not any(s["tool"] == "RAG" for s in current_steps):
             current_steps.insert(0, {"tool": "RAG", "task": state["question"]}) 
             
        return {
            "context_score": res["context_score"],
            "force_tool": force_tool,
            "need_kb": final_use_kb,
            "steps": current_steps,
            "trace": [res.get("trace", "Decision: Done")]
        }

    async def _node_executor_async(self, state: AgentState) -> Dict[str, Any]:
        idx = state["current_step_index"]
        steps = state["steps"]
        
        if idx >= len(steps):
             return {"current_step_index": idx + 1}

        step = steps[idx]
        tool = step["tool"]
        task = step["task"]
        
        self._stream_thought(f"\n> [思考] 步骤 {idx+1}: 使用 {tool}...\n")

        result_text = ""
        new_sources = []
        
        if tool == "RAG":
            self._stream_thought("> [执行] 正在检索知识库...\n")
            ret_res = await self.core.retriever.ainvoke({
                "question": task,
                "final_use_kb": True
            })
            chunks = ret_res["kb_chunks"]
            quality = ret_res.get("retrieval_quality", {}) or {}
            quality_score = float(quality.get("score", 0.0) or 0.0)
            for c in chunks:
                if c.get("doc_name"):
                    new_sources.append(c["doc_name"])
            
            if chunks:
                lines = []
                for c in chunks:
                    content = c.get("content", "") or ""
                    if len(content) > RAG_MAX_CHUNK_LENGTH:
                        content = content[:RAG_MAX_CHUNK_LENGTH] + "…"
                    lines.append(f"【{c.get('doc_name')}】\n{content}")
                result_text = "\n\n".join(lines)
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
                            "replanning_needed": True,
                            "execution_replan_count": replan_count + 1,
                            "retrieval_quality_score": quality_score,
                            "retrieval_quality_detail": quality,
                            "feedback": (
                                f"步骤 {idx+1} [RAG] 检索质量偏低："
                                f"score={quality_score:.2f}, hits={quality.get('hit_count', 0)}, "
                                f"avg_similarity={quality.get('avg_similarity', 0)}。请改用其他检索策略或工具。"
                            ),
                            "trace": ["RAG low-quality, triggering replan"]
                        }
            else:
                self._stream_thought("> [结果] 未找到资料，正在触发重新规划...\n")
                return {
                    "replanning_needed": True,
                    "execution_replan_count": state.get("execution_replan_count", 0) + 1,
                    "retrieval_quality_score": quality_score,
                    "retrieval_quality_detail": quality,
                    "feedback": f"步骤 {idx+1} [RAG] 未找到任何相关资料，请尝试使用搜索引擎或其他工具。",
                    "trace": ["RAG failed, triggering replan"]
                }
                
        else:
            self._stream_thought(f"> [执行] 正在运行 {tool}...\n")
            import asyncio
            loop = asyncio.get_running_loop()
            result_text = await loop.run_in_executor(None, lambda: self.core.execute_tool_step(step))
            
            if (
                not result_text
                or result_text.strip().startswith("Error:")
                or result_text.strip().startswith("[系统错误]")
                or result_text.strip().startswith("[错误]")
            ):
                 self._stream_thought("> [结果] 执行失败或为空，正在触发重新规划...\n")
                 return {
                    "replanning_needed": True,
                    "execution_replan_count": state.get("execution_replan_count", 0) + 1,
                    "feedback": f"步骤 {idx+1} [{tool}] 执行失败：{result_text}。请尝试其他方法。",
                    "trace": [f"{tool} failed, triggering replan"]
                 }

            self._stream_thought("> [结果] 执行完成\n")

        step_record = f"[{tool}] {task}：\n{self._truncate_step_result(result_text)}"
        
        return {
            "step_results": [step_record],
            "current_step_index": idx + 1,
            "sources": new_sources,
            "retrieval_quality_score": quality_score if tool == "RAG" else state.get("retrieval_quality_score", 0.0),
            "retrieval_quality_detail": quality if tool == "RAG" else state.get("retrieval_quality_detail", {}),
            "retrieval_chunks": chunks if tool == "RAG" else [],
            "trace": [f"Executed {tool}"]
        }

    async def _node_solver_async(self, state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {
                "final_answer": f"系统运行出错：{state['error']}"
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
        
        return {
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
    async def run_async(self, question: str) -> Dict[str, Any]:
        inputs = {
            "question": question,
            "plan": {},
            "steps": [],
            "current_step_index": 0,
            "step_results": [],
            "final_answer": "",
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
            "trace": "\n".join(final_state.get("trace", []))
        }
