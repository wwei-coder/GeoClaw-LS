from utils.ollama_client import ask_ollama, ask_ollama_async
from core.config import SMALL_TALK_KEYWORDS
from utils.logger import logger

SMALL_TALK = SMALL_TALK_KEYWORDS

async def judge_context_relevance_async(summary: str, question: str) -> float:
    """
    Async version of judge_context_relevance
    """
    if any(k in question.lower() for k in SMALL_TALK):
        return 0.0
    if not summary.strip():
        return 0.0

    prompt = f"""
你是地质滑坡防治专家。  
只判断【当前问题】是否与【对话摘要】的「地质专业内容」相关。

评分规则：
0.0 = 完全无关（闲聊、自我介绍、非地质）
0.5 = 部分相关（泛泛而谈）
1.0 = 明显追问（继续讨论滑坡、防治、监测等）

只返回 0/0.5/1 三位数字，不要解释。

【对话摘要】
{summary}

【当前问题】
{question}

评分：
"""
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
    # 1. 快速踢掉明显闲聊
    if any(k in question.lower() for k in SMALL_TALK):
        return 0.0

    # 2. 若无摘要，视为新话题
    if not summary.strip():
        return 0.0

    # 3. 让模型只做地质层面判断
    prompt = f"""
你是地质滑坡防治专家。  
只判断【当前问题】是否与【对话摘要】的「地质专业内容」相关。

评分规则：
0.0 = 完全无关（闲聊、自我介绍、非地质）
0.5 = 部分相关（泛泛而谈）
1.0 = 明显追问（继续讨论滑坡、防治、监测等）

只返回 0/0.5/1 三位数字，不要解释。

【对话摘要】
{summary}

【当前问题】
{question}

评分：
"""
    try:
        score = float(ask_ollama(prompt).strip())
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning(f"[ContextJudge] 同步上下文相关性判断失败: {e}")
        return 0.0