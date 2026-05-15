from utils.warning_filters import suppress_known_third_party_warnings

suppress_known_third_party_warnings()

import chromadb
import copy
import gc
import hashlib
import jieba
import json
import os
import pickle
import requests
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from loguru import logger
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from config_runtime import (
    BASE_DIR,
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_BACKEND,
    EMBEDDING_OLLAMA_BATCH_SIZE,
    EMBEDDING_OLLAMA_TIMEOUT,
    EMBEDDING_OLLAMA_URL,
    VECTOR_BATCH_SIZE,
    VECTOR_COLLECTION_NAME,
    VECTOR_DB_PATH,
    VECTOR_HNSW_EF_CONSTRUCTION,
    VECTOR_HNSW_EF_SEARCH,
    VECTOR_HNSW_M,
    VECTOR_HNSW_SPACE,
    VECTOR_SEARCH_CACHE_ENABLED,
    VECTOR_SEARCH_CACHE_MAX_SIZE,
    VECTOR_SEARCH_CACHE_TTL_SECONDS,
    VECTOR_SEARCH_CANDIDATE_MULTIPLIER,
    VECTOR_SEARCH_MAX_CHUNKS_PER_DOC,
    VECTOR_SEARCH_PRERERANK_MAX_PER_DOC,
    VECTOR_SEARCH_PRERERANK_MIN_SECTION_COVERAGE,
    VECTOR_SEARCH_RRF_K,
    VECTOR_SEARCH_TOP_K,
)
from .rerank_types import Reranker

