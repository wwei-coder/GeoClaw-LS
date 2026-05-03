"""Diagnostics helpers for retrieval metrics logging."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any, Dict

from utils.logger import logger


def ensure_metrics_state(holder: Any, window_size: int) -> None:
    if hasattr(holder, "_metrics_lock") and hasattr(holder, "_metrics_window"):
        return
    holder._metrics_lock = threading.Lock()
    holder._metrics_window = deque(maxlen=max(20, int(window_size)))


def record_retrieval_metrics(
    holder: Any,
    *,
    enabled: bool,
    window_size: int,
    log_path: str,
    vector_store: Any,
    duration_ms: float,
    question: str,
    search_queries: list[str],
    metadata_filter: Dict[str, Any] | None,
    expanded: bool,
    quality: Dict[str, Any],
    result_count: int,
) -> None:
    if not enabled:
        return
    ensure_metrics_state(holder, window_size)
    runtime_stats = {}
    try:
        runtime_stats = vector_store.get_runtime_stats()
    except Exception:
        runtime_stats = {}
    event = {
        "ts": time.time(),
        "duration_ms": round(float(duration_ms), 3),
        "question_len": len(question or ""),
        "query_count": len(search_queries or []),
        "filter_used": bool(metadata_filter),
        "expanded": bool(expanded),
        "result_count": int(result_count),
        "quality_score": float(quality.get("score", 0.0)),
        "avg_similarity": float(quality.get("avg_similarity", 0.0)),
        "source_diversity": float(quality.get("source_diversity", 0.0)),
        "cache_hit_rate": runtime_stats.get("cache_hit_rate", 0.0),
        "cache_size": runtime_stats.get("cache_size", 0),
        "kb_version": runtime_stats.get("kb_version", ""),
    }
    with holder._metrics_lock:
        holder._metrics_window.append(event)
        window = list(holder._metrics_window)
    if window:
        avg_duration = sum(x["duration_ms"] for x in window) / len(window)
        avg_quality = sum(x["quality_score"] for x in window) / len(window)
        event["window_size"] = len(window)
        event["window_avg_duration_ms"] = round(avg_duration, 3)
        event["window_avg_quality"] = round(avg_quality, 4)
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning(f"[Retriever] 指标写入失败: {exc}")
