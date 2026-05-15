from __future__ import annotations
from typing import Any, Dict, List
from config_runtime import RAG_MAX_CHUNK_LENGTH, TOOL_RAG_TOP_K
from tools.base import BaseTool, ToolInput, ToolResult

def _normalize_chunk(raw: Any) -> Dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    doc_name = str(item.get("doc_name") or metadata.get("doc_name") or "")
    content = str(item.get("content") or "")
    chunk = {
        "id": str(item.get("id") or ""),
        "content": content,
        "doc_name": doc_name,
        "score": item.get("score", item.get("rrf_score", 0.0)),
        "distance": item.get("distance"),
        "metadata": metadata,
    }
    if item.get("parent_id") or metadata.get("parent_id"):
        chunk["parent_id"] = item.get("parent_id") or metadata.get("parent_id")
    if item.get("section_idx") is not None or metadata.get("section_idx") is not None:
        chunk["section_idx"] = item.get("section_idx", metadata.get("section_idx"))
    return chunk

def _bounded_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score

def _build_quality(chunks: List[Dict[str, Any]], search_meta: Dict[str, Any]) -> Dict[str, Any]:
    if not chunks:
        return {
            "score": 0.0,
            "hit_count": 0,
            "avg_similarity": 0.0,
            "source_diversity": 0.0,
            "expanded": False,
            "strategy": "direct_tool",
            **dict(search_meta or {}),
        }
    similarities = [_bounded_score(c.get("score")) for c in chunks if c.get("score") is not None]
    avg_similarity = sum(similarities) / len(similarities) if similarities else 0.7
    docs = {c.get("doc_name") for c in chunks if c.get("doc_name")}
    source_diversity = len(docs) / max(1, len(chunks))
    quality_score = max(0.7, min(1.0, 0.65 * avg_similarity + 0.35 * min(1.0, source_diversity)))
    return {
        "score": round(quality_score, 3),
        "hit_count": len(chunks),
        "avg_similarity": round(avg_similarity, 3),
        "source_diversity": round(source_diversity, 3),
        "expanded": False,
        "strategy": "direct_tool",
        **dict(search_meta or {}),
    }

class RagTool(BaseTool):
    name = "RAG"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            chunks = agent.vector_store.search(tool_input.task, top_k=TOOL_RAG_TOP_K)
            kb_chunks = [_normalize_chunk(c) for c in chunks or []]
            docs = sorted({c.get("doc_name", "") for c in kb_chunks if c.get("doc_name")})
            search_meta = dict(getattr(agent.vector_store, "last_search_meta", {}) or {})
            quality = _build_quality(kb_chunks, search_meta)
            metadata = {
                "tool": self.name,
                "source_count": len(docs),
                "retrieved_docs": docs,
                "retrieved_chunk_count": len(kb_chunks),
                "retrieval_quality": quality,
                "kb_chunks": kb_chunks,
            }
            if not chunks:
                content = "[RAG] 未检索到相关资料"
                return ToolResult(success=True, content=content, metadata=metadata)
            lines = []
            for item in kb_chunks:
                text = item.get("content", "")
                if len(text) > RAG_MAX_CHUNK_LENGTH:
                    text = text[:RAG_MAX_CHUNK_LENGTH] + "…"
                cid = item.get("id", "")
                doc = item.get("doc_name", "")
                head = f"【{doc}｜{cid}】" if cid else f"【{doc}】"
                lines.append(head + "\n" + text)
            content = "\n\n".join(lines)
            return ToolResult(success=True, content=content, metadata=metadata)
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
