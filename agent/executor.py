from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from core.config import RAG_MAX_CHUNK_LENGTH
from .state import AgentStep, AgentTask, Artifact
from tools.base import ToolInput, ToolResult
from tools.registry import execute_tool


ToolCallable = Callable[[str, Any], str]


def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class AgentExecutor:
    """标准化的步骤执行器：负责状态推进、异常隔离与执行轨迹。"""

    def __init__(self, registry: Dict[str, ToolCallable]):
        self.registry = registry

    def build_steps(self, plan_steps: List[Dict[str, Any]]) -> List[AgentStep]:
        steps: List[AgentStep] = []
        for idx, item in enumerate(plan_steps or []):
            tool_name = str((item or {}).get("tool", "LLM")).upper().strip() or "LLM"
            instruction = str((item or {}).get("task", "")).strip()
            step = AgentStep(
                id=f"step_{idx + 1}_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name,
                instruction=instruction,
                retry_of=(item or {}).get("retry_of"),
                attempts=int((item or {}).get("attempts") or 1),
                input={"tool_name": tool_name, "instruction": instruction},
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
            step.result = result.to_dict()
            step.artifacts = []
            for item in result.artifacts or []:
                if isinstance(item, dict):
                    normalized = dict(item)
                    normalized.setdefault("id", f"artifact_{uuid.uuid4().hex[:8]}")
                    normalized.setdefault("created_at", _iso_now())
                    step.artifacts.append(Artifact.from_dict(normalized))
            step.metadata.update(result.metadata or {})
            step.status = "success" if result.success else "failed"
            step.error = result.error
            if cancellation_event is not None and getattr(cancellation_event, "is_set", None) and cancellation_event.is_set():
                step.cancel_requested = True
                step.status = "skipped"
                step.error = "任务已取消"
        except Exception as exc:  # pragma: no cover
            result = ToolResult(success=False, content="", metadata={"tool": tool_key}, error=str(exc))
            step.status = "failed"
            step.error = str(exc)
            step.result = result.to_dict()
            step.metadata.update({"tool": tool_key})
            if fail_fast:
                raise
        finally:
            step.finished_at = _iso_now()

        trace_item = {
            "step_id": step.id,
            "tool_name": step.tool_name,
            "instruction": step.instruction,
            "status": step.status,
            "error": step.error,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
        }
        return step, result, trace_item

    async def aexecute(self, tool_name: str, task: str, agent: Any) -> ToolResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.execute(tool_name, task, agent))
