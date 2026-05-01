"""RAG package facade for phase-1 architecture decoupling."""

from .loader import load_documents_from_dir, load_file, load_pdf, load_docx, load_txt
from .chunker import build_knowledge_chunks, split_text
from .vector_store import VectorStore, OllamaEmbeddingClient
from .rerank import BaseReranker, KeywordReranker, ModelReranker, get_reranker
from .diagnostics import ensure_metrics_state, record_retrieval_metrics
from .quality import (
    chunk_similarity_score,
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

__all__ = [
    "load_documents_from_dir",
    "load_file",
    "load_pdf",
    "load_docx",
    "load_txt",
    "build_knowledge_chunks",
    "split_text",
    "VectorStore",
    "OllamaEmbeddingClient",
    "BaseReranker",
    "KeywordReranker",
    "ModelReranker",
    "get_reranker",
    "parse_metadata_filter",
    "append_unique_chunks",
    "apply_question_filters",
    "rerank_merged_chunks",
    "rewrite_query",
    "rewrite_query_async",
    "build_dual_queries",
    "build_dual_queries_async",
    "chunk_similarity_score",
    "evaluate_retrieval_quality",
    "is_low_retrieval_quality",
    "fast_path_target",
    "is_fast_path_good_enough",
    "ensure_metrics_state",
    "record_retrieval_metrics",
]
