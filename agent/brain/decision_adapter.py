from __future__ import annotations
from typing import Any, Dict
from .context_judge import judge_context_relevance_async
from .question_classifier import is_complex_question, is_follow_up_question_async
from .decision import HeuristicDecisionService

class DecisionAdapter:
    """Minimal async-compatible wrapper for LLMBrain decision defaults."""

    def __init__(self, *, agent_core: Any):
        self.agent_core = agent_core
        self._service = HeuristicDecisionService(is_complex_question_fn=is_complex_question)

    async def ainvoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = inputs["question"]
        plan = inputs["plan"]
        summary = getattr(self.agent_core, "summary_memory", "")

        context_score = await judge_context_relevance_async(summary, question)
        follow_candidate = await is_follow_up_question_async(summary, question)
        is_follow = bool(follow_candidate and context_score > 0.0)

        return self._service.decide(question, plan, context_score, is_follow)
