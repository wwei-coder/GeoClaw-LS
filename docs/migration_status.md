# GeoClaw-LS 迁移状态（事实源）

> 本文档是“当前架构迁移状态”的事实源。  
> 当 `AGENTS.md`、`docs/architecture_target.md` 与本文件冲突时，以本文件为准。

## 1. 当前边界状态

- Brain：`agent/brain/` 已接入主流程，负责规划、决策、综合、审核等推理门面，不承担工具执行和持久化。
- Runtime：`agent/runtime/` 已接入，负责运行门面与持久化辅助，不承载 RAG 业务实现。
- Capability：`capabilities/` 已建立能力边界；`rag` 默认启用，`kg_rag` 默认禁用，`automl` 仍为占位。
- Storage：`storage/` 已作为统一存储边界接入，当前为薄适配，不迁移运行数据。
- Services：`services/` 已承接 API 业务编排，路由层保持参数校验与错误映射。

## 2. 兼容层与旧导入路径状态

- 兼容层目录 `rag/`、`knowledge/`、`memory/` 已删除。
- 旧导入路径已下线：`rag.*`、`knowledge.*`、`memory.*` 不再受支持。
- 若外部脚本仍使用旧导入路径，运行时会触发 `ImportError`。

## 3. 主实现路径（后续开发必须使用）

- 业务能力：`capabilities/`
- 存储边界：`storage/`
- 推理门面：`agent/brain/`
- 运行门面：`agent/runtime/`
- 服务编排：`services/`

## 4. 历史文档说明

- `docs/archive/compatibility_layers.md` 是兼容层删除前的迁移说明，属于历史文档。
- 该历史文档可用于查阅旧路径到新路径的映射，不用于判定当前目录是否仍存在。
