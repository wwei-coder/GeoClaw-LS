# KG-RAG Capability（阶段七骨架）

本目录提供 KG-RAG 最小可扩展骨架，目标是建立边界而不是立即启用默认执行。

## 当前模块

- `schemas.py`：实体、关系、图检索与混合检索数据结构
- `graph_store.py`：`InMemoryGraphStore` 纯内存图存储 stub
- `entity_extractor.py`：规则型实体抽取 stub（不调用 LLM）
- `relation_extractor.py`：规则型关系抽取 stub（不调用 LLM）
- `graph_retriever.py`：图检索器
- `hybrid_retriever.py`：图+向量融合检索器（向量侧可选）
- `service.py`：`KGRagService` 聚合入口
- `tool.py`：`KGRagTool`（工具名 `KG_RAG`）
- `capability.py`：capability 声明（`enabled=False`）

## 当前约束

- 默认禁用，不进入默认工具可执行列表。
- 不修改 `config/planner.yaml` 默认工具集合。
- 不调用真实 LLM 做实体/关系抽取。
- 不依赖外部图数据库。

## 后续扩展方向

- `graph_store` 替换为 `storage.graph` 的真实适配器（Neo4j/SQLite/其他）
- 引入基于 LLM 的抽取链路（可配置开关）
- 与 `capabilities/rag` 做证据级融合与重排序
- 通过显式开关逐步开放 Planner 使用 `KG_RAG`
