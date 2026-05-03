# GeoClaw-LS Capability 开发指南（阶段三）

## 1. 什么是 Capability

在本项目中，Capability 是“可被 Agent 调用的业务能力边界”，用于承载具体领域实现（如 RAG、未来 KG-RAG、AutoML）。

Capability 目标：
- 隔离业务实现与 Agent 主流程编排；
- 支持后续新增能力时，减少对 `core/` 的直接改动；
- 保持工具协议一致（`ToolInput` / `ToolResult`）。

## 2. Capability 与 Tool 的区别

- Capability：业务能力集合与边界（例如检索、同步、状态查询）。
- Tool：Agent 可执行的最小调用单元（例如 `RAG`、`DATA_PROFILE`）。

关系：
- 一个 capability 可以声明一个或多个 tool；
- tool 负责输入输出适配，复杂业务应放在 capability service；
- `tools/registry.py` 负责把 tool 装配成可执行 registry。

## 3. LLM Brain 与 Capability 边界

LLM Brain（当前主要在 `core/graph_agent.py`、`core/chains.py`）应负责：
- 规划（plan）
- 路由（route）
- 反思与审查（review）
- 最终综合回答（synthesis）

Capability 应负责：
- RAG / KG-RAG / AutoML / 文件分析等业务实现细节
- 能力内部状态与错误处理

不建议继续放进 `core/` 的内容：
- 新增能力的业务算法和实现细节
- 新增能力的内部数据处理流程

## 4. 新增一个 Capability 的推荐步骤

1. 新建目录 `capabilities/<name>/`。
2. 定义 service 边界（先薄封装，复用现有实现）。
3. 提供 capability 声明入口（`get_capability()`）。
4. 在 `capabilities/registry.py` 显式注册（静态导入，避免自动扫描副作用）。
5. 如需对外调用，新增/复用 tool 包装，并保持 `ToolResult` 协议兼容。
6. 增加最小测试：导入、注册、工具实例可获取、旧路径兼容。

## 5. 未来 KG-RAG 模块建议

建议放在 `capabilities/kg_rag/`：
- 图谱构建与更新
- 图谱检索与路径推理
- 与文档 RAG 的融合召回与证据整合
- 与工具层的稳定输入输出适配

## 6. 未来 AutoML 模块建议

建议放在 `capabilities/automl/`：
- 数据任务识别（分类/回归/聚类）
- 特征与训练流程编排
- 模型评估与报告产物生成
- 训练产物元数据管理接口

## 7. 如何保持旧工具兼容

- 保留 `tools/*.py` 现有导入路径；
- `tools/registry.py` 继续保留标准工具硬编码列表作为回退；
- capability 注册工具仅用于覆盖/补充同名工具，不破坏原工具名；
- 避免直接修改 Planner 工具集合，保持当前行为稳定。

