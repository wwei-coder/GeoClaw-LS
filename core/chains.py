import re
import json
import math
import asyncio
import os
import time
import threading
import concurrent.futures
from collections import deque
from typing import Dict, List, Any, Optional
from loguru import logger
from utils.ollama_client import ask_ollama, ask_ollama_stream, ask_ollama_async, ask_ollama_stream_async
from agent.brain.prompt_catalog import get_prompt_catalog
from core.planner import plan_task, plan_task_async
from capabilities.memory.summary import summarize_dialog
from core.question_classifier import is_complex_question, is_follow_up_question, is_follow_up_question_async
from core.context_judge import judge_context_relevance, judge_context_relevance_async
from capabilities.rag.retrieval.diagnostics import record_retrieval_metrics
from capabilities.rag.retrieval.quality import (
    evaluate_retrieval_quality,
    fast_path_target,
    is_fast_path_good_enough,
    is_low_retrieval_quality,
)
from capabilities.rag.retrieval.retriever import (
    append_unique_chunks,
    apply_question_filters,
    build_dual_queries,
    build_dual_queries_async,
    parse_metadata_filter,
    rerank_merged_chunks,
    rewrite_query,
    rewrite_query_async,
)
from core.config import (
    MAX_CONTEXT_LEN,
    MAX_HISTORY_ROUNDS,
    ANALYSIS_KEYWORDS,
    MATH_KEYWORDS,
    COMPLEX_CALC_KEYWORDS,
    VECTOR_SEARCH_TOP_K,
    VECTOR_SEARCH_MAX_WORKERS,
    RAG_EXPANSION_TOP_K,
    RAG_EXPANSION_MIN_IMPROVEMENT,
    RAG_QUALITY_THRESHOLD,
    RAG_QUALITY_MIN_HITS,
    RAG_QUALITY_MIN_SIMILARITY,
    RAG_QUALITY_MIN_SOURCE_DIVERSITY,
    LLM_TEMPERATURE_SEMANTIC_REWRITE,
    LLM_TEMPERATURE_KEYWORD_EXPANSION,
    LLM_TEMPERATURE_METADATA_FILTER,
    SYNTHESIS_MAX_EVIDENCE_CHARS,
    RETRIEVAL_METRICS_ENABLED,
    RETRIEVAL_METRICS_WINDOW,
    RETRIEVAL_METRICS_LOG_PATH,
    RETRIEVAL_FAST_PATH_ENABLED,
    RETRIEVAL_FAST_PATH_QUALITY_MARGIN,
    RETRIEVAL_FAST_PATH_SKIP_COMPLEX
)

#LangChain Compatibility Layer
#Ensure Chain is available and has .invoke() method (LCEL standard)
try:
    from langchain.chains import Chain as _Chain
