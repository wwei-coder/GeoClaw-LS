from __future__ import annotations
from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List
import yaml
from loguru import logger
from config_runtime import (
    ALLOWED_ENGLISH_WORDS,
    INSAR_BAD_PHRASES,
    LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
    LLM_TEMPERATURE_TERMINOLOGY_REWRITE,
    TERMINOLOGY_PATH,
    TERMINOLOGY_REPLACEMENTS,
)
from utils.ollama_client import ask_ollama, ask_ollama_async
from .prompt_catalog import get_prompt_catalog

@dataclass(frozen=True)
class TerminologyTerm:
    id: str
    canonical: str
    standard_name: str
    english_name: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    required_in_answer: bool = False
    required_phrases: tuple[str, ...] = field(default_factory=tuple)
    recommended_definition: str = ""
    forbidden_phrases: tuple[str, ...] = field(default_factory=tuple)
    replacements: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def matches(self, text: str) -> bool:
        haystack = str(text or "")
        haystack_lower = haystack.lower()
        candidates = [self.canonical, self.standard_name, self.english_name, *self.aliases]
        for item in candidates:
            token = str(item or "").strip()
            if not token:
                continue
            if re.search(r"[A-Za-z]", token):
                if token.lower() in haystack_lower:
                    return True
            elif token in haystack:
                return True
        return False


class TerminologyLibrary:
    def __init__(self, *, terms: Iterable[TerminologyTerm], allowed_english_words: Iterable[str]):
        self.terms = list(terms)
        self.allowed_english_words = {str(item).strip() for item in allowed_english_words if str(item).strip()}
        for term in self.terms:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9-]*", f"{term.canonical} {term.english_name} {' '.join(term.aliases)}"):
                self.allowed_english_words.add(token)

    def find_terms(self, text: str) -> List[TerminologyTerm]:
        return [term for term in self.terms if term.matches(text)]

    def apply_replacements(self, text: str) -> str:
        final_text = str(text or "")
        pairs: list[tuple[str, str]] = list(TERMINOLOGY_REPLACEMENTS)
        for term in self.terms:
            pairs.extend(term.replacements)
        seen: set[tuple[str, str]] = set()
        for old, new in pairs:
            pair = (str(old), str(new))
            if pair in seen:
                continue
            seen.add(pair)
            final_text = final_text.replace(pair[0], pair[1])
        return final_text

    def build_prompt_constraints(self, question: str, context: str = "") -> str:
        matched = self.find_terms(f"{question}\n{context}")
        if not matched:
            return "无。"
        lines = ["以下术语属于强定义或推荐定义，回答中涉及时必须遵守："]
        for term in matched:
            label = term.canonical or term.standard_name
            names = []
            if term.standard_name and term.standard_name != label:
                names.append(term.standard_name)
            if term.english_name:
                names.append(term.english_name)
            suffix = f"（{'；'.join(names)}）" if names else ""
            lines.append(f"- {label}{suffix}：{term.recommended_definition or term.standard_name}")
            if term.forbidden_phrases:
                lines.append(f"  禁止误释为：{'、'.join(term.forbidden_phrases)}。")
        return "\n".join(lines)

    def find_violations(self, answer: str, matched_terms: Iterable[TerminologyTerm]) -> List[str]:
        text = str(answer or "")
        violations: list[str] = []
        for term in matched_terms:
            bad_hits = [phrase for phrase in term.forbidden_phrases if phrase and phrase in text]
            if bad_hits:
                violations.append(f"{term.canonical} 出现禁用误释：{'、'.join(bad_hits)}")
            if term.required_in_answer:
                required = [phrase for phrase in term.required_phrases if str(phrase or "").strip()]
                if required:
                    if not all(phrase in text for phrase in required):
                        violations.append(f"{term.canonical} 缺少必需解释：{'、'.join(required)}")
        return violations


def _coerce_replacements(raw: Any) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in raw or []:
        if isinstance(item, dict):
            old = str(item.get("old") or "")
            new = str(item.get("new") or "")
        else:
            try:
                old, new = item[0], item[1]
            except Exception:
                continue
            old = str(old or "")
            new = str(new or "")
        if old and new:
            pairs.append((old, new))
    return tuple(pairs)


def _term_from_dict(item: Dict[str, Any]) -> TerminologyTerm:
    return TerminologyTerm(
        id=str(item.get("id") or item.get("canonical") or "").strip(),
        canonical=str(item.get("canonical") or "").strip(),
        standard_name=str(item.get("standard_name") or item.get("canonical") or "").strip(),
        english_name=str(item.get("english_name") or "").strip(),
        aliases=tuple(str(alias).strip() for alias in (item.get("aliases") or []) if str(alias).strip()),
        required_in_answer=bool(item.get("required_in_answer", False)),
        required_phrases=tuple(str(phrase).strip() for phrase in (item.get("required_phrases") or []) if str(phrase).strip()),
        recommended_definition=str(item.get("recommended_definition") or "").strip(),
        forbidden_phrases=tuple(str(phrase).strip() for phrase in (item.get("forbidden_phrases") or []) if str(phrase).strip()),
        replacements=_coerce_replacements(item.get("replacements") or []),
    )


