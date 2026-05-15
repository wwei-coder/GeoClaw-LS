from __future__ import annotations
from typing import Any, Dict

def check_next_step(state: Dict[str, Any]) -> str:
    if state.get("replanning_needed", False):
        return "replan"
    if state["current_step_index"] < len(state["steps"]):
        return "continue"
    return "done"

def check_review_result(state: Dict[str, Any]) -> str:
    if state.get("is_satisfactory", True):
        return "pass"
    return "fail"

def is_data_analysis_request(question: str, file_id: str) -> bool:
    text = (question or "").lower()
    if file_id:
        if "分析这个文件" in question or "分析文件" in question:
            return True
        if any(k in text for k in ("csv", "excel", "xlsx", "xls", "json", "txt", "file_id", "表格", "数据文件")):
            return True
    return any(k in question for k in ("分析这个文件", "分析数据", "分析表格"))
