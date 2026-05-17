from __future__ import annotations

import re
from typing import List

_QUESTION_STOPWORDS = {
    "什么",
    "什么是",
    "如何",
    "怎么",
    "怎样",
    "哪些",
    "为什么",
    "是否",
    "能否",
    "请问",
    "请你",
    "帮我",
    "一下",
    "这个",
    "那个",
    "有关",
    "关于",
    "介绍",
    "解释",
    "说明",
    "总结",
    "分析",
    "进行",
    "可以",
    "需要",
    "以及",
    "或者",
    "还是",
}


def _extract_question_keywords(question: str) -> List[str]:
    text = str(question or "").strip()
    keywords: list[str] = []

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text):
        keywords.append(token)

    for raw in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        phrase = raw
        for stop in _QUESTION_STOPWORDS:
            phrase = phrase.replace(stop, " ")
        for part in re.findall(r"[\u4e00-\u9fff]{2,}", phrase):
            if part in _QUESTION_STOPWORDS:
                continue
            max_n = min(4, len(part))
            for n in range(2, max_n + 1):
                for idx in range(0, len(part) - n + 1):
                    token = part[idx : idx + n]
                    if token not in _QUESTION_STOPWORDS:
                        keywords.append(token)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in keywords:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:16]


def check_answer_relevance(*, question: str, answer: str) -> List[str]:
    """Lightweight guard against answers that do not cover the user's question at all."""
    q = str(question or "").strip()
    a = str(answer or "").strip()
    if not q or not a:
        return []

    keywords = _extract_question_keywords(q)
    if not keywords:
        return []

    answer_lower = a.lower()
    alpha_keywords = [kw for kw in keywords if re.search(r"[A-Za-z]", kw)]
    if alpha_keywords and not any(kw.lower() in answer_lower for kw in alpha_keywords):
        sample = "、".join(alpha_keywords[:5])
        return [f"回答未覆盖用户问题关键词：{sample}"]

    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    if matched:
        return []

    sample = "、".join(keywords[:5])
    return [f"回答未覆盖用户问题关键词：{sample}"]