except ImportError:
    try:
        from langchain.chains.base import Chain as _Chain
    except ImportError:
        # Fallback for when LangChain is not installed
        class _Chain:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
            def __call__(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return self._call(inputs)
            def _call(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                raise NotImplementedError

class Chain(_Chain):
    """
    Robust Chain wrapper that guarantees .invoke() exists.
    Compatible with both real LangChain (old & new) and simulation mode.
    """
    def invoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        if hasattr(super(), "invoke"):
            return super().invoke(inputs, **kwargs)
        # Fallback for older LangChain (<0.1) or simulation
        return self(inputs, **kwargs)

    async def ainvoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        if hasattr(super(), "ainvoke"):
            return await super().ainvoke(inputs, **kwargs)
        # Fallback: run sync _call in thread pool
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self(inputs, **kwargs))

    def __call__(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # If the parent has __call__, use it (LangChain standard)
        # In simulation mode, this calls our _call
        return super().__call__(inputs, **kwargs)

try:
    from langchain_core.callbacks.manager import CallbackManagerForChainRun
except ImportError:
    CallbackManagerForChainRun = Any


class SmallTalkChain(Chain):
    """Chain for handling Small Talk"""
    agent_core: Any = None

    @property
    def input_keys(self) -> List[str]:
        return ["question"]

    @property
    def output_keys(self) -> List[str]:
        return ["answer", "confidence", "sources"]

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        question = inputs["question"]
        prompt = get_prompt_catalog().render("small_talk", question=question)
        final_answer = ask_ollama(prompt, temperature=self.agent_core.temperature).strip()
        
        sid = self.agent_core.get_active_session_id()
        try:
            # Sync DB save
            self.agent_core.db_manager.add_conversation(
                self.agent_core.user_id, 
                question, 
                final_answer, 
                session_id=sid
            )
        except Exception as e:
            logger.warning(f"记忆查询记录保存失败: {e}")
            
        return {"answer": final_answer, "confidence": 0.0, "sources": []}

class MemoryQueryChain(Chain):
    """Chain for handling Memory Queries"""
    agent_core: Any = None

    @property
    def input_keys(self) -> List[str]:
        return ["question"]

    @property
    def output_keys(self) -> List[str]:
        return ["answer", "confidence", "sources"]

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        question = inputs["question"]
        q = (question or "")
        want_answer = any(k in q for k in ("你刚才说", "上一轮回答", "刚才回答", "你上次说"))
        sid = self.agent_core.get_active_session_id()
        row = self.agent_core.db_manager.get_last_conversation(self.agent_core.user_id, session_id=sid)
        
        if not row:
            final_answer = "无法从记录确定上一轮内容（目前还没有历史对话）。"
        else:
            last_q, last_a = row
            if want_answer:
                final_answer = f"上一轮回答是：{last_a}"
            else:
                final_answer = f"上一轮问题是：{last_q}"

        try:
            self.agent_core.db_manager.add_conversation(
                self.agent_core.user_id, 
                question, 
                final_answer, 
                session_id=sid
            )
        except Exception as e:
            logger.warning(f"记忆查询记录保存失败: {e}")
        
        return {"answer": final_answer, "confidence": 0.0, "sources": []}

# ======================  LangChain Components

class PlannerChain(Chain):
    """Chain for Task Planning"""
    output_key: str = "plan"
    
    @property
    def input_keys(self) -> List[str]:
        return ["question"]

    @property
    def output_keys(self) -> List[str]:
        return [self.output_key, "trace"]

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        question = inputs["question"]
        plan = plan_task(question)
        logger.info("[PlannerChain] 任务计划：")
        for i, s in enumerate(plan["steps"], 1):
            logger.info(f"  {i}. {s['tool']} → {s['task']}")
        
        trace = f"Planner: {len(plan['steps'])} steps"
        return {self.output_key: plan, "trace": trace}

    async def ainvoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        question = inputs["question"]
        plan = await plan_task_async(question)
        logger.info("[PlannerChain] 任务计划 (Async)：")
        for i, s in enumerate(plan["steps"], 1):
            logger.info(f"  {i}. {s['tool']} → {s['task']}")
        
        trace = f"Planner: {len(plan['steps'])} steps"
        return {self.output_key: plan, "trace": trace}

class HeuristicDecisionChain(Chain):
    """Chain for Rule-based Context & Tool Decision (No RL)"""
    agent_core: Any = None
    output_key: str = "decision"

    @property
    def input_keys(self) -> List[str]:
        return ["question", "plan"]

    @property
    def output_keys(self) -> List[str]:
        return ["context_score", "is_follow", "force_tool", "final_use_kb", "trace"]

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        core = self.agent_core
        question = inputs["question"]
        plan = inputs["plan"]
        
        # Context & Follow-up logic
        context_score = judge_context_relevance(core.summary_memory, question)
        follow_candidate = is_follow_up_question(core.summary_memory, question)
        is_follow = bool(follow_candidate and context_score > 0.0)
        
        return self._make_decision(question, plan, context_score, is_follow)

    async def ainvoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        core = self.agent_core
        question = inputs["question"]
        plan = inputs["plan"]
        
        # Context & Follow-up logic
        context_score = await judge_context_relevance_async(core.summary_memory, question)
        follow_candidate = await is_follow_up_question_async(core.summary_memory, question)
        is_follow = bool(follow_candidate and context_score > 0.0)
        
        return self._make_decision(question, plan, context_score, is_follow)

    def _make_decision(self, question, plan, context_score, is_follow):
        planner_need_kb = bool(plan.get("need_kb", False))
        
        # Default decisions
        final_use_kb = planner_need_kb
        force_tool = None
        
        # --- Heuristic Rules ---
        
        # 1. Math Detection
        is_analysis = any(k in (question or "").lower() for k in ANALYSIS_KEYWORDS)
        
        if any(k in (question or "") for k in MATH_KEYWORDS) and not is_analysis:
            # Simple regex check for digits
            if re.search(r"\d", question):
                logger.info("[Rule Override] 检测到计算意图，建议使用 CALCULATOR")
                force_tool = "CALCULATOR"
                
                # Check if we need RAG for variables
                if any(kw in question for kw in COMPLEX_CALC_KEYWORDS):
                    final_use_kb = True
                    logger.info("[Rule Override] 检测到复杂/查表计算，保留 RAG")
                else:
                    final_use_kb = False
                    logger.info("[Rule Override] 检测到纯计算，关闭 RAG")

        # 2. Context Awareness
        # If user asks a follow-up or complex question, ensure KB is enabled if it makes sense
        if is_follow or is_complex_question(question):
            final_use_kb = True
        
        # 3. Discovery Check
        has_discovery = any(s.get("tool") == "DISCOVERY" for s in plan.get("steps", []))
        if has_discovery:
            final_use_kb = True

        logger.debug(f"[HeuristicDecision] UseKB={final_use_kb}, ForceTool={force_tool}")
        
        return {
            "context_score": context_score,
            "is_follow": is_follow,
            "force_tool": force_tool,
            "final_use_kb": final_use_kb,
            "trace": f"Decision: use_kb={final_use_kb}, force={force_tool}"
        }

class RetrieverChain(Chain):
    """Chain for Document Retrieval"""
    vector_store: Any = None
    
    @property
    def input_keys(self) -> List[str]:
        return ["question", "final_use_kb"]

    @property
    def output_keys(self) -> List[str]:
        return ["kb_chunks", "sources", "trace", "retrieval_quality"]

    def _parse_metadata_filter(self, filter_json: str) -> Optional[Dict[str, Any]]:
        return parse_metadata_filter(filter_json)

    def _append_unique_chunks(self, base_chunks: List[Dict[str, Any]], new_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return append_unique_chunks(base_chunks, new_chunks)

    def _apply_question_filters(self, question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return apply_question_filters(question, chunks)

    def _chunk_similarity_score(self, chunk: Dict[str, Any]) -> float:
        from capabilities.rag.retrieval.quality import chunk_similarity_score

        return chunk_similarity_score(chunk)

    def _evaluate_quality(self, chunks: List[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
        return evaluate_retrieval_quality(chunks, top_k)

    def _is_low_quality(self, quality: Dict[str, Any]) -> bool:
        return is_low_retrieval_quality(
            quality,
            quality_threshold=RAG_QUALITY_THRESHOLD,
            min_hits=RAG_QUALITY_MIN_HITS,
            min_similarity=RAG_QUALITY_MIN_SIMILARITY,
            min_source_diversity=RAG_QUALITY_MIN_SOURCE_DIVERSITY,
        )

    def _rerank_merged_chunks(self, query: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        reranker = getattr(self.vector_store, "reranker", None)
        return rerank_merged_chunks(query, chunks, top_k=top_k, reranker=reranker)

    def _rewrite_query(self, question: str) -> str:
        prompt = get_prompt_catalog().render("semantic_rewrite", question=question)
        return rewrite_query(
            question,
            ask_fn=ask_ollama,
            semantic_rewrite_prompt=prompt,
            rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
        )

    async def _rewrite_query_async(self, question: str) -> str:
        prompt = get_prompt_catalog().render("semantic_rewrite", question=question)
        return await rewrite_query_async(
            question,
            ask_async_fn=ask_ollama_async,
            semantic_rewrite_prompt=prompt,
            rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
        )

    def _build_dual_queries(self, question: str) -> List[str]:
        semantic_prompt = get_prompt_catalog().render("semantic_rewrite", question=question)
        keyword_prompt = get_prompt_catalog().render("keyword_expansion", question=question)
        return build_dual_queries(
            question,
            ask_fn=ask_ollama,
            semantic_rewrite_prompt=semantic_prompt,
            keyword_expansion_prompt=keyword_prompt,
            semantic_rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            keyword_expansion_temperature=LLM_TEMPERATURE_KEYWORD_EXPANSION,
        )

    async def _build_dual_queries_async(self, question: str) -> List[str]:
        semantic_prompt = get_prompt_catalog().render("semantic_rewrite", question=question)
        keyword_prompt = get_prompt_catalog().render("keyword_expansion", question=question)
        return await build_dual_queries_async(
            question,
            ask_async_fn=ask_ollama_async,
            semantic_rewrite_prompt=semantic_prompt,
            keyword_expansion_prompt=keyword_prompt,
            semantic_rewrite_temperature=LLM_TEMPERATURE_SEMANTIC_REWRITE,
            keyword_expansion_temperature=LLM_TEMPERATURE_KEYWORD_EXPANSION,
        )

    def _ensure_metrics(self):
        from capabilities.rag.retrieval.diagnostics import ensure_metrics_state

        ensure_metrics_state(self, RETRIEVAL_METRICS_WINDOW)

    def _record_retrieval_metrics(
        self,
        duration_ms: float,
        question: str,
        search_queries: List[str],
        metadata_filter: Optional[Dict[str, Any]],
        expanded: bool,
        quality: Dict[str, Any],
        result_count: int
    ):
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

    def _fast_path_target(self) -> float:
        return fast_path_target(RAG_QUALITY_THRESHOLD, RETRIEVAL_FAST_PATH_QUALITY_MARGIN)

    def _is_fast_path_good_enough(self, quality: Dict[str, Any]) -> bool:
        return is_fast_path_good_enough(
            quality,
            target_score=self._fast_path_target(),
            min_hits=RAG_QUALITY_MIN_HITS,
            min_similarity=RAG_QUALITY_MIN_SIMILARITY,
            min_source_diversity=RAG_QUALITY_MIN_SOURCE_DIVERSITY,
        )

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        if not inputs.get("final_use_kb", False):
            return {"kb_chunks": [], "sources": [], "trace": "Retriever: Skipped", "retrieval_quality": {"score": 0.0}}
            
        started = time.perf_counter()
        question = inputs["question"]
        metadata_filter = None
        try:
            filter_prompt = get_prompt_catalog().render("metadata_filter", question=question)
            filter_json = ask_ollama(filter_prompt, temperature=LLM_TEMPERATURE_METADATA_FILTER).strip()
            metadata_filter = self._parse_metadata_filter(filter_json)
            if metadata_filter:
                logger.info(f"[Retriever] 提取到元数据过滤条件: {metadata_filter}")
        except Exception as e:
            logger.warning(f"[Retriever] 元数据提取失败: {e}")

        top_k = VECTOR_SEARCH_TOP_K
        expanded = False
        search_queries = [question]

        fast_path_enabled = RETRIEVAL_FAST_PATH_ENABLED and not (
            RETRIEVAL_FAST_PATH_SKIP_COMPLEX and is_complex_question(question)
        )
        if fast_path_enabled:
            raw_fast_chunks = self.vector_store.search(
                question,
                top_k=top_k,
                filter=metadata_filter,
                search_mode="hybrid"
            )
            if not raw_fast_chunks and metadata_filter:
                raw_fast_chunks = self.vector_store.search(
                    question,
                    top_k=top_k,
                    filter=None,
                    search_mode="hybrid"
                )
            kb_fast_chunks = self._apply_question_filters(question, raw_fast_chunks)
            quality_fast = self._evaluate_quality(kb_fast_chunks, top_k)
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
                    result_count=len(kb_fast_chunks)
                )
                return {
                    "kb_chunks": kb_fast_chunks,
                    "sources": sources,
                    "trace": (
                        f"Retriever: found {len(kb_fast_chunks)} chunks "
                        f"(filter={metadata_filter}, quality={quality_fast['score']:.2f}, expanded=False, strategy=fast)"
                    ),
                    "retrieval_quality": quality_fast
                }

        search_queries = self._build_dual_queries(question)
        raw_kb_chunks: List[Dict[str, Any]] = []
        max_workers = max(1, min(VECTOR_SEARCH_MAX_WORKERS, len(search_queries)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self.vector_store.search,
                    q,
                    top_k=top_k,
                    filter=metadata_filter,
                    search_mode="hybrid"
                )
                for q in search_queries
            ]
            for f in futures:
                try:
                    raw_kb_chunks = self._append_unique_chunks(raw_kb_chunks, f.result())
                except Exception as e:
                    logger.warning(f"[Retriever] 子查询失败，已跳过: {e}")
        if not raw_kb_chunks and metadata_filter:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self.vector_store.search,
                        q,
                        top_k=top_k,
                        filter=None,
                        search_mode="hybrid"
                    )
                    for q in search_queries
                ]
                for f in futures:
                    try:
                        raw_kb_chunks = self._append_unique_chunks(raw_kb_chunks, f.result())
                    except Exception as e:
                        logger.warning(f"[Retriever] 回退子查询失败，已跳过: {e}")

        raw_kb_chunks = self._rerank_merged_chunks(question, raw_kb_chunks, top_k=max(top_k * 2, top_k))
        kb_chunks = self._apply_question_filters(question, raw_kb_chunks)
        quality = self._evaluate_quality(kb_chunks, top_k)

        if self._is_low_quality(quality):
            expanded = True
            rewritten_query = self._rewrite_query(question)
            expanded_chunks = self.vector_store.search(
                rewritten_query,
                top_k=RAG_EXPANSION_TOP_K,
                filter=metadata_filter,
                search_mode="hybrid"
            )
            if not expanded_chunks and metadata_filter:
                expanded_chunks = self.vector_store.search(
                    rewritten_query,
                    top_k=RAG_EXPANSION_TOP_K,
                    filter=None,
                    search_mode="hybrid"
                )
            expanded_chunks = self._rerank_merged_chunks(
                rewritten_query,
                expanded_chunks,
                top_k=max(RAG_EXPANSION_TOP_K, top_k)
            )
            expanded_chunks = self._apply_question_filters(question, expanded_chunks)
            expanded_chunks = expanded_chunks[:RAG_EXPANSION_TOP_K]
            expanded_quality = self._evaluate_quality(expanded_chunks, RAG_EXPANSION_TOP_K)
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
            result_count=len(kb_chunks)
        )
        return {
            "kb_chunks": kb_chunks, 
            "sources": sources, 
            "trace": (
                f"Retriever: found {len(kb_chunks)} chunks "
                f"(filter={metadata_filter}, quality={quality['score']:.2f}, expanded={expanded}, strategy=slow)"
            ),
            "retrieval_quality": quality
        }

    async def ainvoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        if not inputs.get("final_use_kb", False):
            return {"kb_chunks": [], "sources": [], "trace": "Retriever: Skipped", "retrieval_quality": {"score": 0.0}}
            
        started = time.perf_counter()
        question = inputs["question"]
        metadata_filter = None
        try:
            filter_prompt = get_prompt_catalog().render("metadata_filter", question=question)
            filter_json = await ask_ollama_async(filter_prompt, temperature=LLM_TEMPERATURE_METADATA_FILTER)
            metadata_filter = self._parse_metadata_filter(filter_json)
            if metadata_filter:
                logger.info(f"[Retriever] 提取到元数据过滤条件 (Async): {metadata_filter}")
        except Exception as e:
            logger.warning(f"[Retriever] 元数据提取失败 (Async): {e}")

        loop = asyncio.get_running_loop()
        top_k = VECTOR_SEARCH_TOP_K
        expanded = False
        search_queries = [question]

        fast_path_enabled = RETRIEVAL_FAST_PATH_ENABLED and not (
            RETRIEVAL_FAST_PATH_SKIP_COMPLEX and is_complex_question(question)
        )
        if fast_path_enabled:
            fast_chunks = await loop.run_in_executor(
                None,
                lambda: self.vector_store.search(question, top_k=top_k, filter=metadata_filter, search_mode="hybrid")
            )
            if not fast_chunks and metadata_filter:
                fast_chunks = await loop.run_in_executor(
                    None,
                    lambda: self.vector_store.search(question, top_k=top_k, filter=None, search_mode="hybrid")
                )
            kb_fast_chunks = self._apply_question_filters(question, fast_chunks)
            quality_fast = self._evaluate_quality(kb_fast_chunks, top_k)
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
                    result_count=len(kb_fast_chunks)
                )
                return {
                    "kb_chunks": kb_fast_chunks,
                    "sources": sources,
                    "trace": (
                        f"Retriever: found {len(kb_fast_chunks)} chunks "
                        f"(quality={quality_fast['score']:.2f}, expanded=False, strategy=fast, async)"
                    ),
                    "retrieval_quality": quality_fast
                }

        search_queries = await self._build_dual_queries_async(question)
        initial_tasks = [
            loop.run_in_executor(
                None,
                lambda q=q: self.vector_store.search(q, top_k=top_k, filter=metadata_filter, search_mode="hybrid")
            )
            for q in search_queries
        ]
        initial_results = await asyncio.gather(*initial_tasks)
        raw_kb_chunks: List[Dict[str, Any]] = []
        for result in initial_results:
            raw_kb_chunks = self._append_unique_chunks(raw_kb_chunks, result)
        if not raw_kb_chunks and metadata_filter:
            fallback_tasks = [
                loop.run_in_executor(
                    None,
                    lambda q=q: self.vector_store.search(q, top_k=top_k, filter=None, search_mode="hybrid")
                )
                for q in search_queries
            ]
            fallback_results = await asyncio.gather(*fallback_tasks)
            for result in fallback_results:
                raw_kb_chunks = self._append_unique_chunks(raw_kb_chunks, result)

        raw_kb_chunks = self._rerank_merged_chunks(question, raw_kb_chunks, top_k=max(top_k * 2, top_k))
        kb_chunks = self._apply_question_filters(question, raw_kb_chunks)
        quality = self._evaluate_quality(kb_chunks, top_k)

        if self._is_low_quality(quality):
            expanded = True
            rewritten_query = await self._rewrite_query_async(question)
            expanded_chunks = await loop.run_in_executor(
                None,
                lambda: self.vector_store.search(
                    rewritten_query,
                    top_k=RAG_EXPANSION_TOP_K,
                    filter=metadata_filter,
                    search_mode="hybrid"
                )
            )
            if not expanded_chunks and metadata_filter:
                expanded_chunks = await loop.run_in_executor(
                    None,
                    lambda: self.vector_store.search(
                        rewritten_query,
                        top_k=RAG_EXPANSION_TOP_K,
                        filter=None,
                        search_mode="hybrid"
                    )
                )
            expanded_chunks = self._rerank_merged_chunks(
                rewritten_query,
                expanded_chunks,
                top_k=max(RAG_EXPANSION_TOP_K, top_k)
            )
            expanded_chunks = self._apply_question_filters(question, expanded_chunks)
            expanded_chunks = expanded_chunks[:RAG_EXPANSION_TOP_K]
            expanded_quality = self._evaluate_quality(expanded_chunks, RAG_EXPANSION_TOP_K)
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
            result_count=len(kb_chunks)
        )
        return {
            "kb_chunks": kb_chunks, 
            "sources": sources, 
            "trace": (
                f"Retriever: found {len(kb_chunks)} chunks "
                f"(quality={quality['score']:.2f}, expanded={expanded}, strategy=slow, async)"
            ),
            "retrieval_quality": quality
        }

class SynthesisChain(Chain):
    """Chain for Final Response Synthesis"""
    agent_core: Any = None
    
    @property
    def input_keys(self) -> List[str]:
        return ["question", "step_results", "kb_chunks", "sources"]

    @property
    def output_keys(self) -> List[str]:
        return ["final_answer", "final_sources"]

    def _shrink_text_preserve_edges(self, text: str, budget: int) -> str:
        if budget <= 0:
            return ""
        if len(text) <= budget:
            return text
        if budget <= 12:
            return text[:budget]
        marker = "\n...（已压缩中间内容）...\n"
        if budget <= len(marker) + 2:
            return text[: budget - 1] + "…"
        remain = budget - len(marker)
        head_len = remain // 2
        tail_len = remain - head_len
        shrunk = text[:head_len] + marker + text[-tail_len:]
        if len(shrunk) > budget:
            shrunk = shrunk[:budget]
        return shrunk

    def _compress_step_results_for_context(self, step_results: List[str]) -> str:
        if not step_results:
            return ""
        full_steps = "\n".join(step_results)
        full_len = len(full_steps)
        if full_len <= MAX_CONTEXT_LEN:
            return full_steps

        raw_steps = [s if isinstance(s, str) else str(s) for s in step_results]
        n = len(raw_steps)
        sep_total = max(0, n - 1)
        content_budget = max(1, MAX_CONTEXT_LEN - sep_total)
        lengths = [len(s) for s in raw_steps]
        total_len = sum(lengths)
        if total_len <= content_budget:
            return full_steps

        min_each = 80
        if content_budget < n * min_each:
            min_each = max(1, content_budget // n)

        allocs = [min_each for _ in raw_steps]
        remaining = content_budget - sum(allocs)

        if remaining > 0:
            residuals = [max(0, length - min_each) for length in lengths]
            residual_total = sum(residuals)
            if residual_total > 0:
                extras = []
                used = 0
                for idx, r in enumerate(residuals):
                    extra = int(remaining * (r / residual_total))
                    extra = min(extra, r)
                    extras.append(extra)
                    used += extra
                allocs = [a + e for a, e in zip(allocs, extras)]
                remaining -= used
                if remaining > 0:
                    order = sorted(range(n), key=lambda i: residuals[i] - extras[i], reverse=True)
                    for idx in order:
                        if remaining <= 0:
                            break
                        if allocs[idx] < lengths[idx]:
                            allocs[idx] += 1
                            remaining -= 1
            if remaining > 0:
                order = sorted(range(n), key=lambda i: lengths[i], reverse=True)
                for idx in order:
                    if remaining <= 0:
                        break
                    if allocs[idx] < lengths[idx]:
                        allocs[idx] += 1
                        remaining -= 1

        compressed_steps = [
            self._shrink_text_preserve_edges(step, alloc)
            for step, alloc in zip(raw_steps, allocs)
        ]
        compressed = "\n".join(compressed_steps)
        if len(compressed) > MAX_CONTEXT_LEN:
            compressed = self._shrink_text_preserve_edges(compressed, MAX_CONTEXT_LEN)
        logger.warning(
            f"[Synthesis] ⚠️ 步骤输出超过 {MAX_CONTEXT_LEN} 字符，已按步骤预算压缩"
            f"（原始 {full_len} -> 压缩后 {len(compressed)}）"
        )
        return compressed

    def _call(self, inputs: Dict[str, Any], _run_manager: Optional[CallbackManagerForChainRun] = None) -> Dict[str, Any]:
        if inputs.get("canceled", False):
            return {"final_answer": "已取消", "final_sources": []}
            
        question = inputs["question"]
        kb_chunks = inputs.get("kb_chunks", [])
        step_results = inputs.get("step_results", [])
        sources = inputs.get("sources", [])
        stream_callback = inputs.get("stream_callback", None)

        kb_evidence = ""
        if kb_chunks:
            lines = []
            for c in kb_chunks:
                content = c.get("content", "") or ""
                if len(content) > SYNTHESIS_MAX_EVIDENCE_CHARS:
                    content = content[:SYNTHESIS_MAX_EVIDENCE_CHARS] + "…"
                lines.append(f"【{c.get('doc_name')}】\n{content}")
            kb_evidence = "\n\n".join(lines)
            
        # --- Context Safety: Truncate step_results if too long ---
        full_steps = self._compress_step_results_for_context(step_results)

        # Inject User Preferences
        user_prefs_str = ""
        if self.agent_core.user_preferences:
            prefs = []
            for k, v in self.agent_core.user_preferences.items():
                prefs.append(f"- {k}: {v}")
            user_prefs_str = "\n\n【用户偏好与习惯】\n" + "\n".join(prefs) + "\n请严格遵守上述用户偏好。"

        final_prompt = get_prompt_catalog().render(
            "synthesis_final_answer",
            question=question,
            step_results=full_steps,
            kb_evidence=kb_evidence + user_prefs_str,
        )

        final_answer = ""
        if stream_callback:
            cancel_event = getattr(self.agent_core, "_active_cancel_event", None)
            for token in ask_ollama_stream(final_prompt, temperature=self.agent_core.temperature, cancel_event=cancel_event):
                final_answer += token
                stream_callback(token)
        else:
            final_answer = ask_ollama(final_prompt, temperature=self.agent_core.temperature).strip()

        final_answer = self.agent_core._fix_terminology(final_answer, question)
        
        if sources:
            cited = [s for s in sources if s and s in final_answer]
            if cited:
                sources = cited
        
        # Memory Update
        self.agent_core.short_memory.append(f"用户：{question}")
        self.agent_core.short_memory.append(f"助手：{final_answer}")
        
        sid = self.agent_core.get_active_session_id()
        try:
            # Synchronous DB save
            self.agent_core.db_manager.add_conversation(
                self.agent_core.user_id, 
                question, 
                final_answer, 
                session_id=sid
            )
        except Exception as e:
            logger.error(f"[System] ⚠️ 对话保存失败 (DB Error): {e}")
        
        if len(self.agent_core.short_memory) >= MAX_HISTORY_ROUNDS:
            dialog_text = "\n".join(self.agent_core.short_memory)
            
            # 1. Generate new summary and extract preferences
            new_summary, new_prefs = summarize_dialog(
                (self.agent_core.summary_memory + "\n" + dialog_text).strip()
            )
            
            # Update preferences
            if new_prefs:
                logger.info(f"[Memory] 捕捉到用户偏好更新: {new_prefs}")
                self.agent_core.user_preferences.update(new_prefs)
            
            # 2. Vectorize the OLD summary into Long-Term Memory (if it exists)
            if self.agent_core.summary_memory:
                logger.info("[Memory] 正在将旧摘要存入向量库...")
                self.agent_core.vector_store.add_episodic_memory(self.agent_core.summary_memory)
                self.agent_core.vector_store.save()

            # 3. Update current summary
            self.agent_core.summary_memory = new_summary
            self.agent_core.short_memory = []
            logger.info("[SynthesisChain] Memory compressed & updated")

        return {"final_answer": final_answer, "final_sources": sources}

    async def ainvoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        if inputs.get("canceled", False):
            return {"final_answer": "已取消", "final_sources": []}
            
        question = inputs["question"]
        kb_chunks = inputs.get("kb_chunks", [])
        step_results = inputs.get("step_results", [])
        sources = inputs.get("sources", [])
        stream_callback = inputs.get("stream_callback", None)

        kb_evidence = ""
        if kb_chunks:
            lines = []
            for c in kb_chunks:
                content = c.get("content", "") or ""
                if len(content) > SYNTHESIS_MAX_EVIDENCE_CHARS:
                    content = content[:SYNTHESIS_MAX_EVIDENCE_CHARS] + "…"
                lines.append(f"【{c.get('doc_name')}】\n{content}")
            kb_evidence = "\n\n".join(lines)
            
        # --- Context Safety: Truncate step_results if too long ---
        full_steps = self._compress_step_results_for_context(step_results)

        # Inject User Preferences
        user_prefs_str = ""
        if self.agent_core.user_preferences:
            prefs = []
            for k, v in self.agent_core.user_preferences.items():
                prefs.append(f"- {k}: {v}")
            user_prefs_str = "\n\n【用户偏好与习惯】\n" + "\n".join(prefs) + "\n请严格遵守上述用户偏好。"

        final_prompt = get_prompt_catalog().render(
            "synthesis_final_answer",
            question=question,
            step_results=full_steps,
            kb_evidence=kb_evidence + user_prefs_str,
        )

        final_answer = ""
        if stream_callback:
            cancel_event = getattr(self.agent_core, "_active_cancel_event", None)
            async for token in ask_ollama_stream_async(final_prompt, temperature=self.agent_core.temperature, cancel_event=cancel_event):
                final_answer += token
                stream_callback(token)
        else:
            final_answer = await ask_ollama_async(final_prompt, temperature=self.agent_core.temperature)
            final_answer = final_answer.strip()

        final_answer = await self.agent_core._fix_terminology_async(final_answer, question)
        
        if sources:
            cited = [s for s in sources if s and s in final_answer]
            if cited:
                sources = cited
        
        # Memory Update
        self.agent_core.short_memory.append(f"用户：{question}")
        self.agent_core.short_memory.append(f"助手：{final_answer}")
        
        sid = self.agent_core.get_active_session_id()
        try:
            # Async DB save
            import asyncio
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.agent_core.db_manager.add_conversation(
                    self.agent_core.user_id, 
                    question, 
                    final_answer, 
                    session_id=sid
                )
            )
        except Exception as e:
            logger.error(f"[System] ⚠️ 对话保存失败 (DB Error): {e}")
        
        if len(self.agent_core.short_memory) >= MAX_HISTORY_ROUNDS:
            dialog_text = "\n".join(self.agent_core.short_memory)
            
            # 1. Generate new summary and extract preferences
            # summarize_dialog is sync. For now run in executor.
            import asyncio
            loop = asyncio.get_running_loop()
            
            def do_summary_update():
                 new_summary, new_prefs = summarize_dialog(
                    (self.agent_core.summary_memory + "\n" + dialog_text).strip()
                 )
                 return new_summary, new_prefs
            
            new_summary, new_prefs = await loop.run_in_executor(None, do_summary_update)
            
            # Update preferences
            if new_prefs:
                logger.info(f"[Memory] 捕捉到用户偏好更新: {new_prefs}")
                self.agent_core.user_preferences.update(new_prefs)
            
            # 2. Vectorize the OLD summary into Long-Term Memory (if it exists)
            if self.agent_core.summary_memory:
                logger.info("[Memory] 正在将旧摘要存入向量库...")
                # Run vector store write in executor
                await loop.run_in_executor(
                    None, 
                    lambda: self.agent_core.vector_store.add_episodic_memory(self.agent_core.summary_memory)
                )
                await loop.run_in_executor(
                    None,
                    self.agent_core.vector_store.save
                )

            # 3. Update current summary
            self.agent_core.summary_memory = new_summary
            self.agent_core.short_memory = []
            logger.info("[SynthesisChain] Memory compressed & updated")

        return {"final_answer": final_answer, "final_sources": sources}
