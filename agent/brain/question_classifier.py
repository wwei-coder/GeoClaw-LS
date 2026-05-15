from __future__ import annotations
from config_runtime import COMPLEX_KEYWORDS, MEMORY_QUERY_KEYWORDS, SMALL_TALK_KEYWORDS, SMALL_TALK_PUNCTUATION
from utils.ollama_client import ask_ollama, ask_ollama_async
from .prompt_catalog import get_prompt_catalog

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
    """Judge whether the current question follows the previous summary."""
    if is_small_talk(question):
        return False
    if not (summary or "").strip():
        return False
    prompt = get_prompt_catalog().render("follow_up_judge", summary=summary, question=question)
    result = ask_ollama(prompt).strip().upper()
    return result.startswith("YES")


async def is_follow_up_question_async(summary: str, question: str) -> bool:
    if is_small_talk(question):
        return False
    if not (summary or "").strip():
        return False
    prompt = get_prompt_catalog().render("follow_up_judge", summary=summary, question=question)
    result = await ask_ollama_async(prompt)
    return result.strip().upper().startswith("YES")
