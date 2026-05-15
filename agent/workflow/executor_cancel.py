from __future__ import annotations

from typing import Any, Dict

from .executor_outputs import build_cancel_return_payload


def build_cancel_trace_text() -> str:
    return "Task canceled"


def build_cancelled_result_text() -> str:
    return "任务已取消。"


def build_pre_execution_cancel_payload(*, task: Dict[str, Any], current_step_index: int) -> Dict[str, Any]:
    return build_cancel_return_payload(
        task=task,
        current_step_index=current_step_index,
        trace=[build_cancel_trace_text()],
        cancel_requested=True,
    )


def build_post_execution_cancel_payload(
    *,
    task: Dict[str, Any],
    current_step_index: int,
    step_payload: Dict[str, Any],
) -> Dict[str, Any]:
    return build_cancel_return_payload(
        task=task,
        current_step_index=current_step_index,
        trace=[build_cancel_trace_text()],
        cancel_requested=True,
        step_payload=step_payload,
    )
