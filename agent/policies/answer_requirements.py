from __future__ import annotations
from typing import Any, Dict, List

def check_answer_requirements(*, plan: Dict[str, Any], answer: str, sources: List[str]) -> List[str]:
    requirements = [str(item).strip() for item in (dict(plan or {}).get("answer_requirements", []) or []) if str(item).strip()]
    if not requirements:
        return []
    missing: List[str] = []
    for req in requirements:
        if "中文" in req:
            has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in (answer or ""))
            if not has_chinese:
                missing.append(req)
        elif "引用资料来源" in req:
            if not (("来源" in (answer or "")) or bool(sources)):
                missing.append(req)
        elif "区分资料支持和模型推断" in req:
            text = answer or ""
            has_split = ("资料支持" in text and "推断" in text) or ("资料未明确提及" in text and "推断" in text)
            if not has_split:
                missing.append(req)
    return missing

def summarize_step_trace(step: Dict[str, Any]) -> List[str]:
    parts: List[str] = []
    tool = str(step.get("tool", "")).strip()
    reason = str(step.get("reason", "")).strip()
    expected_output = str(step.get("expected_output", "")).strip()
    fallback = str(step.get("fallback", "")).strip()
    if reason:
        parts.append(f"选择 {tool or '工具'}：{reason}")
    if expected_output:
        parts.append(f"预期输出：{expected_output}")
    if fallback:
        parts.append(f"回退策略：{fallback}")
    return parts
