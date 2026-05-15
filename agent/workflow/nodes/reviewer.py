from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict

from utils.logger import logger
from utils.ollama_client import ask_ollama_async


class ReviewerNode:
    def __init__(
        self,
        *,
        core: Any,
        check_answer_requirements: Callable[[Dict[str, Any]], list],
        stream_thought: Callable[[str], None],
        review_prompt_template: str,
        ask_async_fn=ask_ollama_async,
    ):
        self.core = core
        self.check_answer_requirements = check_answer_requirements
        self.stream_thought = stream_thought
        self.review_prompt_template = review_prompt_template
        self.ask_async_fn = ask_async_fn

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        count = state.get("review_count", 0)
        evidence_assessment = dict(state.get("evidence_quality_assessment") or {})
        evidence_issue = str(evidence_assessment.get("issue_type") or "none")
        if evidence_issue not in {"none", ""} and bool(evidence_assessment.get("need_evidence", False)):
            if count >= 2:
                return {"is_satisfactory": True}
            return {
                "is_satisfactory": False,
                "feedback": f"证据校验提示：{evidence_assessment.get('summary', '证据不足。')}",
                "review_count": count + 1,
            }

        missing_requirements = self.check_answer_requirements(state)
        if missing_requirements:
            if count >= 2:
                return {"is_satisfactory": True}
            return {
                "is_satisfactory": False,
                "feedback": f"回答未满足要求：{'; '.join(missing_requirements)}",
                "review_count": count + 1,
            }

        brain = getattr(self.core, "brain", None)
        if brain is not None:
            self.stream_thought("\n> [思考] 正在审核回答质量...\n")
            brain_review = await brain.review(
                question=state["question"],
                answer=state["final_answer"],
                review_count=count,
            )
            if not brain_review.is_satisfactory:
                self.stream_thought(f"> [审核未通过] -> {brain_review.feedback}\n")
                return {
                    "is_satisfactory": False,
                    "feedback": brain_review.feedback,
                    "review_count": brain_review.review_count,
                }
            self.stream_thought("> [审核通过] 回答质量达标\n")
            return {"is_satisfactory": True}

        if count >= 2:
            return {"is_satisfactory": True}

        self.stream_thought("\n> [思考] 正在审核回答质量...\n")
        prompt = self.review_prompt_template.format(
            question=state["question"],
            answer=state["final_answer"],
        )
        try:
            raw = (await self.ask_async_fn(prompt)).strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            res = json.loads(raw)
            is_ok = (res.get("status") == "PASS")
            if not is_ok:
                self.stream_thought(f"> [审核未通过] {res.get('reason')} -> {res.get('suggestion')}\n")
                return {
                    "is_satisfactory": False,
                    "feedback": res.get("suggestion"),
                    "review_count": count + 1,
                }
            self.stream_thought("> [审核通过] 回答质量达标\n")
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
