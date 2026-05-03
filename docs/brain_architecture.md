# GeoClaw-LS Brain 架构说明（阶段四）

## 1. 为什么需要 LLM Brain 层

当前系统中，规划、决策、审核、综合回答等 LLM 职责分散在 `core/agent_core.py`、`core/graph_agent.py`、`core/chains.py`。  
阶段四引入 `agent/brain/`，目标是把“大脑职责”显性化，同时保持现有行为稳定。

本阶段定位：
- 只建立边界与门面；
- 不重写 Graph 流程；
- 不迁移工具执行逻辑；
- 不改变 API / WebUI / 工具名与工具协议。

## 2. 四层职责边界

- Brain（`agent/brain/`）
  - 意图识别（闲聊/记忆查询）
  - 任务规划（plan）
  - 工具路由决策（decide）
  - 回答综合（synthesize）
  - 回答审核（review）
  - 提示词访问边界（prompt_catalog）

- Runtime（当前主要在 `core/graph_agent.py` + `agent/executor.py`）
  - LangGraph 节点推进
  - 步骤执行与错误处理
  - 任务状态与执行轨迹
  - 取消/重试/继续
  - 产物落库

- Capability（`capabilities/*`）
  - RAG、未来 KG-RAG、未来 AutoML 的业务实现
  - 与工具层解耦的能力边界和服务接口

- Tool（`tools/*`）
  - 工具输入输出适配（`ToolInput/ToolResult`）
  - 可执行工具名与注册
  - 不承载复杂大脑推理逻辑

## 3. 当前 LLMBrain 包装范围

`agent/brain/llm_brain.py` 当前薄封装以下旧链路：
- `PlannerChain`
- `HeuristicDecisionChain`
- `SynthesisChain`
- `SmallTalkChain`
- `MemoryQueryChain`

并提供门面方法：
- `is_small_talk()`
- `is_memory_query()`
- `answer_small_talk()`
- `answer_memory_query()`
- `plan()`
- `decide()`
- `synthesize()`
- `review()`
- `normalize_answer_terms()`

说明：`review()` 仍复用现有 reviewer 提示词与 LLM 调用策略，只是入口移入 Brain。

## 4. GraphAgent 当前接入程度

`core/graph_agent.py` 仍是 Runtime 主体，状态结构、节点名和边结构未改变。  
本阶段仅做“优先委托”：
- planner 节点优先调用 `core.brain.plan()`
- decision 节点优先调用 `core.brain.decide()`
- solver 节点优先调用 `core.brain.synthesize()`
- reviewer 节点优先调用 `core.brain.review()`

若 `core.brain` 不可用，仍回退旧逻辑，确保可回滚。

## 5. 提示词分层建议

- Brain prompts
  - 规划：`config/planner.yaml` 的 `prompts.planner_task`
  - 综合回答：`prompts.final_answer`
  - 审核：`prompts.review`
  - 轻问答：`prompts.small_talk`

- Capability prompts
  - 检索改写、关键词扩展、元数据过滤
  - 未来 KG-RAG / AutoML 的能力专属提示

- Tool deterministic logic
  - 工具输入输出适配、结构化结果拼装
  - 不放推理型 prompt 编排

## 6. 未来迁移建议（阶段五以后）

- 逐步将 reviewer/solver 中散落的 LLM 细节完全移入 Brain；
- 在 Brain 中统一输出结构（Plan/Decision/Review/Answer）并保持 Graph 状态兼容；
- 引入 capability 路由策略（但不把能力实现塞进 Brain）；
- KG-RAG、AutoML 通过 capability 接口接入，由 Brain 负责“何时调用”，Capability 负责“如何实现”。

