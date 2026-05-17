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
        task_from_state: Callable[[Dict[str, Any]], Any] | None = None,
        safe_save_task: Callable[[Any], None] | None = None,
        check_answer_requirements: Callable[[Dict[str, Any]], list],
        check_answer_relevance: Callable[[Dict[str, Any]], list] | None = None,
        stream_thought: Callable[[str], None],
        review_prompt_template: str,
        ask_async_fn=ask_ollama_async,
        review_replan_max_attempts: int = 2,
    ):
        self.core = core
        self.task_from_state = task_from_state
        self.safe_save_task = safe_save_task
        self.check_answer_requirements = check_answer_requirements
        self.check_answer_relevance = check_answer_relevance or (lambda state: [])
        self.stream_thought = stream_thought
        self.review_prompt_template = review_prompt_template
        self.ask_async_fn = ask_async_fn
        self.review_replan_max_attempts = max(0, int(review_replan_max_attempts or 0))

    def _has_usable_outputs(self, state: Dict[str, Any]) -> bool:
        if state.get("active_step_results") or state.get("step_results"):
            return True
        if state.get("active_retrieval_chunks") or state.get("retrieval_chunks"):
            return True
        for item in list(state.get("active_tool_results_v2", []) or []) + list(state.get("tool_results_v2", []) or []):
            payload = dict(item or {})
            metadata = dict(payload.get("metadata") or {})
            outcome = dict(metadata.get("outcome_assessment") or payload.get("outcome_assessment") or {})
            if bool(outcome.get("usable", False)):
                return True
        return False

    def _build_fail_payload(
        self,
        *,
        state: Dict[str, Any],
        current_count: int,
        feedback: str,
        next_count: int | None = None,
    ) -> Dict[str, Any]:
        effective_next_count = int(next_count if next_count is not None else (current_count + 1))
        if self.review_replan_max_attempts and effective_next_count > self.review_replan_max_attempts:
            return self._finalize_review_limit(state, feedback=feedback, review_count=effective_next_count)
        return {
            "is_satisfactory": False,
            "feedback": feedback,
            "review_count": effective_next_count,
            "answer_revision_needed": False,
            "replanning_needed": True,
            "execution_trace": [
                self._build_review_trace(
                    status="fail",
                    summary=feedback,
                    review_count=effective_next_count,
                    next_action="replan",
                )
            ],
            "trace": [f"Reviewer FAIL: {feedback}"],
        }

    def _finalize_pass(self, state: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "is_satisfactory": True,
            "answer_revision_needed": False,
            "replanning_needed": False,
            "execution_trace": [
                self._build_review_trace(
                    status="pass",
                    summary="回答质量审核通过。",
                    review_count=int(state.get("review_count", 0) or 0),
                    next_action="finalize",
                )
            ],
        }
        if not callable(self.task_from_state) or not callable(self.safe_save_task):
            return payload
        task = self.task_from_state(state)
        approved_answer = str(state.get("final_answer") or "").strip()
        if not approved_answer:
            payload["task"] = task.to_dict()
            payload["task_id"] = task.id
            return payload
        metadata = dict(task.metadata or {})
        metadata.pop("draft_answer", None)
        task.metadata = metadata
        task.final_answer = approved_answer
        task.status = str(metadata.pop("pending_final_status", "") or task.status or "success")
        task.touch()
        self.safe_save_task(task)
        store = getattr(self.core, "task_store", None)
        if store:
            try:
                store.update_task_status(task.id, task.status, final_answer=approved_answer)
            except Exception as exc:
                logger.warning(f"[Reviewer] 更新任务最终状态失败（已忽略）: {exc}")
        payload["task"] = task.to_dict()
        payload["task_id"] = task.id
        return payload

    def _build_review_trace(
        self,
        *,
        status: str,
        summary: str,
        review_count: int,
        next_action: str,
    ) -> Dict[str, Any]:
        return {
            "phase": "reviewer",
            "type": "quality_review",
            "status": status,
            "summary": str(summary or "")[:220],
            "review_count": int(review_count or 0),
            "next_action": next_action,
        }

    def _finalize_review_limit(self, state: Dict[str, Any], *, feedback: str, review_count: int) -> Dict[str, Any]:
        summary = str(feedback or "回答未通过质量审核。").strip()
        state["final_answer"] = (
            "当前回答连续多次未通过质量审核，已停止自动重规划以避免循环。\n\n"
            f"审核意见：{summary}\n\n"
            "建议补充更明确的问题、指定资料范围，或先同步/重建知识库后重试。"
        )
        payload = self._finalize_pass(state)
        payload.update(
            {
                "review_count": int(review_count or 0),
                "feedback": summary,
                "execution_trace": [
                    self._build_review_trace(
                        status="limit_reached",
                        summary=summary,
                        review_count=int(review_count or 0),
                        next_action="degrade_answer",
                    )
                ],
                "trace": [f"Reviewer limit reached: {summary}"],
            }
        )
        return payload

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        count = state.get("review_count", 0)
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
                return self._build_fail_payload(
                    state=state,
                    current_count=count,
                    feedback=brain_review.feedback,
                    next_count=int(brain_review.review_count or (count + 1)),
                )
            self.stream_thought("> [审核通过] 回答质量达标\n")
        else:
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
                    return self._build_fail_payload(
                        state=state,
                        current_count=count,
                        feedback=str(res.get("suggestion") or ""),
                    )
                self.stream_thought("> [审核通过] 回答质量达标\n")
            except Exception as e:
                err_text = str(e)
                match = re.search(r"状态码\s+(\d+)", err_text)
                status_code = int(match.group(1)) if match else None
                if status_code in {408, 429, 500, 502, 503, 504}:
                    logger.info(f"[Reviewer] 审核请求临时失败（HTTP {status_code}），已降级为规则审查")
                else:
                    logger.warning(f"[Reviewer] 异步审核异常，已降级为规则审查: {e}")

        evidence_assessment = dict(state.get("evidence_quality_assessment") or {})
        evidence_issue = str(evidence_assessment.get("issue_type") or "none")
        if evidence_issue not in {"none", ""} and bool(evidence_assessment.get("need_evidence", False)):
            return self._build_fail_payload(
                state=state,
                current_count=count,
                feedback=f"证据校验提示：{evidence_assessment.get('summary', '证据不足。')}",
            )

        relevance_issues = self.check_answer_relevance(state)
        if relevance_issues:
            return self._build_fail_payload(
                state=state,
                current_count=count,
                feedback=f"回答与用户问题相关性不足：{'; '.join(relevance_issues)}。请围绕原问题重新回答。",
            )

        missing_requirements = self.check_answer_requirements(state)
        if missing_requirements:
            return self._build_fail_payload(
                state=state,
                current_count=count,
                feedback=f"回答未满足要求：{'; '.join(missing_requirements)}",
            )

        return self._finalize_pass(state)
