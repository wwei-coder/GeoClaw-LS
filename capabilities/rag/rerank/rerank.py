from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import jieba
from loguru import logger

from core.config import KEYWORD_RERANK_STOP_WORDS
from utils.warning_filters import suppress_known_third_party_warnings

suppress_known_third_party_warnings()


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass


class KeywordReranker(BaseReranker):
    """
    Reranks candidates based on keyword matching (Jieba based).
    """

    def __init__(self):
        # Initialize jieba lazily when used.
        pass

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        query_keywords = set(jieba.cut_for_search(query))
        query_keywords = {k for k in query_keywords if k not in KEYWORD_RERANK_STOP_WORDS and len(k.strip()) > 0}

        if not query_keywords:
            return candidates

        for cand in candidates:
            content = cand.get("content", "")
            content_lower = content.lower()
            count = 0
            for kw in query_keywords:
                count += content_lower.count(kw.lower())
            cand["keyword_score"] = count

        candidates.sort(key=lambda x: (-x.get("keyword_score", 0), x.get("distance", 100)))
        return candidates


class ModelReranker(BaseReranker):
    """
    Reranks candidates using a Cross-Encoder model.
    """

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"[Reranker] Loading CrossEncoder model: {model_name} on {device}")
            self.model = CrossEncoder(model_name, device=device)
        except Exception as e:
            logger.error(f"Failed to load CrossEncoder model {model_name}: {e}")
            self.model = None

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.model or not candidates:
            return candidates

        pairs = [[query, c["content"]] for c in candidates]
        scores = self.model.predict(pairs)

        for i, score in enumerate(scores):
            candidates[i]["model_score"] = score

        candidates.sort(key=lambda x: x.get("model_score", -100), reverse=True)
        return candidates


def get_reranker(strategy: str, model_name: Optional[str] = None) -> Optional[BaseReranker]:
    if strategy == "keyword":
        return KeywordReranker()
    if strategy == "model":
        if not model_name:
            logger.warning("Model strategy selected but no model name provided. Falling back to keyword.")
            return KeywordReranker()
        return ModelReranker(model_name)
    return None