class OllamaEmbeddingClient:
    def __init__(self, model_name: str, endpoint: str, timeout: int = 60, batch_size: int = 16):
        self.model_name = model_name
        self.timeout = max(5, int(timeout))
        self.batch_size = max(1, int(batch_size))
        self.embed_url, self.legacy_url = self._normalize_urls(endpoint)
        self._prefer_embed_api = True

    def _normalize_urls(self, endpoint: str):
        endpoint = (endpoint or "").strip().rstrip("/")
        if not endpoint:
            endpoint = "http://localhost:11434/api/embed"
        if endpoint.endswith("/api/embed"):
            base = endpoint[:-10]
            return endpoint, base + "/api/embeddings"
        if endpoint.endswith("/api/embeddings"):
            base = endpoint[:-15]
            return base + "/api/embed", endpoint
        if endpoint.endswith("/api"):
            return endpoint + "/embed", endpoint + "/embeddings"
        return endpoint + "/api/embed", endpoint + "/api/embeddings"

    def encode(self, texts: List[str]):
        if not texts:
            return []
        outputs = []
        for i in range(0, len(texts), self.batch_size):
            batch = [str(t or "") for t in texts[i : i + self.batch_size]]
            outputs.extend(self._encode_batch(batch))
        return outputs

    def _encode_batch(self, batch: List[str]) -> List[List[float]]:
        if self._prefer_embed_api:
            try:
                resp = requests.post(
                    self.embed_url,
                    json={"model": self.model_name, "input": batch},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings") or []
                if len(embeddings) == len(batch):
                    return embeddings
            except Exception as e:
                logger.warning(f"[VectorStore] Ollama /api/embed unavailable, fallback to legacy endpoint: {e}")
                self._prefer_embed_api = False
        return [self._encode_single_legacy(text) for text in batch]

    def _encode_single_legacy(self, text: str) -> List[float]:
        resp = requests.post(
            self.legacy_url,
            json={"model": self.model_name, "prompt": text},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError("Ollama embedding response missing 'embedding' field")
        return embedding


class VectorStore:
    """
    Vector Store management using ChromaDB and SentenceTransformers.
    Supports Hybrid Search (Vector + BM25) and Parent-Child Indexing.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        index_path: str = "vector_db",
        reranker: Optional[Reranker] = None,
    ):
        """
        Initialize the VectorStore.
        """
        if not model_name:
            model_name = DEFAULT_EMBEDDING_MODEL

        logger.info(f"[VectorStore] Loading model: {model_name} (backend={EMBEDDING_BACKEND})")
        if EMBEDDING_BACKEND == "ollama":
            self.model = OllamaEmbeddingClient(
                model_name=model_name,
                endpoint=EMBEDDING_OLLAMA_URL,
                timeout=EMBEDDING_OLLAMA_TIMEOUT,
                batch_size=EMBEDDING_OLLAMA_BATCH_SIZE,
            )
        else:
            self.model = SentenceTransformer(model_name)
            logger.debug(f"[VectorStore] Embedding Device: {self.model.device}")

        self.persist_directory = index_path
        if index_path == "vector_db":
            self.persist_directory = VECTOR_DB_PATH
        elif not os.path.isabs(self.persist_directory):
            self.persist_directory = os.path.join(BASE_DIR, self.persist_directory)

        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.client.get_or_create_collection(name=VECTOR_COLLECTION_NAME, metadata=self._collection_metadata())
        logger.info(f"📦 Loaded ChromaDB Collection '{VECTOR_COLLECTION_NAME}', count: {self.collection.count()}")

        self.reranker = reranker
        if self.reranker:
            logger.info("[VectorStore] Reranker injected")
        else:
            logger.info("[VectorStore] No reranker injected; search will use base ranking only")

        # Initialize BM25
        self.bm25 = None
        self.bm25_ids = []
        self._build_bm25_index()
        self.cache_enabled = VECTOR_SEARCH_CACHE_ENABLED
        self.cache_ttl = max(1, VECTOR_SEARCH_CACHE_TTL_SECONDS)
        self.cache_max_size = max(8, VECTOR_SEARCH_CACHE_MAX_SIZE)
        self._search_cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        self.kb_version = f"{int(time.time())}-{self.collection.count()}"
        self.last_search_meta: Dict[str, Any] = {}

    def set_reranker(self, reranker: Optional[Reranker]) -> None:
        self.reranker = reranker
        self._invalidate_cache()

    def _encode_texts(self, texts: List[str]) -> List[List[float]]:
        vectors = self.model.encode(texts)
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()
        return [list(v) for v in vectors]

    def _collection_metadata(self) -> Dict[str, Any]:
        return {
            "hnsw:space": VECTOR_HNSW_SPACE,
            "hnsw:M": int(VECTOR_HNSW_M),
            "hnsw:construction_ef": int(VECTOR_HNSW_EF_CONSTRUCTION),
            "hnsw:search_ef": int(VECTOR_HNSW_EF_SEARCH),
        }

    def _new_kb_version(self):
        self.kb_version = f"{int(time.time() * 1000)}-{self.collection.count()}"
        self._invalidate_cache()

    def _normalize_filter(self, filter_obj: Optional[Dict[str, Any]]) -> str:
        if not filter_obj:
            return ""
        try:
            return json.dumps(filter_obj, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(filter_obj)

    def _cache_key(self, query: str, top_k: int, filter_obj: Optional[Dict[str, Any]], search_mode: str) -> str:
        raw = "||".join(
            [
                str(self.kb_version),
                (query or "").strip(),
                str(int(top_k)),
                (search_mode or "hybrid").lower(),
                self._normalize_filter(filter_obj),
            ]
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _invalidate_cache(self):
        with self._cache_lock:
            self._search_cache.clear()

    def _get_cache(self, cache_key: str):
        if not self.cache_enabled:
            return None
        now = time.time()
        with self._cache_lock:
            item = self._search_cache.get(cache_key)
            if not item:
                return None
            if item["expire_at"] < now:
                self._search_cache.pop(cache_key, None)
                return None
            self._search_cache.move_to_end(cache_key)
            return copy.deepcopy(item["value"])

    def _set_cache(self, cache_key: str, value: List[Dict[str, Any]]):
        if not self.cache_enabled:
            return
        now = time.time()
        with self._cache_lock:
            self._search_cache[cache_key] = {"expire_at": now + self.cache_ttl, "value": copy.deepcopy(value)}
            self._search_cache.move_to_end(cache_key)
            while len(self._search_cache) > self.cache_max_size:
                self._search_cache.popitem(last=False)

    def get_runtime_stats(self) -> Dict[str, Any]:
        with self._cache_lock:
            cache_size = len(self._search_cache)
            hits = self._cache_hits
            misses = self._cache_misses
        total = hits + misses
        hit_rate = (hits / total) if total > 0 else 0.0
        return {
            "kb_version": self.kb_version,
            "cache_enabled": self.cache_enabled,
            "cache_size": cache_size,
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_rate": round(hit_rate, 4),
        }

    def _tokenize(self, text: str) -> List[str]:
        return list(jieba.cut_for_search(text))

    def _build_bm25_index(self, force_rebuild: bool = False):
        """Build BM25 index from existing ChromaDB documents."""
        cache_path = os.path.join(self.persist_directory, "bm25_index.pkl")

        try:
            count = self.collection.count()
            if count == 0:
                if os.path.exists(cache_path):
                    try:
                        os.remove(cache_path)
                    except Exception as e:
                        logger.warning(f"[VectorStore] Failed to remove stale BM25 cache: {e}")
                return

            if not force_rebuild and os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as f:
                        data = pickle.load(f)

                    if data.get("count") == count:
                        self.bm25 = data["bm25"]
                        self.bm25_ids = data["ids"]
                        logger.info(f"[VectorStore] Loaded BM25 index from cache ({count} docs)")
                        return
                except Exception as e:
                    logger.warning(f"[VectorStore] Failed to load BM25 cache: {e}")

            logger.info("[VectorStore] Rebuilding BM25 index...")
            result = self.collection.get()
            documents = result["documents"]
            self.bm25_ids = result["ids"]

            tokenized_corpus = [self._tokenize(doc) for doc in documents]
            self.bm25 = BM25Okapi(tokenized_corpus)
            logger.info(f"[VectorStore] BM25 Index built with {len(documents)} documents")

            try:
                with open(cache_path, "wb") as f:
                    pickle.dump({"bm25": self.bm25, "ids": self.bm25_ids, "count": len(documents)}, f)
            except Exception as e:
                logger.warning(f"[VectorStore] Failed to save BM25 cache: {e}")

        except Exception as e:
            logger.warning(f"[VectorStore] Failed to build BM25 index: {e}")

    def load(self) -> bool:
        return True

    def build_full(self, chunks: List[Dict[str, Any]]):
        try:
            self.client.delete_collection(VECTOR_COLLECTION_NAME)
        except Exception as e:
            logger.warning(f"[VectorStore] Delete old collection failed, continue recreate: {e}")
        self.collection = self.client.get_or_create_collection(name=VECTOR_COLLECTION_NAME, metadata=self._collection_metadata())

        if not chunks:
            self._new_kb_version()
            return

        self.add_chunks(chunks, refresh_index=False)
        self.refresh_bm25(force_rebuild=True)
        self._new_kb_version()
        logger.info(f"✅ Full index build complete: {self.collection.count()} items")

    def refresh_bm25(self, force_rebuild: bool = True):
        self._build_bm25_index(force_rebuild=force_rebuild)

    def deactivate_by_doc(self, doc_name: str, refresh_index: bool = True):
        self.collection.delete(where={"doc_name": doc_name})
        logger.info(f"🗑️ Removed document index: {doc_name}")
        if refresh_index:
            self.refresh_bm25(force_rebuild=True)
            self._new_kb_version()

    def deactivate_by_docs(self, doc_names: List[str]):
        targets = [name for name in (doc_names or []) if name]
        if not targets:
            return
        for doc_name in targets:
            self.deactivate_by_doc(doc_name, refresh_index=False)
        self.refresh_bm25(force_rebuild=True)
        self._new_kb_version()

    def add_chunks(self, new_chunks: List[Dict[str, Any]], refresh_index: bool = True):
        if not new_chunks:
            return

        ids = [str(c["id"]) for c in new_chunks]
        documents = [c["content"] for c in new_chunks]
        metadatas = []

        for c in new_chunks:
            meta = {
                "doc_name": c.get("doc_name", "unknown"),
                "page_num": c.get("page_num", 0),
                "type": c.get("type", "knowledge"),
                "section_idx": c.get("section_idx", -1),
                "parent_id": c.get("parent_id", ""),
                "parent_content": c.get("parent_content", ""),
                "active": True,
            }
            year = c.get("year")
            if isinstance(year, int) and 1900 <= year <= 2100:
                meta["year"] = year
            metadatas.append(meta)

        embeddings = self._encode_texts(documents)

        batch_size = VECTOR_BATCH_SIZE
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            self.collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
                documents=documents[i:end],
            )

        logger.info(f"➕ Added vectors: {len(new_chunks)}")
        if refresh_index:
            self.refresh_bm25(force_rebuild=True)
            self._new_kb_version()

    def rebuild_hnsw_index(self, m: int, ef_construction: int, ef_search: int):
        m = int(max(8, m))
        ef_construction = int(max(32, ef_construction))
        ef_search = int(max(16, ef_search))
        existing = self.collection.get()
        ids = existing.get("ids", [])
        documents = existing.get("documents", [])
        metadatas = existing.get("metadatas", [])
        embeddings = existing.get("embeddings")
        if embeddings is None and documents:
            embeddings = self._encode_texts(documents)
        try:
            self.client.delete_collection(VECTOR_COLLECTION_NAME)
        except Exception:
            pass
        metadata = {
            "hnsw:space": VECTOR_HNSW_SPACE,
            "hnsw:M": m,
            "hnsw:construction_ef": ef_construction,
            "hnsw:search_ef": ef_search,
        }
        self.collection = self.client.get_or_create_collection(name=VECTOR_COLLECTION_NAME, metadata=metadata)
        batch = max(1, VECTOR_BATCH_SIZE)
        for i in range(0, len(ids), batch):
            end = min(i + batch, len(ids))
            self.collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
                documents=documents[i:end],
            )
        self._build_bm25_index(force_rebuild=True)
        self._new_kb_version()

    def add_episodic_memory(self, memory_text: str):
        import uuid

        chunk = {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "content": memory_text,
            "doc_name": "长期记忆",
            "page_num": 0,
            "type": "episodic",
            "active": True,
        }
        self.add_chunks([chunk])

    def _search_vector(self, query: str, top_k: int, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        query_embedding = self._encode_texts([query])
        initial_k = top_k * VECTOR_SEARCH_CANDIDATE_MULTIPLIER
        count = self.collection.count()
        if count == 0:
            return []
        initial_k = min(initial_k, count)

        results = self.collection.query(query_embeddings=query_embedding, n_results=initial_k, where=filter)

        candidates = []
        if not results["ids"]:
            return []

        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            doc_text = results["documents"][0][i]
            doc_id = results["ids"][0][i]

            chunk = {
                "id": doc_id,
                "content": doc_text,
                "metadata": meta,
                "doc_name": meta.get("doc_name", ""),
                "parent_content": meta.get("parent_content", ""),
                "distance": dist,
                "score": 1.0 / (1.0 + dist),
            }
            candidates.append(chunk)
        return candidates

    def _search_bm25(self, query: str, top_k: int, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self.bm25:
            return []

        tokenized_query = self._tokenize(query)
        doc_scores = self.bm25.get_scores(tokenized_query)
        top_n_indices = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[
            : top_k * VECTOR_SEARCH_CANDIDATE_MULTIPLIER
        ]

        candidates = []
        for idx in top_n_indices:
            if doc_scores[idx] == 0:
                continue
            doc_id = self.bm25_ids[idx]
            candidates.append({"id": doc_id, "score": doc_scores[idx], "is_bm25": True})

        if not candidates:
            return []

        ids_to_fetch = [c["id"] for c in candidates]
        fetched = self.collection.get(ids=ids_to_fetch, where=filter)
        fetched_map = {id: (doc, meta) for id, doc, meta in zip(fetched["ids"], fetched["documents"], fetched["metadatas"])}

        final_candidates = []
        for c in candidates:
            if c["id"] in fetched_map:
                doc, meta = fetched_map[c["id"]]
                c["content"] = doc
                c["metadata"] = meta
                c["doc_name"] = meta.get("doc_name", "")
                c["parent_content"] = meta.get("parent_content", "")
                final_candidates.append(c)

        return final_candidates

    def _rrf_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], k: int = VECTOR_SEARCH_RRF_K) -> List[Dict]:
        """Reciprocal Rank Fusion"""
        scores = {}
        id_to_item = {}

        for rank, item in enumerate(vector_results):
            doc_id = item["id"]
            id_to_item[doc_id] = item
            scores[doc_id] = scores.get(doc_id, 0) + (1 / (k + rank + 1))

        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            if doc_id not in id_to_item:
                id_to_item[doc_id] = item
            scores[doc_id] = scores.get(doc_id, 0) + (1 / (k + rank + 1))

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        results = []
        for doc_id in sorted_ids:
            item = id_to_item[doc_id]
            item["rrf_score"] = scores[doc_id]
            results.append(item)

        return results

    def _candidate_doc_name(self, item: Dict[str, Any]) -> str:
        doc_name = item.get("doc_name")
        if doc_name:
            return str(doc_name)
        metadata = item.get("metadata") or {}
        return str(metadata.get("doc_name", ""))

    def _candidate_section_parent(self, item: Dict[str, Any]) -> Any:
        metadata = item.get("metadata") or {}
        section_idx = metadata.get("section_idx", item.get("section_idx", -1))
        try:
            section_idx = int(section_idx)
        except Exception:
            pass
        parent_id = metadata.get("parent_id", item.get("parent_id", ""))
        return section_idx, str(parent_id or "")

    def _apply_pre_rerank_constraints(self, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        max_per_doc = max(1, int(VECTOR_SEARCH_PRERERANK_MAX_PER_DOC))
        min_coverage = float(VECTOR_SEARCH_PRERERANK_MIN_SECTION_COVERAGE)
        min_coverage = max(0.0, min(1.0, min_coverage))
        target = min(len(candidates), max(int(top_k), int(top_k * VECTOR_SEARCH_CANDIDATE_MULTIPLIER)))
        selected: List[Dict[str, Any]] = []
        selected_ids = set()
        doc_stats: Dict[str, Dict[str, Any]] = {}

        def can_take(item: Dict[str, Any], prefer_new_section: bool, enforce_coverage: bool) -> bool:
            doc_name = self._candidate_doc_name(item)
            section_idx, parent_id = self._candidate_section_parent(item)
            stats = doc_stats.get(doc_name)
            if stats is None:
                stats = {"count": 0, "sections": set(), "parents": set()}
            if stats["count"] >= max_per_doc:
                return False
            if parent_id and parent_id in stats["parents"]:
                return False
            is_new_section = section_idx not in stats["sections"]
            if prefer_new_section and stats["count"] > 0 and not is_new_section:
                return False
            if enforce_coverage and not is_new_section and stats["count"] > 0:
                projected_count = stats["count"] + 1
                projected_unique = len(stats["sections"])
                if projected_count > 0 and (projected_unique / projected_count) < min_coverage:
                    return False
            return True

        def take(item: Dict[str, Any]):
            doc_name = self._candidate_doc_name(item)
            section_idx, parent_id = self._candidate_section_parent(item)
            stats = doc_stats.get(doc_name)
            if stats is None:
                stats = {"count": 0, "sections": set(), "parents": set()}
            stats["count"] += 1
            stats["sections"].add(section_idx)
            if parent_id:
                stats["parents"].add(parent_id)
            doc_stats[doc_name] = stats
            selected.append(item)
            selected_ids.add(item.get("id"))

        for prefer_new_section, enforce_coverage in ((True, True), (False, True), (False, False)):
            for item in candidates:
                if len(selected) >= target:
                    break
                item_id = item.get("id")
                if item_id in selected_ids:
                    continue
                if can_take(item, prefer_new_section, enforce_coverage):
                    take(item)
            if len(selected) >= target:
                break
        return selected

    def search(
        self,
        query: str,
        top_k: int = VECTOR_SEARCH_TOP_K,
        filter: Optional[Dict[str, Any]] = None,
        search_mode: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        """
        Hybrid Search (Vector + BM25) with Parent-Child Indexing support.
        Args:
            query: Search query
            top_k: Number of results
            filter: Metadata filter dict (e.g. {"doc_name": "report.pdf"} or {"type": "knowledge"})
        """
        started = time.perf_counter()
        mode = (search_mode or "hybrid").lower()
        cache_key = self._cache_key(query, top_k, filter, mode)
        cached = self._get_cache(cache_key)
        if cached is not None:
            with self._cache_lock:
                self._cache_hits += 1
            duration_ms = (time.perf_counter() - started) * 1000
            self.last_search_meta = {
                "cache_hit": True,
                "duration_ms": round(duration_ms, 3),
                "mode": mode,
                "top_k": int(top_k),
                "result_count": len(cached),
            }
            return cached
        with self._cache_lock:
            self._cache_misses += 1
        vector_results = self._search_vector(query, top_k, filter=filter)
        bm25_results = self._search_bm25(query, top_k, filter=filter)

        if mode == "vector":
            fused_results = vector_results
        elif mode == "bm25":
            fused_results = bm25_results
        else:
            fused_results = self._rrf_fusion(vector_results, bm25_results)

        if self.reranker:
            candidates_to_rerank = fused_results[: top_k * VECTOR_SEARCH_CANDIDATE_MULTIPLIER]
            candidates_to_rerank = self._apply_pre_rerank_constraints(candidates_to_rerank, top_k)
            fused_results = self.reranker.rerank(query, candidates_to_rerank)

        final_results = []
        seen_docs = {}

        for res in fused_results:
            display_content = res.get("parent_content")
            if not display_content:
                display_content = res["content"]

            res["content"] = display_content

            doc = res.get("doc_name", "")
            if seen_docs.get(doc, 0) >= VECTOR_SEARCH_MAX_CHUNKS_PER_DOC:
                continue
            seen_docs[doc] = seen_docs.get(doc, 0) + 1

            final_results.append(res)
            if len(final_results) >= top_k:
                break

        duration_ms = (time.perf_counter() - started) * 1000
        self._set_cache(cache_key, final_results)
        self.last_search_meta = {
            "cache_hit": False,
            "duration_ms": round(duration_ms, 3),
            "mode": mode,
            "top_k": int(top_k),
            "result_count": len(final_results),
            "vector_candidates": len(vector_results),
            "bm25_candidates": len(bm25_results),
        }
        return copy.deepcopy(final_results)

    def inactive_ratio(self) -> float:
        return 0.0

    def save(self):
        pass

    def close(self):
        try:
            self._invalidate_cache()
        except Exception:
            pass
        try:
            self.collection = None
        except Exception:
            pass
        try:
            self.client = None
        except Exception:
            pass
        try:
            self.bm25 = None
            self.bm25_ids = []
        except Exception:
            pass
        try:
            self.model = None
            self.reranker = None
        except Exception:
            pass
        gc.collect()
