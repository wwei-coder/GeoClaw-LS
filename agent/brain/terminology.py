from __future__ import annotations
import re
from typing import Any, Awaitable, Callable
from loguru import logger
from config_runtime import (
    ALLOWED_ENGLISH_WORDS,
    INSAR_BAD_PHRASES,
    LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
    LLM_TEMPERATURE_TERMINOLOGY_REWRITE,
    TERMINOLOGY_REPLACEMENTS,
)
from utils.ollama_client import ask_ollama, ask_ollama_async
from .prompt_catalog import get_prompt_catalog

def _get_disallowed_words(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", text)
    return [word for word in words if word not in ALLOWED_ENGLISH_WORDS]

def _apply_hard_replacements(text: str) -> str:
    final_text = text
    for old, new in TERMINOLOGY_REPLACEMENTS:
        final_text = final_text.replace(old, new)
    return final_text

def _strip_prompt_echo(text: str, fallback: str = "") -> str:
    cleaned = str(text or "").strip()
    if "【润色结果】" in cleaned:
        cleaned = cleaned.split("【润色结果】", 1)[1].strip()
    if cleaned.startswith("润色结果："):
        cleaned = cleaned.split("：", 1)[1].strip()
    prompt_echo_markers = ("### 处理原则", "【原文】", "不得改变原文的逻辑", "最小改动")
    if any(marker in cleaned for marker in prompt_echo_markers):
        return str(fallback or "").strip()
    return cleaned

def _cleanup_meta_text(text: str, question: str, fallback: str = "") -> str:
    text = _strip_prompt_echo(text, fallback=fallback)
    if any(token in question for token in ("翻译", "英文", "中文")):
        return text

    lines = [line for line in text.splitlines() if line.strip()]
    if lines and ("允许保留 InSAR" in lines[0] or "以下是英文单词" in lines[0]):
        lines = [
            line
            for line in lines
            if "允许保留 InSAR" not in line and "以下是英文单词" not in line
        ]
        return "\n".join(lines).strip()
    return text

def fix_terminology(
    answer: str,
    question: str = "",
    *,
    prompt_catalog: Any = None,
    ask_fn: Callable[..., str] | None = None,
) -> str:
    prompt_catalog = prompt_catalog or get_prompt_catalog()
    ask_fn = ask_fn or ask_ollama
    final_answer = answer
    original_answer = answer

    if re.search(r"[A-Za-z]{3,}", final_answer):
        disallowed = _get_disallowed_words(final_answer)
        if disallowed:
            rewrite_prompt = prompt_catalog.render("rewrite", text=final_answer)
            try:
                final_answer = ask_fn(
                    rewrite_prompt,
                    temperature=LLM_TEMPERATURE_TERMINOLOGY_REWRITE,
                ).strip()
            except Exception as exc:
                logger.warning(f"[Terminology] 英文术语润色失败，保留原回答: {exc}")

    final_answer = _apply_hard_replacements(final_answer)

    if "InSAR" in question:
        if ("干涉合成孔径雷达" not in final_answer) or any(
            phrase in final_answer for phrase in INSAR_BAD_PHRASES
        ):
            fix_prompt = prompt_catalog.render(
                "fix_insar",
                question=question,
                answer=final_answer,
            )
            try:
                final_answer = ask_fn(
                    fix_prompt,
                    temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
                ).strip()
            except Exception as exc:
                logger.warning(f"[Terminology] InSAR 术语修正失败，保留当前回答: {exc}")
                return final_answer

            for _ in range(2):
                disallowed = _get_disallowed_words(final_answer)
                if not disallowed:
                    break
                rewrite_prompt = prompt_catalog.render("rewrite", text=final_answer)
                try:
                    final_answer = ask_fn(
                        rewrite_prompt,
                        temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
                    ).strip()
                except Exception as exc:
                    logger.warning(f"[Terminology] InSAR 二次英文润色失败，保留当前回答: {exc}")
                    break

            final_answer = _apply_hard_replacements(final_answer)

    return _cleanup_meta_text(final_answer, question, fallback=original_answer)

async def fix_terminology_async(
    answer: str,
    question: str = "",
    *,
    prompt_catalog: Any = None,
    ask_async_fn: Callable[..., Awaitable[str]] | None = None,
) -> str:
    prompt_catalog = prompt_catalog or get_prompt_catalog()
    ask_async_fn = ask_async_fn or ask_ollama_async
    final_answer = answer
    original_answer = answer

    if re.search(r"[A-Za-z]{3,}", final_answer):
        disallowed = _get_disallowed_words(final_answer)
        if disallowed:
            rewrite_prompt = prompt_catalog.render("rewrite", text=final_answer)
            try:
                final_answer = (
                    await ask_async_fn(
                        rewrite_prompt,
                        temperature=LLM_TEMPERATURE_TERMINOLOGY_REWRITE,
                    )
                ).strip()
            except Exception as exc:
                logger.warning(f"[Terminology] 英文术语润色失败，保留原回答: {exc}")

    final_answer = _apply_hard_replacements(final_answer)

    if "InSAR" in question:
        if ("干涉合成孔径雷达" not in final_answer) or any(
            phrase in final_answer for phrase in INSAR_BAD_PHRASES
        ):
            fix_prompt = prompt_catalog.render(
                "fix_insar",
                question=question,
                answer=final_answer,
            )
            try:
                final_answer = (
                    await ask_async_fn(
                        fix_prompt,
                        temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
                    )
                ).strip()
            except Exception as exc:
                logger.warning(f"[Terminology] InSAR 术语修正失败，保留当前回答: {exc}")
                return final_answer

            for _ in range(2):
                disallowed = _get_disallowed_words(final_answer)
                if not disallowed:
                    break
                rewrite_prompt = prompt_catalog.render("rewrite", text=final_answer)
                try:
                    final_answer = (
                        await ask_async_fn(
                            rewrite_prompt,
                            temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
                        )
                    ).strip()
                except Exception as exc:
                    logger.warning(f"[Terminology] InSAR 二次英文润色失败，保留当前回答: {exc}")
                    break

            final_answer = _apply_hard_replacements(final_answer)

    return _cleanup_meta_text(final_answer, question, fallback=original_answer)
