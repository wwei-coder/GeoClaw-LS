"""Retriever utility helpers used by RetrieverChain."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional

from utils.logger import logger


def parse_metadata_filter(filter_json: str) -> Optional[Dict[str, Any]]:
    cleaned = re.sub(r"```json|```", "", (filter_json or "")).strip()
    if not cleaned or cleaned == "{}":
        return None
    import json

    try:
        extracted_filter = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not extracted_filter:
        return None

    def _is_empty_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return len(value.strip()) == 0
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    conditions = []
    for key, value in extracted_filter.items():
        if _is_empty_value(value):
            continue
        if key == "doc_name" and isinstance(value, str):
            text = value.strip()
            if text:
                conditions.append({key: {"$contains": text}})
        else:
            conditions.append({key: value})
    if len(conditions) == 1:
        return conditions[0]
    if len(conditions) > 1:
        return {"$and": conditions}
    return None


def append_unique_chunks(base_chunks: List[Dict[str, Any]], new_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids = {c.get("id") for c in base_chunks if c.get("id")}
    merged = list(base_chunks)
    for chunk in new_chunks:
        cid = chunk.get("id")
        if cid:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
        merged.append(chunk)
    return merged


def apply_question_filters(question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kb_chunks = list(chunks)
    ascii_terms = re.findall(r"[A-Za-z0-9-]+", question)
    if ascii_terms:
        filtered = [c for c in kb_chunks if any(t in (c.get("content", "") or "") for t in ascii_terms)]
        if filtered:
            kb_chunks = filtered
    if "毕业设计" in question:
        filtered = [c for c in kb_chunks if "毕业设计" in (c.get("doc_name", "") or "")]
        if filtered:
            kb_chunks = filtered
    return kb_chunks


def rerank_merged_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
    reranker: Any,
) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    if not reranker:
        return chunks[:top_k]
    try:
        reranked = reranker.rerank(query, chunks[: max(top_k * 3, top_k)])
        return reranked[:top_k]
    except Exception as exc:
        logger.warning(f"[Retriever] Rerank merged chunks failed, fallback original ranking: {exc}")
        return chunks[:top_k]


def rewrite_query(
    question: str,
    ask_fn: Callable[..., str],
    semantic_rewrite_prompt: str,
    rewrite_temperature: float,
) -> str:
    prompt = semantic_rewrite_prompt.format(question=question)
    rewritten = ask_fn(prompt, temperature=rewrite_temperature).strip()
    return rewritten if 0 < len(rewritten) <= 120 else question


async def rewrite_query_async(
    question: str,
    ask_async_fn: Callable[..., Any],
    semantic_rewrite_prompt: str,
    rewrite_temperature: float,
) -> str:
    prompt = semantic_rewrite_prompt.format(question=question)
    rewritten = (await ask_async_fn(prompt, temperature=rewrite_temperature)).strip()
    return rewritten if 0 < len(rewritten) <= 120 else question


def build_dual_queries(
    question: str,
    ask_fn: Callable[..., str],
    semantic_rewrite_prompt: str,
    keyword_expansion_prompt: str,
    semantic_rewrite_temperature: float,
    keyword_expansion_temperature: float,
) -> List[str]:
    semantic_query = question
    keyword_query = question
    try:
        semantic_candidate = ask_fn(
            semantic_rewrite_prompt.format(question=question),
            temperature=semantic_rewrite_temperature,
        ).strip()
        if 0 < len(semantic_candidate) <= 120:
            semantic_query = semantic_candidate
    except Exception as exc:
        logger.warning(f"[Retriever] 语义改写失败，回退原问题: {exc}")
    try:
        keywords = ask_fn(
            keyword_expansion_prompt.format(question=question),
            temperature=keyword_expansion_temperature,
        ).strip()
        if 0 < len(keywords) <= 80:
            keyword_query = f"{question} {keywords}"
    except Exception as exc:
        logger.warning(f"[Retriever] 关键词扩展失败，回退原问题: {exc}")
    queries: List[str] = []
    for q in (semantic_query, keyword_query):
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)
    return queries if queries else [question]


async def build_dual_queries_async(
    question: str,
    ask_async_fn: Callable[..., Any],
    semantic_rewrite_prompt: str,
    keyword_expansion_prompt: str,
    semantic_rewrite_temperature: float,
    keyword_expansion_temperature: float,
) -> List[str]:
    semantic_query = question
    keyword_query = question
    try:
        semantic_task = ask_async_fn(
            semantic_rewrite_prompt.format(question=question),
            temperature=semantic_rewrite_temperature,
        )
        keyword_task = ask_async_fn(
            keyword_expansion_prompt.format(question=question),
            temperature=keyword_expansion_temperature,
        )
        semantic_candidate, keywords = await asyncio.gather(semantic_task, keyword_task)
        semantic_candidate = (semantic_candidate or "").strip()
        keywords = (keywords or "").strip()
        if 0 < len(semantic_candidate) <= 120:
            semantic_query = semantic_candidate
        if 0 < len(keywords) <= 80:
            keyword_query = f"{question} {keywords}"
    except Exception as exc:
        logger.warning(f"[Retriever] 异步双查询构建失败，回退原问题: {exc}")
    queries: List[str] = []
    for q in (semantic_query, keyword_query):
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)
    return queries if queries else [question]
