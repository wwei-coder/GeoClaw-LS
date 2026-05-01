# GeoClaw-LS Agent 化改造（Phase 5）

## 目标
- 将同步请求内执行升级为支持后台任务生命周期管理。
- 在不引入重型队列系统的前提下，实现本地可用的取消、重试、继续与进度轮询。
- 保持 `/api/chat` 同步兼容与现有工具生态不变。

## TaskRunner 设计
- 新增 `agent/task_runner.py`，由 `AgentCore` 持有单例。
- 基于 `ThreadPoolExecutor(max_workers=1)` + `threading.Event`：
  - 提交后台任务；
  - 查询运行状态；
  - 协作式取消；
  - 重试失败任务；
  - 继续未完成任务。
- 运行态内存映射：
  - `task_id`
  - `future`
  - `cancel_event`
  - `started_at`

## 同步与后台关系
- `/api/chat`：保持原有同步路径，不改入参与基本响应字段。
- `POST /api/tasks`：新增后台执行入口，返回 `task_id`。
- 同步与后台共享同一套 Agent/Graph/TaskStore 逻辑，结果统一可在任务面板查看。

## 新增/增强 API
- 新增 `POST /api/tasks`
  - 创建后台任务，参数：`message/session_id/file_id/run_mode`。
- 新增 `POST /api/tasks/{task_id}/cancel`
  - 发送取消请求（协作式取消）。
- 新增 `POST /api/tasks/{task_id}/retry`
  - 重试失败任务；可选 `step_id`（当前作为轻量语义记录）。
- 新增 `POST /api/tasks/{task_id}/resume`
  - 继续未完成任务（基于原任务上下文启动新后台任务）。
- 增强 `GET /api/tasks`
  - 返回 `is_running`、`cancel_requested`、`progress`。
- 增强 `GET /api/tasks/{task_id}`
  - 返回 `task/steps/artifacts` 及 `is_running/cancel_requested/progress`。

## 取消、重试、恢复语义
- 取消：
  - 采用协作式取消，步骤边界生效；
  - 若工具调用本身耗时较长，取消可能在该步完成后生效。
- 重试：
  - 对失败/部分失败任务创建新的后台任务；
  - 关联 `resumed_from`，并复用原任务 `message/session_id/file_id` 上下文。
- 恢复：
  - 对 `canceled/failed/partial` 任务发起继续，创建新任务并关联来源任务。

## 进度计算
- 进度结构：
  - `total_steps`
  - `completed_steps`
  - `failed_steps`
  - `running_steps`
  - `percent`
- 映射规则：
  - `pending` -> 0%
  - `running` -> 按步骤完成度（限制在 1~99%）
  - `success` -> 100%
  - `partial/failed/canceled` -> 按已完成步骤比例

## 并发策略
- 默认串行后台执行（`max_workers=1`），避免本地 Ollama/SQLite/ChromaDB 并发冲突。
- `AgentCore` 增加执行互斥锁，降低同实例并发读写风险。
- 当前阶段重点是稳定可控，不追求高并发吞吐。

## 服务重启后的处理
- 启动时扫描 `status=running` 的历史任务并标记为 `partial`，写入中断原因：
  - “应用重启或进程中断，后台任务未能继续运行。”
- 本阶段不保证跨进程保留旧 `Future`，需通过 `resume` 重新提交。

## 已知限制
- 取消为协作式，不是线程强杀。
- `retry step_id` 目前是轻量语义入口，底层执行仍以任务级重提交流程为主。
- 后台任务在极端异常场景下可能只保留部分步骤状态。

## 第六阶段建议
- 多文件联合分析工作流。
- 图表类工具（分布/趋势/对比）。
- 更正式的工作流编排与模板化。
- WebSocket/SSE 实时推送进度。
- 报告导出与归档策略。
- 权限控制与审计能力。
