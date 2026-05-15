from __future__ import annotations
from config_runtime import SMALL_TALK_KEYWORDS
from utils.logger import logger
from utils.ollama_client import ask_ollama, ask_ollama_async
from .prompt_catalog import get_prompt_catalog

SMALL_TALK = SMALL_TALK_KEYWORDS

async def judge_context_relevance_async(summary: str, question: str) -> float:
    """Async version of context relevance scoring."""
    if any(k in question.lower() for k in SMALL_TALK):
        return 0.0
    if not summary.strip():
        return 0.0

    prompt = get_prompt_catalog().render("context_relevance", summary=summary, question=question)
    try:
        raw = await ask_ollama_async(prompt)
        score = float(raw.strip())
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning(f"[ContextJudge] 异步上下文相关性判断失败: {e}")
        return 0.0

def judge_context_relevance(summary: str, question: str) -> float:
    """
    判断当前问题是否与已有上下文（地质专业）高度相关
    返回 0~1 之间的连续性评分
    """
    # 1. 踢掉闲聊
    if any(k in question.lower() for k in SMALL_TALK):
        return 0.0
    # 2. 若无摘要，视为新话题
    if not summary.strip():
        return 0.0

    prompt = get_prompt_catalog().render("context_relevance", summary=summary, question=question)
    try:
        score = float(ask_ollama(prompt).strip())
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning(f"[ContextJudge] 同步上下文相关性判断失败: {e}")
        return 0.0
