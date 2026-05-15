"""Retrieval orchestration pipeline for RAG capability."""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from typing import Any, Callable, Dict, List, Optional

from config_runtime import (
    LLM_TEMPERATURE_KEYWORD_EXPANSION,
    LLM_TEMPERATURE_METADATA_FILTER,
    LLM_TEMPERATURE_SEMANTIC_REWRITE,
    RAG_EXPANSION_MIN_IMPROVEMENT,
    RAG_EXPANSION_TOP_K,
    RAG_QUALITY_MIN_HITS,
    RAG_QUALITY_MIN_SIMILARITY,
    RAG_QUALITY_MIN_SOURCE_DIVERSITY,
    RAG_QUALITY_THRESHOLD,
    RETRIEVAL_FAST_PATH_ENABLED,
    RETRIEVAL_FAST_PATH_QUALITY_MARGIN,
    RETRIEVAL_FAST_PATH_SKIP_COMPLEX,
    RETRIEVAL_METRICS_ENABLED,
    RETRIEVAL_METRICS_LOG_PATH,
    RETRIEVAL_METRICS_WINDOW,
    VECTOR_SEARCH_MAX_WORKERS,
    VECTOR_SEARCH_TOP_K,
)
from utils.logger import logger

from .diagnostics import record_retrieval_metrics
from .quality import (
    evaluate_retrieval_quality,
    fast_path_target,
    is_fast_path_good_enough,
    is_low_retrieval_quality,
)
from .retriever import (
    append_unique_chunks,
    apply_question_filters,
    build_dual_queries,
    build_dual_queries_async,
    parse_metadata_filter,
    rerank_merged_chunks,
    rewrite_query,
    rewrite_query_async,
)

