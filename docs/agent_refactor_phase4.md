# GeoClaw-LS Agent 化改造（Phase 4）

## 阶段目标
- 将单次请求内执行升级为可追踪、可恢复、可管理的任务雏形。
- 保持聊天主流程、RAG、数据分析工具与 `/api/chat` 响应兼容。
- 新增任务持久化、任务查询、产物管理与前端任务面板。

## 为什么需要任务持久化
- 仅依赖单次请求内状态，无法跨请求查看历史执行过程。
- 数据分析和检索步骤产物需要与任务关联，便于回放与复用。
- 为后续“后台长任务/取消重试/多文件分析”提供统一存储基础。

## TaskStore 设计
- 新增 `agent/task_store.py`，归属 Agent 任务域。
- 复用现有 `long_term_memory.db` 与 `DatabaseManager` 锁/连接模型，避免多数据库并发复杂性。
- 核心方法：
  - `ensure_schema()`
  - `save_task(task, session_id=None)`
  - `update_task_status(task_id, status, final_answer=None)`
  - `save_step(task_id, step, position)`
  - `save_artifact(task_id, artifact)`
  - `get_task(task_id)`
  - `list_tasks(session_id=None, limit=50)`
  - `list_artifacts(task_id=None, limit=50)`
  - `get_artifact(artifact_id)`
- 失败策略：写库异常只记录日志，不中断主聊天流程。

## SQLite 表结构
- `agent_tasks`
  - `id TEXT PRIMARY KEY`
  - `session_id TEXT`
  - `user_query TEXT`
  - `status TEXT`
  - `final_answer TEXT`
  - `metadata_json TEXT`
  - `created_at TEXT`
  - `updated_at TEXT`
- `agent_steps`
  - `id TEXT PRIMARY KEY`
  - `task_id TEXT`
  - `position INTEGER`
  - `tool_name TEXT`
  - `instruction TEXT`
  - `status TEXT`
  - `input_json TEXT`
  - `result_json TEXT`
  - `error TEXT`
  - `started_at TEXT`
  - `finished_at TEXT`
  - `metadata_json TEXT`
- `agent_artifacts`
  - `id TEXT PRIMARY KEY`
  - `task_id TEXT`
  - `name TEXT`
  - `type TEXT`
  - `path TEXT`
  - `url TEXT`
  - `mime_type TEXT`
  - `metadata_json TEXT`
  - `created_at TEXT`

## 状态语义
- `AgentStep` 状态：
  - `pending`
  - `running`
  - `success`
  - `failed`
  - `skipped`（保留）
- `AgentTask` 状态：
  - `pending`
  - `running`
  - `success`
  - `failed`
  - `partial`
  - `canceled`（预留）
- 当前落地规则：
  - 生成有效最终回答且步骤全成功：`success`
  - 生成有效回答但存在失败步骤：`partial`
  - 未生成有效回答：`failed`

## 执行链路接入
- `core/agent_core.py`
  - 初始化 `TaskStore`（失败降级为无持久化模式）。
- `core/graph_agent.py`
  - planner 节点创建任务后入库。
  - decision 节点同步步骤并入库。
  - executor 节点每步执行后保存 `AgentStep`；如有产物则保存 `Artifact` 并关联 `task_id`。
  - solver 节点更新 `final_answer` 与任务最终状态。
- 保持 `execution_trace`、`steps`、`artifacts` 原有返回能力。

## Artifact 模型增强
- `agent/state.py` 的 `Artifact` 增加字段：
  - `id`
  - `task_id`
  - `name`
  - `type`
  - `path`
  - `url`
  - `mime_type`
  - `size`
  - `metadata`
  - `created_at`
- 兼容策略：
  - 保留 `kind` 映射输出（`kind == type`）兼容旧前端/旧工具。
  - 保持第三阶段 `DATA_PROFILE` 返回结构可继续使用。

## 新增/增强 API
- `GET /api/tasks`
  - 支持 `session_id`、`limit`
  - 返回最近任务列表。
- `GET /api/tasks/{task_id}`
  - 返回 `task`、`steps`、`artifacts`。
- `GET /api/tasks/{task_id}/artifacts`
  - 返回任务关联产物列表。
- `GET /api/artifacts`
  - 返回最近产物列表。
- `GET /api/artifacts/{artifact_id}`
  - 复用第三阶段接口并增强：
    - 文件产物：返回下载流。
    - 非文件产物：返回 metadata + download_url。

## 前端任务/产物面板
- 在聊天区右侧新增轻量“任务工作台”：
  - 最近任务列表。
  - 当前任务详情（问题、状态、步骤、回答摘要、产物）。
  - 产物可直接下载。
- 保持聊天主流程不变，回答下方 `execution_trace` 展示继续保留。
- 移动端改为纵向布局，避免溢出。

## 安全边界
- 产物下载仅允许 `workspace/artifacts/` 下文件。
- 不支持任意 path 参数读取，不暴露任意绝对路径。
- 不新增代码执行能力，不引入 Python Sandbox。

## 兼容关系
- `/api/chat` 请求参数保持兼容，响应核心字段保持兼容。
- 工具名保持不变：
  - `RAG`
  - `MEMORY`
  - `LLM`
  - `CALCULATOR`
  - `DISCOVERY`
  - `DATA_PROFILE`
  - `FILE_INSPECTOR`
- 第三阶段上传与分析流程不变，仅新增任务化管理能力。

## Phase 5 建议
- 后台长任务与任务队列。
- 任务取消、重试与失败恢复。
- 图表类产物工具（趋势、分布、对比）。
- 报告生成流水线（多步骤复用）。
- 多文件联合分析与任务模板。
- 权限与审计（单机可选开关）。