def _fallback_library() -> TerminologyLibrary:
    return TerminologyLibrary(
        terms=[
            TerminologyTerm(
                id="insar",
                canonical="InSAR",
                standard_name="干涉合成孔径雷达",
                english_name="Interferometric Synthetic Aperture Radar",
                aliases=("InSAR", "insar", "干涉合成孔径雷达"),
                required_in_answer=True,
                required_phrases=("干涉合成孔径雷达", "Interferometric Synthetic Aperture Radar"),
                recommended_definition=(
                    "InSAR 是干涉合成孔径雷达（Interferometric Synthetic Aperture Radar），"
                    "通过多期 SAR 影像相位差获取地表形变信息。"
                ),
                forbidden_phrases=tuple(INSAR_BAD_PHRASES),
                replacements=tuple(TERMINOLOGY_REPLACEMENTS),
            )
        ],
        allowed_english_words=ALLOWED_ENGLISH_WORDS,
    )


_GLOBAL_TERMINOLOGY_LIBRARY: TerminologyLibrary | None = None


def get_terminology_library(*, force_reload: bool = False) -> TerminologyLibrary:
    global _GLOBAL_TERMINOLOGY_LIBRARY
    if _GLOBAL_TERMINOLOGY_LIBRARY is not None and not force_reload:
        return _GLOBAL_TERMINOLOGY_LIBRARY
    path = Path(TERMINOLOGY_PATH)
    if not path.exists():
        _GLOBAL_TERMINOLOGY_LIBRARY = _fallback_library()
        return _GLOBAL_TERMINOLOGY_LIBRARY
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_terms = data.get("terms") or []
        terms = [_term_from_dict(item) for item in raw_terms if isinstance(item, dict)]
        allowed = ((data.get("global") or {}).get("allowed_english_words") or ALLOWED_ENGLISH_WORDS)
        _GLOBAL_TERMINOLOGY_LIBRARY = TerminologyLibrary(
            terms=terms or _fallback_library().terms,
            allowed_english_words=allowed,
        )
    except Exception as exc:
        logger.warning(f"[Terminology] 术语库加载失败，使用内置兜底: {exc}")
        _GLOBAL_TERMINOLOGY_LIBRARY = _fallback_library()
    return _GLOBAL_TERMINOLOGY_LIBRARY


def build_terminology_constraints(question: str, context: str = "") -> str:
    return get_terminology_library().build_prompt_constraints(question, context)


def _get_disallowed_words(text: str) -> list[str]:
    allowed_words = get_terminology_library().allowed_english_words or ALLOWED_ENGLISH_WORDS
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", text)
    return [word for word in words if word not in allowed_words]

def _apply_hard_replacements(text: str) -> str:
    return get_terminology_library().apply_replacements(text)

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

    final_answer = _cleanup_meta_text(final_answer, question, fallback=original_answer)
    final_answer = _apply_hard_replacements(final_answer)

    library = get_terminology_library()
    matched_terms = library.find_terms(f"{question}\n{final_answer}")
    violations = library.find_violations(final_answer, matched_terms)
    if violations:
        has_insar = any(term.id == "insar" or term.canonical == "InSAR" for term in matched_terms)
        if has_insar:
            fix_prompt = prompt_catalog.render(
                "fix_insar",
                question=question,
                answer=final_answer,
            )
        else:
            fix_prompt = prompt_catalog.render(
                "fix_terminology_concepts",
                question=question,
                answer=final_answer,
                terminology_constraints=library.build_prompt_constraints(question, final_answer),
                violations="\n".join(f"- {item}" for item in violations),
            )
        try:
            final_answer = ask_fn(
                fix_prompt,
                temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
            ).strip()
        except Exception as exc:
            logger.warning(f"[Terminology] 术语修正失败，保留当前回答: {exc}")
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
                logger.warning(f"[Terminology] 术语二次英文润色失败，保留当前回答: {exc}")
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

    final_answer = _cleanup_meta_text(final_answer, question, fallback=original_answer)
    final_answer = _apply_hard_replacements(final_answer)

    library = get_terminology_library()
    matched_terms = library.find_terms(f"{question}\n{final_answer}")
    violations = library.find_violations(final_answer, matched_terms)
    if violations:
        has_insar = any(term.id == "insar" or term.canonical == "InSAR" for term in matched_terms)
        if has_insar:
            fix_prompt = prompt_catalog.render(
                "fix_insar",
                question=question,
                answer=final_answer,
            )
        else:
            fix_prompt = prompt_catalog.render(
                "fix_terminology_concepts",
                question=question,
                answer=final_answer,
                terminology_constraints=library.build_prompt_constraints(question, final_answer),
                violations="\n".join(f"- {item}" for item in violations),
            )
        try:
            final_answer = (
                await ask_async_fn(
                    fix_prompt,
                    temperature=LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR,
                )
            ).strip()
        except Exception as exc:
            logger.warning(f"[Terminology] 术语修正失败，保留当前回答: {exc}")
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
                logger.warning(f"[Terminology] 术语二次英文润色失败，保留当前回答: {exc}")
                break

        final_answer = _apply_hard_replacements(final_answer)

    return _cleanup_meta_text(final_answer, question, fallback=original_answer)
