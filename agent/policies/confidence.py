from __future__ import annotations

from config_runtime import (
    ANSWER_CONFIDENCE_HIGH_THRESHOLD,
    ANSWER_CONFIDENCE_MEDIUM_THRESHOLD,
    ANSWER_CONFIDENCE_NEED_KB_CONTEXT_WEIGHT,
    ANSWER_CONFIDENCE_NEED_KB_RETRIEVAL_WEIGHT,
    ANSWER_CONFIDENCE_NO_KB_FLOOR,
    ANSWER_CONFIDENCE_REPLAN_PENALTY_CAP,
    ANSWER_CONFIDENCE_REPLAN_PENALTY_STEP,
)

def grade_answer_confidence(
    *,
    need_kb: bool,
    context_score: float,
    retrieval_quality: float,
    execution_replan_count: int,
):
    replan_penalty = min(
        ANSWER_CONFIDENCE_REPLAN_PENALTY_CAP,
        ANSWER_CONFIDENCE_REPLAN_PENALTY_STEP * max(0, int(execution_replan_count)),
    )

    if need_kb:
        score = (
            ANSWER_CONFIDENCE_NEED_KB_RETRIEVAL_WEIGHT * float(retrieval_quality or 0.0)
            + ANSWER_CONFIDENCE_NEED_KB_CONTEXT_WEIGHT * float(context_score or 0.0)
            - replan_penalty
        )
    else:
        score = max(ANSWER_CONFIDENCE_NO_KB_FLOOR, float(context_score or 0.0)) - replan_penalty
    score = max(0.0, min(1.0, score))

    if score >= ANSWER_CONFIDENCE_HIGH_THRESHOLD:
        label = "高"
    elif score >= ANSWER_CONFIDENCE_MEDIUM_THRESHOLD:
        label = "中"
    else:
        label = "低"
    return score, label
