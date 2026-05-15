from __future__ import annotations

from config_runtime import GRAPH_STEP_RESULT_MAX_CHARS


def truncate_step_result(text: str) -> str:
    if not text:
        return ""
    if len(text) <= GRAPH_STEP_RESULT_MAX_CHARS:
        return text
    keep = max(1, GRAPH_STEP_RESULT_MAX_CHARS // 2)
    return text[:keep] + "\n...（步骤结果已压缩）...\n" + text[-keep:]
