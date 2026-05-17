from __future__ import annotations
from typing import Any, Callable, Dict, List
from agent.brain.decision_adapter import DecisionAdapter
from utils.logger import logger as default_logger

def _first_file_id(state: Dict[str, Any]) -> str:
    file_id = str(state.get("file_id") or "").strip()
    if file_id:
        return file_id
    for item in list(state.get("files") or []):
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("file_id") or item.get("id") or "").strip()
        if candidate:
            return candidate
    return ""

def _append_file_id(task: str, file_id: str) -> str:
    if not file_id:
        return task
    if "file_id" in (task or "").lower():
        return task
    return f"{task}\nfile_id: {file_id}"


def _missing_file_context_step(question: str) -> Dict[str, Any]:
    return {
        "tool": "LLM",
        "task": (
            "用户想分析上传文件，但当前请求缺少 file_id。"
            f"请用中文说明需要用户先上传或选择文件后再执行。原始问题：{question}"
        ),
        "reason": "文件分析缺少 file_id，先请求用户补充。",
    }

class DecisionNode:
    def __init__(
        self,
        *,
        core: Any,
        is_data_analysis_request: Callable[[str, str], bool],
        stream_thought: Callable[[str], None],
        task_from_state: Callable[[Dict[str, Any]], Any],
        sync_task_steps: Callable[[Any, List[Dict[str, Any]]], Any],
        safe_save_task: Callable[[Any], None],
        safe_save_step: Callable[[str, Any, int], None],
        sync_legacy_steps: Callable[[Any], List[Dict[str, Any]]],
        logger=default_logger,
    ):
        self.core = core
        self.is_data_analysis_request = is_data_analysis_request
        self.stream_thought = stream_thought
        self.task_from_state = task_from_state
        self.sync_task_steps = sync_task_steps
        self.safe_save_task = safe_save_task
        self.safe_save_step = safe_save_step
        self.sync_legacy_steps = sync_legacy_steps
        self.logger = logger
        self._decision_fallback_adapter = None

    def _get_decision_fallback_adapter(self) -> DecisionAdapter:
        adapter = self._decision_fallback_adapter
        if adapter is None:
            adapter = DecisionAdapter(agent_core=self.core)
            self._decision_fallback_adapter = adapter
        return adapter

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.stream_thought("\n> [思考] 正在评估上下文和决策...\n")
        brain = getattr(self.core, "brain", None)
        if brain is not None:
            brain_decision = await brain.decide(question=state["question"], plan=state["plan"])
            force_tool = brain_decision.force_tool
            final_use_kb = brain_decision.need_kb
            context_score = brain_decision.context_score
            trace_text = brain_decision.reason or f"Decision: use_kb={final_use_kb}, force={force_tool}"
        else:
            res = await self._get_decision_fallback_adapter().ainvoke(
                {
                    "question": state["question"],
                    "plan": state["plan"],
                }
            )
            force_tool = res["force_tool"]
            final_use_kb = res["final_use_kb"]
            context_score = res["context_score"]
            trace_text = res.get("trace", "Decision: Done")
        current_steps = list(state["steps"])

        if final_use_kb and not any(s["tool"] == "RAG" for s in current_steps):
            current_steps.insert(0, {"tool": "RAG", "task": state["question"]})

        if self.is_data_analysis_request(state["question"], state.get("file_id", "")):
            has_data_tool = any(str(s.get("tool", "")).upper() in {"DATA_PROFILE", "FILE_INSPECTOR"} for s in current_steps)
            if not has_data_tool:
                data_task = state["question"]
                file_id = _first_file_id(state)
                if file_id:
                    data_task = _append_file_id(data_task, file_id)
                    current_steps = [
                        {"tool": "FILE_INSPECTOR", "task": data_task},
                        {"tool": "DATA_PROFILE", "task": data_task},
                    ]
                else:
                    current_steps = [_missing_file_context_step(state["question"])]
                    trace_text = f"{trace_text}; missing_context=file_id"

        task = self.task_from_state(state)
        task = self.sync_task_steps(task, current_steps)
        self.safe_save_task(task)
        for pos, step in enumerate(task.steps):
            self.safe_save_step(task.id, step, pos)
        return {
            "context_score": context_score,
            "force_tool": force_tool,
            "need_kb": final_use_kb,
            "steps": self.sync_legacy_steps(task),
            "task": task.to_dict(),
            "trace": [trace_text],
        }
