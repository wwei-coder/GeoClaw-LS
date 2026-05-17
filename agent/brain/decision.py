from __future__ import annotations
from typing import Any, Dict
from utils.logger import logger

class HeuristicDecisionService:
    def __init__(
        self,
        *,
        is_complex_question_fn: Any,
    ):
        self.is_complex_question_fn = is_complex_question_fn

    def decide(self, question: str, plan: Dict[str, Any], context_score: float, is_follow: bool) -> Dict[str, Any]:
        planner_need_kb = bool(plan.get("need_kb", False))

        final_use_kb = planner_need_kb
        force_tool = None

        if is_follow or self.is_complex_question_fn(question):
            final_use_kb = True

        has_discovery = any(s.get("tool") == "DISCOVERY" for s in plan.get("steps", []))
        if has_discovery:
            final_use_kb = True

        logger.debug(f"[HeuristicDecision] UseKB={final_use_kb}, ForceTool={force_tool}")
        return {
            "context_score": context_score,
            "is_follow": is_follow,
            "force_tool": force_tool,
            "final_use_kb": final_use_kb,
            "trace": f"Decision: use_kb={final_use_kb}, force={force_tool}",
        }
