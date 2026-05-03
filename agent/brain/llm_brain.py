from __future__ import annotations
import json
import re
from typing import Any, Optional
from core.chains import HeuristicDecisionChain, MemoryQueryChain, PlannerChain, SmallTalkChain, SynthesisChain
from core.question_classifier import is_memory_query, is_small_talk
from utils.ollama_client import ask_ollama_async
from utils.logger import logger
from .prompt_catalog import BrainPromptCatalog
from .schemas import BrainAnswer, BrainDecision, BrainPlan, BrainReview

class LLMBrain:
    """Thin brain facade that wraps existing chain-based logic."""

    def __init__(
        self,
        agent_core: Any,
        *,
        planner_chain: Optional[Any] = None,
        decision_chain: Optional[Any] = None,
        synthesis_chain: Optional[Any] = None,
        small_talk_chain: Optional[Any] = None,
        memory_query_chain: Optional[Any] = None,
        prompt_catalog: Optional[BrainPromptCatalog] = None,
        review_llm_call: Optional[Any] = None,
    ):
        self.agent_core = agent_core
        self.planner_chain = planner_chain or PlannerChain()
        self.decision_chain = decision_chain or HeuristicDecisionChain(agent_core=agent_core)
        self.synthesis_chain = synthesis_chain or SynthesisChain(agent_core=agent_core)
        self.small_talk_chain = small_talk_chain or SmallTalkChain(agent_core=agent_core)
        self.memory_query_chain = memory_query_chain or MemoryQueryChain(agent_core=agent_core)
        self.prompt_catalog = prompt_catalog or BrainPromptCatalog()
        self._review_llm_call = review_llm_call or ask_ollama_async

    def is_small_talk(self, question: str) -> bool:
        return bool(is_small_talk(question))

    def is_memory_query(self, question: str) -> bool:
        return bool(is_memory_query(question))

    async def answer_small_talk(self, question: str):
        return await self.small_talk_chain.ainvoke({"question": question})

    async def answer_memory_query(self, question: str):
        return await self.memory_query_chain.ainvoke({"question": question})

    async def plan(self, question: str) -> BrainPlan:
        res = await self.planner_chain.ainvoke({"question": question})
        raw_plan = dict(res.get("plan", {}) or {})
        return BrainPlan(
            steps=list(raw_plan.get("steps", []) or []),
            raw_plan=raw_plan,
            source="PlannerChain",
            trace=str(res.get("trace", "")),
        )

    async def decide(self, question: str, plan: dict) -> BrainDecision:
        res = await self.decision_chain.ainvoke({"question": question, "plan": plan})
        return BrainDecision(
            force_tool=res.get("force_tool"),
            need_kb=bool(res.get("final_use_kb", False)),
            context_score=float(res.get("context_score", 0.0) or 0.0),
            reason=str(res.get("trace", "")),
        )

    async def synthesize(
        self,
        *,
        question: str,
        step_results: list,
        kb_chunks: list,
        sources: list,
        canceled: bool = False,
        stream_callback: Any = None,
    ) -> BrainAnswer:
        res = await self.synthesis_chain.ainvoke(
            {
                "question": question,
                "step_results": list(step_results or []),
                "kb_chunks": list(kb_chunks or []),
                "sources": list(sources or []),
                "canceled": bool(canceled),
                "stream_callback": stream_callback,
            }
        )
        return BrainAnswer(
            answer=str(res.get("final_answer", "")),
            sources=list(res.get("final_sources", sources or []) or []),
        )

    async def review(self, *, question: str, answer: str, review_count: int = 0) -> BrainReview:
        if review_count >= 2:
            return BrainReview(is_satisfactory=True, feedback="", review_count=review_count)

        prompt = self.prompt_catalog.render("reviewer", question=question, answer=answer)
        try:
            raw = (await self._review_llm_call(prompt)).strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            payload = json.loads(raw)
            is_ok = payload.get("status") == "PASS"
            if not is_ok:
                return BrainReview(
                    is_satisfactory=False,
                    feedback=str(payload.get("suggestion", "")),
                    review_count=review_count + 1,
                )
            return BrainReview(is_satisfactory=True, feedback="", review_count=review_count)
        except Exception as e:
            err_text = str(e)
            match = re.search(r"状态码\s+(\d+)", err_text)
            status_code = int(match.group(1)) if match else None
            if status_code in {408, 429, 500, 502, 503, 504}:
                logger.info(f"[LLMBrain] 审核请求临时失败（HTTP {status_code}），降级放行")
            else:
                logger.warning(f"[LLMBrain] 审核异常，降级放行: {e}")
            return BrainReview(is_satisfactory=True, feedback="", review_count=review_count)

    async def normalize_answer_terms(self, answer: str, question: str = "") -> str:
        fixer = getattr(self.agent_core, "_fix_terminology_async", None)
        if fixer is None:
            return answer
        return await fixer(answer, question)
