from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from capabilities.rag.indexing.chunker import build_knowledge_chunks
from capabilities.rag.indexing.fingerprint import diff_fingerprint, generate_fingerprint, load_fingerprint, save_fingerprint
from capabilities.rag.indexing.loader import load_documents_from_dir

from .schemas import KnowledgeBaseStatus, KnowledgeSyncSummary, RetrievalRequest, RetrievalResult


class RagService:
    """RAG capability boundary (thin wrapper around existing implementations)."""

    def __init__(
        self,
        *,
        vector_store: Any,
        data_dir: str,
        fingerprint_path: str,
        collection_name: str,
        embedding_model: str,
        embedding_backend: str,
        rerank_strategy: str,
        rerank_model: str,
    ):
        self.vector_store = vector_store
        self.data_dir = data_dir
        self.fingerprint_path = fingerprint_path
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.embedding_backend = embedding_backend
        self.rerank_strategy = rerank_strategy
        self.rerank_model = rerank_model

    def load_fingerprint(self) -> Dict[str, Any]:
        return load_fingerprint(self.fingerprint_path) or {}

    def generate_fingerprint(self) -> Dict[str, Any]:
        return generate_fingerprint(self.data_dir)

    def sync_knowledge_base(self, current_fp: Dict[str, Any], saved_fp: Dict[str, Any], *, force_rebuild: bool = False) -> Dict[str, Any]:
        if force_rebuild:
            return self.full_rebuild(current_fp, reason="force_rebuild")
        return self.incremental_update(current_fp, saved_fp)

    def full_rebuild(self, current_fp: Dict[str, Any], *, reason: str = "force_rebuild") -> Dict[str, Any]:
        logger.info("📚 执行全量重建向量库…")
        documents = load_documents_from_dir(self.data_dir)
        chunks = build_knowledge_chunks(documents)
        self.vector_store.build_full(chunks)
        save_fingerprint(current_fp, self.fingerprint_path)
        logger.info(f"✅ 全量重建完成，文档数={len(documents)}，切块数={len(chunks)}")
        return KnowledgeSyncSummary(
            mode="full",
            reason=reason,
            changes={"added": len(current_fp.keys()), "updated": 0, "removed": 0},
            documents=len(documents),
            chunks=len(chunks),
        ).to_dict()

    def incremental_update(self, current_fp: Dict[str, Any], saved_fp: Dict[str, Any]) -> Dict[str, Any]:
        changes = diff_fingerprint(current_fp, saved_fp)
        if not changes["changed"]:
            logger.info("📚 文档无变化，跳过增量更新。")
            return KnowledgeSyncSummary(
                mode="no_change",
                changes={"added": 0, "updated": 0, "removed": 0},
                documents=0,
                chunks=0,
            ).to_dict()

        changed_for_reload = sorted(changes["added"] + changes["updated"])
        docs_to_remove = sorted(changes["removed"] + changes["updated"])
        logger.info(
            f"📚 检测到文档变更：新增={len(changes['added'])}，修改={len(changes['updated'])}，删除={len(changes['removed'])}"
        )
        if docs_to_remove:
            self.vector_store.deactivate_by_docs(docs_to_remove)
        touched_documents = 0
        touched_chunks = 0
        if changed_for_reload:
            changed_docs = load_documents_from_dir(self.data_dir, file_names=changed_for_reload)
            changed_chunks = build_knowledge_chunks(changed_docs)
            self.vector_store.add_chunks(changed_chunks)
            logger.info(f"📚 增量写入完成：文档数={len(changed_docs)}，切块数={len(changed_chunks)}")
            touched_documents = len(changed_docs)
            touched_chunks = len(changed_chunks)
        save_fingerprint(current_fp, self.fingerprint_path)
        return KnowledgeSyncSummary(
            mode="incremental",
            changes={
                "added": len(changes["added"]),
                "updated": len(changes["updated"]),
                "removed": len(changes["removed"]),
            },
            documents=touched_documents,
            chunks=touched_chunks,
        ).to_dict()

    def get_status(self, *, last_sync: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        collection_count = 0
        collection_metadata: Dict[str, Any] = {}
        runtime_stats: Dict[str, Any] = {}
        try:
            collection = getattr(self.vector_store, "collection", None)
            if collection is not None:
                collection_count = int(collection.count())
                collection_metadata = dict(getattr(collection, "metadata", None) or {})
        except Exception as e:
            logger.warning(f"[RagService] 获取知识库 collection 状态失败: {e}")
        try:
            runtime_stats = self.vector_store.get_runtime_stats()
        except Exception as e:
            logger.warning(f"[RagService] 获取向量库运行状态失败: {e}")
        current_fp = self.generate_fingerprint()
        saved_fp = self.load_fingerprint()
        status = KnowledgeBaseStatus(
            data_dir=self.data_dir,
            collection_name=self.collection_name,
            collection_count=collection_count,
            collection_metadata=collection_metadata,
            embedding_model=self.embedding_model,
            embedding_backend=self.embedding_backend,
            rerank_strategy=self.rerank_strategy,
            rerank_model=self.rerank_model,
            last_sync=dict(last_sync or {}),
            runtime=runtime_stats,
            fingerprint={
                "current_count": len(current_fp),
                "saved_count": len(saved_fp),
                "changed": diff_fingerprint(current_fp, saved_fp).get("changed", []),
            },
        )
        return status.to_dict()

    def retrieve(
        self,
        *,
        query: str,
        top_k: int,
        filter: Optional[Dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> Dict[str, Any]:
        req = RetrievalRequest(query=query, top_k=top_k, filter=filter, search_mode=search_mode)
        chunks: List[Dict[str, Any]] = self.vector_store.search(
            req.query,
            top_k=req.top_k,
            filter=req.filter,
            search_mode=req.search_mode,
        )
        sources = sorted({c.get("doc_name", "") for c in chunks if c.get("doc_name")})
        return RetrievalResult(chunks=chunks, sources=sources).to_dict()

    def search(
        self,
        query: str,
        top_k: int,
        filter: Optional[Dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        # 保持与 VectorStore.search 一致的旧接口返回结构
        return self.vector_store.search(query, top_k=top_k, filter=filter, search_mode=search_mode)
