# GeoClaw-LS Runtime 架构说明（阶段五）

## 1. 为什么需要 Agent Runtime 层

在当前代码中，`core/graph_agent.py` 同时承担流程推进与持久化细节。  
阶段五引入 `agent/runtime/` 的目标是把“执行时职责”显性化，便于后续迁移取消、重试、继续、事件追踪等运行时能力，而不影响 Brain 和 Capability。

本阶段原则：
- 不重写 LangGraph；
- 不改变 API 与 WebUI；
- 不迁移 LLM 思考逻辑；
- 不迁移 RAG/工具实现逻辑。

## 2. Runtime 与 Brain 的区别

- Brain（`agent/brain/`）
  - 规划、路由、审查、综合回答
  - 提示词组织与 LLM 调用策略

- Runtime（`agent/runtime/`）
  - 流程推进（依托 GraphAgent）
  - 步骤执行状态流转
  - 任务/步骤/产物持久化辅助
  - 运行时门面（GraphRuntime）

## 3. Runtime 与 Capability/Tool 的区别

- Capability / Tool 负责“做什么业务”：
  - RAG、文件分析、计算器、未来 KG-RAG / AutoML
- Runtime 负责“如何推进执行过程”：
  - 节点推进、状态更新、持久化落盘、运行时安全降级

## 4. 当前 RuntimePersistence 接管范围

新增 `agent/runtime/persistence.py`：
- `save_task(task)`
- `save_step(task_id, step, position)`
- `save_artifact(task_id, artifact)`

特性：
- 复用现有 `TaskStore`；
- 异常仅 warning，不中断主流程；
- 行为与原 `GraphAgent._safe_save_*` 一致。

`core/graph_agent.py` 已改为委托 `RuntimePersistence`，但 `_safe_save_*` 方法名保留，确保低风险兼容。

## 5. GraphAgent 当前保留职责

`GraphAgent` 仍是 LangGraph workflow 实现主体：
- 状态结构（TypedDict）未改；
- 节点名和边结构未改；
- executor 调用行为未改；
- Brain 委托沿用阶段四结果；
- 持久化细节改为 runtime 层门面委托。

## 6. 后续迁移建议（阶段六+）

建议逐步迁入 `agent/runtime/` 的能力：
- cancellation 协调（统一取消状态传播）
- retry/resume 策略辅助
- trace event 标准化结构
- artifact normalization 统一逻辑
- task status derivation 统一策略

建议保持在 `core/graph_agent.py` 的内容（短期）：
- 节点编排图结构
- 业务流程主干逻辑

## 7. API / WebUI 为何不应感知 runtime 内部

- API 只关心稳定响应字段；
- WebUI 只消费任务状态、步骤、产物与进度；
- runtime 内部实现可迭代替换，避免牵动前后端契约。

