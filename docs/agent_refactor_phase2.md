# GeoClaw-LS Agent 化改造（Phase 2）

## 本阶段完成内容
- 将“结构化目录”推进为“运行时按 Agent 步骤执行”。
- 在不重写 LangGraph 主流程的前提下，接入标准执行器与任务状态。
- 保持 `RAG/MEMORY/LLM/CALCULATOR/DISCOVERY` 工具名兼容。
- 保持 `/api/chat` 原字段兼容，并新增可选执行轨迹字段。

## 运行时模型关系
- `AgentTask`：单次请求的任务容器，包含任务状态、步骤集合、最终回答与产物。
- `AgentStep`：单步执行状态机，支持 `pending/running/success/failed/skipped`。
- `ToolResult`：每个工具的标准输出（`success/content/metadata/artifacts/error`）。
- 执行流程：
  1. Planner 产出步骤。
  2. Executor 逐步执行并更新 `AgentStep`。
  3. 结果写回 `AgentTask` 与 Graph state。
  4. Solver 继续使用旧 `step_results` 生成最终回答。

## GraphAgent 兼容策略
- 继续保留旧字段：`question/steps/step_results/sources/trace`。
- 新增并行字段：`task/task_id/tool_results_v2/execution_trace/artifacts`。
- Executor 节点改为通过 `agent/executor.py` 执行，避免单步异常击穿接口。
- 低质量检索重规划逻辑保持可用，仍基于检索质量阈值触发。

## /api/chat 新增响应字段
- 保持已有字段不变：
  - `answer`
  - `sources`
  - `trace`
  - `session_id`
- 新增可选字段：
  - `task_id`
  - `execution_trace`
  - `steps`
  - `artifacts`

## 前端执行过程展示
- 在每条助手回答下新增“执行过程”简洁区域。
- 有 `execution_trace/steps` 时显示；无数据时自动隐藏。
- 保持原消息渲染与来源显示逻辑不变。
- 样式做最小增量，移动端不溢出。

## 第三阶段建议
- 将 `tool_results_v2` 与 `artifacts` 接入更细粒度可视化（例如可折叠步骤详情）。
- 在 `tools/` 下增加数据处理类工具（文件解析、统计、图表）并复用当前 Executor。
- 按需增加任务持久化（SQLite 表）与任务回放，不影响现有会话接口。
