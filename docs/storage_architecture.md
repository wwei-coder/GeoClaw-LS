# GeoClaw-LS Storage 架构说明（阶段六）

## 1. 为什么需要 Storage 层

当前系统的持久化能力分散在多个旧模块中：会话在 `memory/database_manager.py`，任务与产物记录在 `agent/task_store.py`，文件产物在 `core/file_workspace.py`，向量索引在 `memory/vector_store.py`。  
阶段六的目标是先建立统一存储边界，后续能力扩展优先通过 `storage/` 接入，而不是继续把持久化细节塞进 AgentCore/Runtime/Capability。

本阶段特性：
- 新增适配器，不改真实数据，不改表结构；
- 不重建向量库，不迁移线上/本地运行数据；
- API 与 WebUI 行为保持不变。

## 2. Storage 与其他层边界

- Brain：不直接访问数据库、向量库、文件系统。
- Runtime：通过存储接口保存任务/步骤/产物，不关心底层 `TaskStore` 实现细节。
- Capability：可使用存储适配器（如向量索引适配器），不直接耦合 Agent 流程。
- API：继续使用稳定返回结构，不感知存储内部重构。

## 3. 当前底层实现仍保留

本阶段以下旧模块继续作为底层实现（未删除、未迁移）：
- `memory/database_manager.py`
- `agent/task_store.py`
- `core/file_workspace.py`
- `memory/vector_store.py`

## 4. 新增的 Storage 适配器

- `storage/sqlite/session_repository.py`
  - `SessionRepository` 薄封装 `DatabaseManager` 的会话方法：
  - `list_sessions/create_session/rename_session/delete_session`

- `storage/sqlite/task_repository.py`
  - `TaskRepository` 薄封装 `TaskStore`：
  - `save_task/save_step/save_artifact/get_task/list_tasks/list_artifacts/get_artifact`

- `storage/artifacts/artifact_store.py`
  - `ArtifactStore` 薄封装 `FileWorkspace` + `TaskRepository`：
  - `list_artifacts/get_artifact/register_artifact/resolve_artifact_path`
  - 当前以最小 wrapper 为主，未改 `/api/artifacts/{artifact_id}` 行为。

- `storage/vector/vector_index.py`
  - `VectorIndexAdapter` 薄封装现有 `VectorStore`：
  - `count/get_status/search/build_full/add_chunks/deactivate_by_docs/load`
  - 当前为适配边界，不强制改 `RagService` 的主调用路径。

## 5. RuntimePersistence 当前变化

`agent/runtime/persistence.py` 现已支持注入 `TaskRepository`：
- 传入 repository 时，优先调用 repository；
- 不传入时，仍从 `agent_core.task_store` 构造兼容路径；
- `save_task/save_step/save_artifact` 对外行为不变，异常继续降级为 warning。

## 6. 为什么本阶段不迁移真实数据或 schema

- 当前系统已有稳定 SQLite/ChromaDB 运行数据，直接改 schema 或迁移风险高；
- 阶段六重点是“边界显性化”，不是“底层替换”；
- 先建立 adapter 和测试，再在后续阶段分步替换调用方，风险更低、回滚更简单。

## 7. 后续扩展建议

- KG-RAG 存储建议：
  - 新增 `storage/graph/`
  - `GraphStore`
  - `EntityRepository`
  - `RelationRepository`

- AutoML 存储建议：
  - 新增 `storage/experiments/`
  - `ExperimentRepository`
  - `ModelArtifactRepository`

建议沿用当前策略：先 adapter，再替换调用点，最后再考虑底层实现演进。

