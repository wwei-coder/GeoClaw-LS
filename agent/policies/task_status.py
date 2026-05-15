from __future__ import annotations
from typing import Iterable

def derive_task_status(*, cancel_requested: bool, final_answer: str, step_statuses: Iterable[str]) -> str:
    if cancel_requested:
        return "canceled"
    if not str(final_answer or "").strip():
        return "failed"
    statuses = {str(status or "").lower() for status in (step_statuses or [])}
    if "failed" in statuses:
        return "partial"
    return "success"
