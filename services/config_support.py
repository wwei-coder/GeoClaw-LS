from __future__ import annotations
from typing import Any, Dict, List, Tuple

COMMON_PREFIXES = (
    "agent.max_context_len",
    "agent.max_history_rounds",
    "models.ollama.url",
    "models.ollama.model",
    "models.ollama.temperature",
    "models.ollama.timeout",
    "models.ollama.stream_timeout",
    "rag.search_top_k",
    "rag.quality_threshold",
    "rag.rerank_strategy",
    "rag.expansion_top_k",
    "rag.expansion_min_improvement",
    "tool.rag_top_k",
    "tool.discovery_top_k",
    "vector_search.candidate_multiplier",
    "vector_search.rrf_k",
    "vector_search.max_chunks_per_doc",
)

HIDDEN_PREFIXES = (
    "llm.temperatures.",
    "vector_search.hnsw.",
    "graph.answer_confidence.",
    "chunking.",
    "keyword_rerank.",
    "retrieval.metrics.",
    "terminology.",
    "system.hf_endpoint",
)

PARAM_HINTS = {
    "models.ollama.model": ("作用：选择回复模型", "建议：优先 7B/14B 常用模型"),
    "models.ollama.url": ("作用：Ollama 服务地址", "建议：本机默认 http://localhost:11434/api/generate"),
    "models.ollama.temperature": ("作用：控制回答发散度", "建议：0.2~0.8"),
    "rag.search_top_k": ("作用：首轮召回片段数量", "建议：3~8"),
    "rag.quality_threshold": ("作用：检索质量阈值", "建议：0.45~0.70"),
}

def iter_leaf_items(node: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    if isinstance(node, dict):
        out: List[Tuple[str, Any]] = []
        for key, value in node.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(iter_leaf_items(value, next_prefix))
        return out
    return [(prefix, node)]

def is_tunable(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in HIDDEN_PREFIXES)

def infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"

def flatten_config(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for top_key, top_value in data.items():
        items = iter_leaf_items(top_value, top_key) if isinstance(top_value, dict) else [(top_key, top_value)]
        for full_path, value in items:
            if not is_tunable(full_path):
                continue
            hint = PARAM_HINTS.get(full_path)
            rows.append(
                {
                    "group": str(top_key),
                    "path": full_path,
                    "value": value,
                    "type": infer_type(value),
                    "is_common": any(full_path.startswith(prefix) for prefix in COMMON_PREFIXES),
                    "hint": {"title": hint[0], "recommend": hint[1]} if hint else None,
                }
            )
    return rows
