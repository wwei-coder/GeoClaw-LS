import core.prompts as prompts
from utils.ollama_client import ask_ollama, ask_ollama_async
from core.config import (
    COMPLEX_KEYWORDS,
    SMALL_TALK_KEYWORDS,
    SMALL_TALK_PUNCTUATION,
    MEMORY_QUERY_KEYWORDS
)

def is_complex_question(q: str) -> bool:
    """Check if the question involves complex domain knowledge."""
    return any(k in q for k in COMPLEX_KEYWORDS)

def is_small_talk(q: str) -> bool:
    """Check if the question is just small talk."""
    q = (q or "").strip().lower()
    if not q:
        return True
    if q in SMALL_TALK_PUNCTUATION:
        return True
    return any(k in q for k in SMALL_TALK_KEYWORDS)

def is_memory_query(q: str) -> bool:
    """Check if the question is asking about conversation history."""
    q = (q or "").strip()
    return any(k in q for k in MEMORY_QUERY_KEYWORDS)

def is_follow_up_question(summary: str, question: str) -> bool:
    """
    Determine if the question is a follow-up to the previous context.
    
    Args:
        summary: The summary of the previous conversation.
        question: The current question.
        
    Returns:
        True if it is a follow-up, False otherwise.
    """
    if is_small_talk(question):
        return False
    if not summary.strip():
        return False
    prompt = prompts.FOLLOW_UP_JUDGE_PROMPT.format(summary=summary, question=question)
    result = ask_ollama(prompt).strip().upper()
    return result.startswith("YES")

async def is_follow_up_question_async(summary: str, question: str) -> bool:
    if is_small_talk(question):
        return False
    if not summary.strip():
        return False
    prompt = prompts.FOLLOW_UP_JUDGE_PROMPT.format(summary=summary, question=question)
    result = await ask_ollama_async(prompt)
    return result.strip().upper().startswith("YES")