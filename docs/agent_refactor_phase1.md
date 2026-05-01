# GeoClaw-LS Agent 化改造（Phase 1）

## 目标
- 将系统主轴从“RAG 问答流程”整理为“Agent 编排 + 工具执行”。
- 保持现有 WebUI、API、配置与 RAG 问答行为兼容。
- 本阶段聚焦结构边界，不重写核心业务逻辑。

## 新目录职责
- `agent/`：Agent 运行态抽象与执行封装。
- `rag/`：RAG 能力统一入口（加载、切块、向量检索、重排）。
- `tools/`：统一工具协议、工具包装层、注册中心。

## Agent 主轴与 RAG 工具化
- Agent 负责“规划 -> 决策 -> 执行 -> 汇总 -> 审核”的流程编排。
- RAG 在能力边界上归类为工具能力，不再作为系统唯一主路径。
- 工具名保持 `RAG/MEMORY/LLM/CALCULATOR/DISCOVERY`，保证 Planner 输出与现网行为不变。

## 兼容迁移策略
- 采用“新增目录封装旧实现”，优先低风险演进。
- 旧路径继续保留并可直接被当前代码引用：
  - `core/tools.py`
  - `memory/vector_store.py`
  - `memory/rerank.py`
  - `knowledge/knowledge_loader.py`
  - `knowledge/knowledge_chunker.py`
- 新路径通过 wrapper/re-export 暴露统一入口，不改变旧实现逻辑。

## 本阶段新增基础协议
- `tools/base.py` 定义：
  - `ToolInput`
  - `ToolResult`
  - `BaseTool`
- `ToolResult` 当前字段：
  - `success: bool`
  - `content: str`
  - `metadata: dict`
  - `artifacts: list`
  - `error: str | None`

## 本阶段新增状态模型
- `agent/state.py` 定义：
  - `AgentTask`
  - `AgentStep`
  - `AgentState`
  - `Artifact`
- 当前先作为后续扩展基础，不强制替换现有 `GraphAgent` 状态字典。

## 第二阶段建议
- 逐步让 `GraphAgent` 节点使用 `agent.state` 结构。
- 将 `core/tools.py` 逐步拆分到 `tools/*.py` 具体实现，减少核心层直接依赖。
- 让 `core/agent_core.py` 优先依赖 `agent.executor` 与标准注册中心。
- 为工具执行增加统一观测字段（耗时、token、引用源、错误码）。
