# Compatibility Layers 说明

本文档用于“兼容层删除前的清理 PR 说明”。当前状态：`rag/`、`knowledge/`、`memory/` 已进入**可删除候选**，但删除动作必须通过单独 PR 执行，并完成最终回归。

## 主实现目录（新代码优先）

- `capabilities/`：业务能力边界（`capabilities/rag/`、`capabilities/memory/`）。
- `storage/`：统一存储边界（`storage/sqlite/`、`storage/vector/`）。
- `services/`：API 面向业务服务层。
- `agent/brain/`、`agent/runtime/`：Brain 与 Runtime 边界。

## 兼容层迁移表（旧路径 -> 主实现）

- `knowledge.knowledge_loader` -> `capabilities.rag.indexing.loader`
- `knowledge.knowledge_chunker` -> `capabilities.rag.indexing.chunker`
- `rag.loader` -> `capabilities.rag.indexing.loader`
- `rag.chunker` -> `capabilities.rag.indexing.chunker`
- `rag.retriever` -> `capabilities.rag.retrieval.retriever`
- `rag.quality` -> `capabilities.rag.retrieval.quality`
- `rag.diagnostics` -> `capabilities.rag.retrieval.diagnostics`
- `rag.rerank` -> `capabilities.rag.rerank.rerank`
- `rag.vector_store` -> `storage.vector.vector_store`
- `memory.database_manager` -> `storage.sqlite.database_manager`
- `memory.vector_store` -> `storage.vector.vector_store`
- `memory.summary_memory` -> `capabilities.memory.summary`
- `memory.doc_fingerprint` -> `capabilities.rag.indexing.fingerprint`
- `memory.rerank` -> `capabilities.rag.rerank.rerank`

## 兼容层删除的破坏面

- 外部脚本或下游代码若仍 `import rag.* / knowledge.* / memory.*`，删除目录后会触发 `ImportError`。
- 删除兼容层目录不会删除运行数据，也不应影响 `vector_db/`、`workspace/`、`long_term_memory.db`、`doc_fingerprint.json`。
- 删除兼容层目录本身不等于重建知识库，不应触发向量库重建。

## 删除前检查清单（必须全部满足）

1. 静态扫描确认全仓无旧导入（`rag.*`、`knowledge.*`、`memory.*`）。
2. `python -m pytest` 通过。
3. WebUI 手动回归通过：聊天、后台任务、文件上传、配置保存、知识库状态/同步。
4. 如存在外部调用方，先完成迁移通知，再执行删除 PR。