class RagRetrievalPipeline:
    def __init__(
        self,
        *,
        vector_store: Any,
        render_prompt_fn: Callable[..., str],
        ask_fn: Callable[..., str],
        ask_async_fn: Callable[..., Any],
        is_complex_question_fn: Callable[[str], bool],
    ):
        self.vector_store = vector_store
        self.render_prompt = render_prompt_fn
        self.ask_fn = ask_fn
        self.ask_async_fn = ask_async_fn
        self.is_complex_question = is_complex_question_fn

    def _record_retrieval_metrics(
        self,
        *,
        duration_ms: float,
        question: str,
        search_queries: List[str],
        metadata_filter: Optional[Dict[str, Any]],
        expanded: bool,
        quality: Dict[str, Any],
        result_count: int,
    ) -> None:
        record_retrieval_metrics(
            self,
            enabled=RETRIEVAL_METRICS_ENABLED,
            window_size=RETRIEVAL_METRICS_WINDOW,
            log_path=RETRIEVAL_METRICS_LOG_PATH,
            vector_store=self.vector_store,
            duration_ms=duration_ms,
            question=question,
            search_queries=search_queries,
            metadata_filter=metadata_filter,
            expanded=expanded,
            quality=quality,
            result_count=result_count,
        )

    def _is_low_quality(self, quality: Dict[str, Any]) -> bool:
        return is_low_retrieval_quality(
            quality,
            quality_threshold=RAG_QUALITY_THRESHOLD,
            min_hits=RAG_QUALITY_MIN_HITS,
            min_similarity=RAG_QUALITY_MIN_SIMILARITY,
            min_source_diversity=RAG_QUALITY_MIN_SOURCE_DIVERSITY,
        )

    def _is_fast_path_good_enough(self, quality: Dict[str, Any]) -> bool:
        target = fast_path_target(RAG_QUALITY_THRESHOLD, RETRIEVAL_FAST_PATH_QUALITY_MARGIN)
        return is_fast_path_good_enough(
            quality,
            target_score=target,
            min_hits=RAG_QUALITY_MIN_HITS,
            min_similarity=RAG_QUALITY_MIN_SIMILARITY,
            min_source_diversity=RAG_QUALITY_MIN_SOURCE_DIVERSITY,
        )

    def run(self, *, question: str, final_use_kb: bool) -> Dict[str, Any]:
        if not final_use_kb:
            return {"kb_chunks": [], "sources": [], "trace": "Retriever: Skipped", "retrieval_quality": {"score": 0.0}}

        started = time.perf_counter()
        metadata_filter = None
        try:
            filter_prompt = self.render_prompt("metadata_filter", question=question)
            filter_json = self.ask_fn(filter_prompt, temperature=LLM_TEMPERATURE_METADATA_FILTER).strip()
            metadata_filter = parse_metadata_filter(filter_json)
            if metadata_filter:
                logger.info(f"[Retriever] 提取到元数据过滤条件: {metadata_filter}")
        except Exception as e:
            logger.warning(f"[Retriever] 元数据提取失败: {e}")

        top_k = VECTOR_SEARCH_TOP_K
        expanded = False
        search_queries = [question]

        fast_path_enabled = RETRIEVAL_FAST_PATH_ENABLED and not (
            RETRIEVAL_FAST_PATH_SKIP_COMPLEX and self.is_complex_question(question)
        )
        if fast_path_enabled:
            raw_fast_chunks = self.vector_store.search(
                question,
                top_k=top_k,
                filter=metadata_filter,
                search_mode="hybrid",
            )
            if not raw_fast_chunks and metadata_filter:
                raw_fast_chunks = self.vector_store.search(question, top_k=top_k, filter=None, search_mode="hybrid")
            kb_fast_chunks = apply_question_filters(question, raw_fast_chunks)
            quality_fast = evaluate_retrieval_quality(kb_fast_chunks, top_k)
            if self._is_fast_path_good_enough(quality_fast):
                quality_fast["expanded"] = False
                quality_fast["fast_path"] = True
                sources = sorted({c.get("doc_name", "") for c in kb_fast_chunks if c.get("doc_name")})
                self._record_retrieval_metrics(
                    duration_ms=(time.perf_counter() - started) * 1000,
                    question=question,
                    search_queries=search_queries,
                    metadata_filter=metadata_filter,
                    expanded=False,
                    quality=quality_fast,
                    result_count=len(kb_fast_chunks),
                )
                return {
                    "kb_chunks": kb_fast_chunks,
                    "sources": sources,
                    "trace": (
                        f"Retriever: found {len(kb_fast_chunks)} chunks "
                        f"(filter={metadata_filter}, quality={quality_fast['score']:.2f}, expanded=False, strategy=fast)"
                    ),
                    "retrieval_quality": quality_fast,
                }

        search_queries = build_dual_queries(
            question,
            ask_fn=self.ask_fn,
            semantic_rewrite_prompt=self.render_prompt("semantic_rewrite", question=question),
            keyword_expansion_prompt=self.render_prompt("keyword_expansion", question=question),
            semantic_rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            keyword_expansion_temperature=LLM_TEMPERATURE_KEYWORD_EXPANSION,
        )
        raw_kb_chunks: List[Dict[str, Any]] = []
        max_workers = max(1, min(VECTOR_SEARCH_MAX_WORKERS, len(search_queries)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.vector_store.search, q, top_k=top_k, filter=metadata_filter, search_mode="hybrid")
                for q in search_queries
            ]
            for f in futures:
                try:
                    raw_kb_chunks = append_unique_chunks(raw_kb_chunks, f.result())
                except Exception as e:
                    logger.warning(f"[Retriever] 子查询失败，已跳过: {e}")
        if not raw_kb_chunks and metadata_filter:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(self.vector_store.search, q, top_k=top_k, filter=None, search_mode="hybrid")
                    for q in search_queries
                ]
                for f in futures:
                    try:
                        raw_kb_chunks = append_unique_chunks(raw_kb_chunks, f.result())
                    except Exception as e:
                        logger.warning(f"[Retriever] 回退子查询失败，已跳过: {e}")

        raw_kb_chunks = rerank_merged_chunks(
            question,
            raw_kb_chunks,
            top_k=max(top_k * 2, top_k),
            reranker=getattr(self.vector_store, "reranker", None),
        )
        kb_chunks = apply_question_filters(question, raw_kb_chunks)
        quality = evaluate_retrieval_quality(kb_chunks, top_k)

        if self._is_low_quality(quality):
            expanded = True
            rewritten_query = rewrite_query(
                question,
                ask_fn=self.ask_fn,
                semantic_rewrite_prompt=self.render_prompt("semantic_rewrite", question=question),
                rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            )
            expanded_chunks = self.vector_store.search(
                rewritten_query,
                top_k=RAG_EXPANSION_TOP_K,
                filter=metadata_filter,
                search_mode="hybrid",
            )
            if not expanded_chunks and metadata_filter:
                expanded_chunks = self.vector_store.search(
                    rewritten_query,
                    top_k=RAG_EXPANSION_TOP_K,
                    filter=None,
                    search_mode="hybrid",
                )
            expanded_chunks = rerank_merged_chunks(
                rewritten_query,
                expanded_chunks,
                top_k=max(RAG_EXPANSION_TOP_K, top_k),
                reranker=getattr(self.vector_store, "reranker", None),
            )
            expanded_chunks = apply_question_filters(question, expanded_chunks)
            expanded_chunks = expanded_chunks[:RAG_EXPANSION_TOP_K]
            expanded_quality = evaluate_retrieval_quality(expanded_chunks, RAG_EXPANSION_TOP_K)
            if expanded_quality["score"] >= (quality["score"] + RAG_EXPANSION_MIN_IMPROVEMENT):
                kb_chunks = expanded_chunks
                quality = expanded_quality

        sources = sorted({c.get("doc_name", "") for c in kb_chunks if c.get("doc_name")})
        quality["expanded"] = expanded
        quality["fast_path"] = False
        self._record_retrieval_metrics(
            duration_ms=(time.perf_counter() - started) * 1000,
            question=question,
            search_queries=search_queries,
            metadata_filter=metadata_filter,
            expanded=expanded,
            quality=quality,
            result_count=len(kb_chunks),
        )
        return {
            "kb_chunks": kb_chunks,
            "sources": sources,
            "trace": (
                f"Retriever: found {len(kb_chunks)} chunks "
                f"(filter={metadata_filter}, quality={quality['score']:.2f}, expanded={expanded}, strategy=slow)"
            ),
            "retrieval_quality": quality,
        }

    async def run_async(self, *, question: str, final_use_kb: bool) -> Dict[str, Any]:
        if not final_use_kb:
            return {"kb_chunks": [], "sources": [], "trace": "Retriever: Skipped", "retrieval_quality": {"score": 0.0}}

        started = time.perf_counter()
        metadata_filter = None
        try:
            filter_prompt = self.render_prompt("metadata_filter", question=question)
            filter_json = await self.ask_async_fn(filter_prompt, temperature=LLM_TEMPERATURE_METADATA_FILTER)
            metadata_filter = parse_metadata_filter(filter_json)
            if metadata_filter:
                logger.info(f"[Retriever] 提取到元数据过滤条件 (Async): {metadata_filter}")
        except Exception as e:
            logger.warning(f"[Retriever] 元数据提取失败 (Async): {e}")

        loop = asyncio.get_running_loop()
        top_k = VECTOR_SEARCH_TOP_K
        expanded = False
        search_queries = [question]

        fast_path_enabled = RETRIEVAL_FAST_PATH_ENABLED and not (
            RETRIEVAL_FAST_PATH_SKIP_COMPLEX and self.is_complex_question(question)
        )
        if fast_path_enabled:
            fast_chunks = await loop.run_in_executor(
                None, lambda: self.vector_store.search(question, top_k=top_k, filter=metadata_filter, search_mode="hybrid")
            )
            if not fast_chunks and metadata_filter:
                fast_chunks = await loop.run_in_executor(
                    None, lambda: self.vector_store.search(question, top_k=top_k, filter=None, search_mode="hybrid")
                )
            kb_fast_chunks = apply_question_filters(question, fast_chunks)
            quality_fast = evaluate_retrieval_quality(kb_fast_chunks, top_k)
            if self._is_fast_path_good_enough(quality_fast):
                quality_fast["expanded"] = False
                quality_fast["fast_path"] = True
                sources = sorted({c.get("doc_name", "") for c in kb_fast_chunks if c.get("doc_name")})
                self._record_retrieval_metrics(
                    duration_ms=(time.perf_counter() - started) * 1000,
                    question=question,
                    search_queries=search_queries,
                    metadata_filter=metadata_filter,
                    expanded=False,
                    quality=quality_fast,
                    result_count=len(kb_fast_chunks),
                )
                return {
                    "kb_chunks": kb_fast_chunks,
                    "sources": sources,
                    "trace": (
                        f"Retriever: found {len(kb_fast_chunks)} chunks "
                        f"(quality={quality_fast['score']:.2f}, expanded=False, strategy=fast, async)"
                    ),
                    "retrieval_quality": quality_fast,
                }

        search_queries = await build_dual_queries_async(
            question,
            ask_async_fn=self.ask_async_fn,
            semantic_rewrite_prompt=self.render_prompt("semantic_rewrite", question=question),
            keyword_expansion_prompt=self.render_prompt("keyword_expansion", question=question),
            semantic_rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            keyword_expansion_temperature=LLM_TEMPERATURE_KEYWORD_EXPANSION,
        )
        initial_tasks = [
            loop.run_in_executor(
                None, lambda q=q: self.vector_store.search(q, top_k=top_k, filter=metadata_filter, search_mode="hybrid")
            )
            for q in search_queries
        ]
        initial_results = await asyncio.gather(*initial_tasks)
        raw_kb_chunks: List[Dict[str, Any]] = []
        for result in initial_results:
            raw_kb_chunks = append_unique_chunks(raw_kb_chunks, result)
        if not raw_kb_chunks and metadata_filter:
            fallback_tasks = [
                loop.run_in_executor(None, lambda q=q: self.vector_store.search(q, top_k=top_k, filter=None, search_mode="hybrid"))
                for q in search_queries
            ]
            fallback_results = await asyncio.gather(*fallback_tasks)
            for result in fallback_results:
                raw_kb_chunks = append_unique_chunks(raw_kb_chunks, result)

        raw_kb_chunks = rerank_merged_chunks(
            question,
            raw_kb_chunks,
            top_k=max(top_k * 2, top_k),
            reranker=getattr(self.vector_store, "reranker", None),
        )
        kb_chunks = apply_question_filters(question, raw_kb_chunks)
        quality = evaluate_retrieval_quality(kb_chunks, top_k)

        if self._is_low_quality(quality):
            expanded = True
            rewritten_query = await rewrite_query_async(
                question,
                ask_async_fn=self.ask_async_fn,
                semantic_rewrite_prompt=self.render_prompt("semantic_rewrite", question=question),
                rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            )
            expanded_chunks = await loop.run_in_executor(
                None,
                lambda: self.vector_store.search(
                    rewritten_query,
                    top_k=RAG_EXPANSION_TOP_K,
                    filter=metadata_filter,
                    search_mode="hybrid",
                ),
            )
            if not expanded_chunks and metadata_filter:
                expanded_chunks = await loop.run_in_executor(
                    None,
                    lambda: self.vector_store.search(
                        rewritten_query,
                        top_k=RAG_EXPANSION_TOP_K,
                        filter=None,
                        search_mode="hybrid",
                    ),
                )
            expanded_chunks = rerank_merged_chunks(
                rewritten_query,
                expanded_chunks,
                top_k=max(RAG_EXPANSION_TOP_K, top_k),
                reranker=getattr(self.vector_store, "reranker", None),
            )
            expanded_chunks = apply_question_filters(question, expanded_chunks)
            expanded_chunks = expanded_chunks[:RAG_EXPANSION_TOP_K]
            expanded_quality = evaluate_retrieval_quality(expanded_chunks, RAG_EXPANSION_TOP_K)
            if expanded_quality["score"] >= (quality["score"] + RAG_EXPANSION_MIN_IMPROVEMENT):
                kb_chunks = expanded_chunks
                quality = expanded_quality

        sources = sorted({c.get("doc_name", "") for c in kb_chunks if c.get("doc_name")})
        quality["expanded"] = expanded
        quality["fast_path"] = False
        self._record_retrieval_metrics(
            duration_ms=(time.perf_counter() - started) * 1000,
            question=question,
            search_queries=search_queries,
            metadata_filter=metadata_filter,
            expanded=expanded,
            quality=quality,
            result_count=len(kb_chunks),
        )
        return {
            "kb_chunks": kb_chunks,
            "sources": sources,
            "trace": (
                f"Retriever: found {len(kb_chunks)} chunks "
                f"(quality={quality['score']:.2f}, expanded={expanded}, strategy=slow, async)"
            ),
            "retrieval_quality": quality,
        }
