# GeoClaw-LS Agent 改造阶段八（收敛验收）

## 阶段目标

在前七阶段完成 Brain / Runtime / Capability / Storage / KG-RAG 骨架后，本阶段聚焦：
- 架构边界一致性核验；
- 默认行为兼容性核验；
- 回归测试与轻量导入检查；
- 进入真实功能 MVP 前的收敛结论。

本阶段不继续新增架构层，不实现真实 KG-RAG 或 AutoML。

## 检查范围

- 工作区与差异：`git status --short`、`git diff --stat`、关键配置 diff。
- 核心代码：`core/agent_core.py`、`core/graph_agent.py`、`tools/registry.py`。
- 新边界目录：`agent/brain/`、`agent/runtime/`、`capabilities/`、`storage/`。
- 配置：`config/config.yaml`、`config/config.default.yaml`、`config/planner.yaml`、`core/config.py`。
- 文档：`docs/*architecture*.md`、`docs/capability_development.md`、`AGENTS.md`。
- 测试：`python -m pytest` 全量。

## 当前架构边界总结

- Brain
  - `agent/brain/LLMBrain` 为薄封装，包装 planner/decision/synthesis/review/small-talk/memory-query。
  - 不承载 RAG/KG-RAG/AutoML 业务实现，不直接做持久化。

- Runtime
  - `agent/runtime/` 负责运行时门面与持久化辅助（`GraphRuntime`、`RuntimePersistence`）。
  - 不承载 LLM 推理逻辑，不承载能力实现细节。

- Capability
  - `capabilities/rag` 默认启用；
  - `capabilities/kg_rag` 已有完整最小骨架，但默认禁用；
  - `capabilities/automl` 仍为占位，不注册默认工具。

- Storage
  - `storage/` 为薄适配层（sqlite/artifacts/vector/graph 协议占位）。
  - 未迁移真实 SQLite schema，未重建 ChromaDB。
  - 旧模块继续作为底层实现保留。

- Tools
  - `tools/registry.py` 仍保留标准工具并合并 enabled capability 工具；
  - capability 加载失败可 warning 并安全回退；
  - 默认工具列表不包含 `KG_RAG`、`AUTOML`。

## 测试结果

- 执行命令：`python -m pytest`
- 结果：`53 passed, 15 warnings`
- 结论：阶段二到阶段七新增边界与兼容测试均通过，未出现行为回归。

## 配置检查结果

- `core/config.py` 仍强制：`LLM_PROVIDER = "ollama"`。
- `config/planner.yaml` 默认工具仍为：
  - `RAG`、`MEMORY`、`LLM`、`CALCULATOR`、`DISCOVERY`、`DATA_PROFILE`、`FILE_INSPECTOR`
- `KG_RAG` / `AUTOML` 未进入 Planner 默认工具列表。
- `observability.enabled`：
  - `config/config.yaml` 当前为 `false`
  - `config/config.default.yaml` 当前为 `false`
  - 两者一致。

## 默认工具列表核验

通过 `tools.registry.get_tool_instances().keys()` 验证：
- 包含：`RAG`、`MEMORY`、`LLM`、`CALCULATOR`、`DISCOVERY`、`DATA_PROFILE`、`FILE_INSPECTOR`
- 不包含：`KG_RAG`
- 不包含：`AUTOML`

## KG-RAG / AutoML 状态

- KG-RAG：骨架完成（stub），`capability.enabled=False`，默认不启用。
- AutoML：目录占位，未注册默认工具，未进入 Planner 默认执行。

## 已知风险与说明

- 轻量导入检查中，直接执行 `import capabilities.registry` 会级联加载 `capabilities.rag` 与 `PyMuPDF`，在某些环境下可能较慢；本阶段已修复一处包级循环导入风险（`tools/__init__.py` 改为惰性导出）。
- 运行数据目录（如 `workspace/`）存在本地文件，属于运行态数据，不做清理。
- `AGENTS.md` 包含“当前 Git/工作区”描述，适合作为本仓库开发现场说明；若后续希望更稳态，可在后续文档维护时弱化“当前”措辞。

## 是否建议继续架构拆分

结论：**不建议继续新增架构层**。  
前七阶段边界已足够支撑下一步真实功能 MVP，继续拆层将带来收益递减和回归成本上升。

## 下一阶段建议（MVP 选择）

建议进入真实功能开发阶段，优先级可选：

1. `KG-RAG MVP`（推荐优先）
   - 小规模文档 ingestion -> 实体/关系构建 -> graph+vector 融合召回；
   - 通过显式开关灰度启用，不改变默认 Planner。

2. `AutoML MVP`
   - 先做实验记录与模型产物协议，再补最小训练/评估链路；
   - 不影响现有问答主链路。

3. `WebUI / 任务系统回归增强`
   - 强化任务可观测性与失败可解释性；
   - 作为 MVP 支撑工程保障。

