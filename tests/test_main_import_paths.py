from __future__ import annotations

from capabilities.memory.summary import summarize_dialog
from capabilities.rag.indexing.chunker import build_knowledge_chunks
from capabilities.rag.indexing.fingerprint import generate_fingerprint
from capabilities.rag.indexing.loader import load_documents_from_dir
from capabilities.rag.rerank.rerank import get_reranker
from capabilities.rag.retrieval.quality import evaluate_retrieval_quality
from capabilities.rag.retrieval.retriever import parse_metadata_filter
from storage.sqlite.database_manager import DatabaseManager
from storage.vector.vector_store import VectorStore


def test_main_rag_indexing_imports():
    assert callable(load_documents_from_dir)
    assert callable(build_knowledge_chunks)


def test_main_rag_retrieval_imports():
    assert callable(parse_metadata_filter)
    assert callable(evaluate_retrieval_quality)
    assert VectorStore is not None


def test_main_memory_storage_imports():
    assert DatabaseManager is not None
    assert VectorStore is not None
    assert callable(summarize_dialog)
    assert callable(generate_fingerprint)
    assert callable(get_reranker)


def test_parse_metadata_filter_tolerates_non_json():
    assert parse_metadata_filter("") is None
    assert parse_metadata_filter("not a json response") is None
    assert parse_metadata_filter("```json\n{}\n```") is None
