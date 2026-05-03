# GeoClaw-LS KG-RAG 架构说明（阶段七）

## 1. KG-RAG 定位

KG-RAG 在本项目中属于 **Capability 层**，用于提供“图谱证据 + 文本证据”的联合检索能力。  
它不是 Brain，也不是 Runtime。

- Brain 负责“何时调用 KG-RAG”
- KG-RAG capability 负责“如何构建/检索图谱并融合证据”

## 2. 与现有 RAG 的关系

- 现有 `capabilities/rag`：以文档 chunk 向量检索为核心。
- 新增 `capabilities/kg_rag`：以实体/关系图检索为核心，可选融合向量结果。
- 当前阶段二者并存，默认仍使用现有 RAG，不改变问答行为。

## 3. Brain 未来路由方式（规划）

未来 Brain 可根据问题类型选择：
- 事实型文档问答：优先 `RAG`
- 实体关系推断/多跳关联：可尝试 `KG_RAG`
- 复杂问题：`RAG + KG_RAG` 融合

当前阶段不开放 Planner 默认调用 `KG_RAG`，避免行为变化。

## 4. KG-RAG capability 内部模块

- `entity_extractor.py`：实体抽取（当前规则 stub，不调用 LLM）
- `relation_extractor.py`：关系抽取（当前规则 stub，不调用 LLM）
- `graph_store.py`：图存储（当前 `InMemoryGraphStore`）
- `graph_retriever.py`：图检索
- `hybrid_retriever.py`：图+向量融合检索（向量检索器可选）
- `service.py`：`KGRagService` 聚合入口
- `tool.py`：`KGRagTool`（工具名 `KG_RAG`）
- `capability.py`：声明 capability，默认 `enabled=False`

## 5. 为什么当前默认 disabled

- 目前仅为最小可扩展骨架，未接入真实图数据库与稳定抽取链路；
- 直接开放会改变工具空间与 Planner 行为，带来回归风险；
- 阶段目标是“先立边界、再逐步启用”。

## 6. 后续接入路线

1. 文档 ingestion：从知识库 chunk 增量构建实体与关系；
2. 抽取升级：可配置切换到 LLM 抽取；
3. 图存储升级：对接 `storage/graph/`（GraphStore/EntityRepository/RelationRepository）；
4. 融合检索：与 RAG 证据统一排序与去重；
5. Planner 开放：在评估稳定性后再将 `KG_RAG` 加入默认可用工具。

## 7. 当前不改变问答行为的原因

- 默认 capability 列表不启用 `kg_rag`；
- `tools.registry` 仅合并 enabled capabilities；
- `config/planner.yaml` 未增加 `KG_RAG`，因此现有链路与结果保持不变。

