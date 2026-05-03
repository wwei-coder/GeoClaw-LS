"""Retrieval quality helpers for RAG pipeline."""

from __future__ import annotations

import math
from typing import Any, Dict, List


def chunk_similarity_score(chunk: Dict[str, Any]) -> float:
    if "model_score" in chunk:
        score = 1.0 / (1.0 + math.exp(-float(chunk["model_score"])))
        return max(0.0, min(1.0, score))
    if "score" in chunk:
        score = float(chunk["score"])
        return max(0.0, min(1.0, score))
    if "distance" in chunk:
        return 1.0 / (1.0 + max(0.0, float(chunk["distance"])))
    if "rrf_score" in chunk:
        score = float(chunk["rrf_score"]) * 120.0
        return max(0.0, min(1.0, score))
    return 0.0


def evaluate_retrieval_quality(chunks: List[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
    hit_count = len(chunks)
    source_count = len({c.get("doc_name", "") for c in chunks if c.get("doc_name")})
    hit_score = min(1.0, hit_count / max(1, top_k))
    similarity_score = 0.0
    if chunks:
        similarity_score = sum(chunk_similarity_score(c) for c in chunks) / len(chunks)
    source_diversity = 0.0
    if hit_count > 0:
        source_diversity = source_count / hit_count
    score = (0.45 * hit_score) + (0.40 * similarity_score) + (0.15 * source_diversity)
    return {
        "score": max(0.0, min(1.0, score)),
        "hit_count": hit_count,
        "avg_similarity": round(similarity_score, 4),
        "source_diversity": round(source_diversity, 4),
        "source_count": source_count,
    }


def is_low_retrieval_quality(
    quality: Dict[str, Any],
    quality_threshold: float,
    min_hits: int,
    min_similarity: float,
    min_source_diversity: float,
) -> bool:
    return (
        quality["score"] < quality_threshold
        or quality["hit_count"] < min_hits
        or quality["avg_similarity"] < min_similarity
        or quality["source_diversity"] < min_source_diversity
    )


def fast_path_target(quality_threshold: float, quality_margin: float) -> float:
    return max(quality_threshold, min(1.0, quality_threshold + quality_margin))


def is_fast_path_good_enough(
    quality: Dict[str, Any],
    target_score: float,
    min_hits: int,
    min_similarity: float,
    min_source_diversity: float,
) -> bool:
    return (
        quality.get("score", 0.0) >= target_score
        and quality.get("hit_count", 0) >= min_hits
        and quality.get("avg_similarity", 0.0) >= min_similarity
        and quality.get("source_diversity", 0.0) >= min_source_diversity
    )
