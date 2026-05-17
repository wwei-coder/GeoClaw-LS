# GeoClaw-LS 项目信息

## 项目概览

GeoClaw-LS 是一个面向地质滑坡防治领域的本地智能助手。项目目标是把本地地质灾害资料构建为知识库，并结合 RAG、长期记忆、任务规划、工具调用、后台任务、上传文件分析，以及后续 KG-RAG / AutoML 能力扩展，为用户提供中文专业问答、资料引用、计算、对话回顾、深度洞察、数据文件概览和任务过程追踪。

当前应用形态是 FastAPI + 原生 WebUI。主入口是 `app.py`，HTTP 路由位于 `api/`。核心运行依赖本地 Ollama，后端维护 SQLite 会话与任务记录、ChromaDB 向量索引、知识库文档指纹、文件工作区索引，以及可选 Phoenix / OpenTelemetry 观测链路。

当前架构已经进入“边界收口 + 可审计执行闭环”阶段：

- `agent/workflow/nodes/` 承载 LangGraph 的 planner、decision、executor、solver、reviewer 节点实现。
- `agent/policies/` 承载回答要求检查、可信度分级、补救状态和任务状态等纯规则策略。
- `agent/executor.py` 负责工具执行、工具结果评估、受控补救、失败熔断、补救指标和证据质量检查。
- 规划、补救和证据 trace 都只保存结构化短摘要，不保存完整隐藏推理过程或 CoT。

## 当前事实源

- 当前迁移事实源：`docs/migration_status.md`。
- 当前边界开发准则：`docs/architecture_boundaries.md`。
- 当前配置事实源：`config_runtime.py`。
- 当前工具注册事实源：`tools/registry.py` 与 `tools/base.py`。
- 当前 RAG 检索主路径：`capabilities/rag/retrieval/pipeline.py`。

已删除并禁止重新依赖的旧路径：

- 旧导入路径已下线；外部脚本若仍导入 `rag.*`、`knowledge.*`、`memory.*` 会触发 `ImportError`。
- 顶层兼容目录：`rag/`、`knowledge/`、`memory/`。
- 旧 core shim：`core/chains.py`、`core/config.py`、`core/planner.py`、`core/question_classifier.py`、`core/context_judge.py`、`core/tools.py`。
- 旧 agent 工具门面：`agent/registry.py`。
- RAG 旧工具包装：`capabilities/rag/tool.py`。

`core/` 当前只保留运行装配和基础设施：

- `core/__init__.py`
- `core/agent_core.py`
- `core/agent_core_facades.py`
- `core/graph_agent.py`
- `core/file_workspace.py`
- `core/reset_handler.py`

不要把 Brain、Planner、Config、Classifier、Tool Registry 等事实源重新塞回 `core/`。
- `core/agent_core.py` 当前定位是 composition root / runtime facade；`core/graph_agent.py` 当前定位是 LangGraph wiring facade。后续若继续收口，应优先把状态与路由语义下沉到 `agent/workflow/`，而不是在 `core/` 扩张新业务逻辑。

## Git 与工作区规则

- 本仓库允许存在未提交改动；不要误删、回滚或清理用户改动。
- 当前本地扫描时间：2026-05-16。
- 当前工作区存在大量未提交改动和新增文件，涉及 `.gitignore`、`AGENTS.md`、`app.py`、`config_runtime.py`、`agent/`、`api/`、`capabilities/`、`core/`、`services/`、`storage/`、`tools/`、`utils/`、`static/` 等。
- 本次扫描确认的新增或重点变更包括：`config/terminology.yaml`、`agent/policies/relevance.py`、`tools/tool_catalog.py`、`data/` 下新增的地质灾害大模型与滑坡识别 PDF，以及已删除的 `tools/calculator_tool.py`。
- `docs/` 和 `tests/` 仅作为本地资料/验证目录保留，不上传 GitHub；它们已被 `.gitignore` 忽略。
- `workspace/` 是本地运行目录；不要手动清理上传文件、产物或 `files_index.json`，除非任务明确要求。
- 当前根目录可见 `vector_db/`、`long_term_memory.db`、`doc_fingerprint.json` 等本地运行数据；这些文件已被 `.gitignore` 覆盖，不应手动改写、删除或上传。
- 禁止使用 `git reset --hard`、批量 checkout 或破坏性清理来处理工作区差异。

## 技术栈

- 后端：FastAPI、Uvicorn、Pydantic、python-multipart。
- Agent 编排：LangGraph、自定义 Brain / Workflow / Runtime / Policies / Executor。
- 模型调用：本地 Ollama，当前强制 `LLM_PROVIDER = "ollama"`。
- 默认生成模型：`qwen2.5:7b`。
- 默认嵌入模型：`qwen3-embedding:4b`。
- RAG：ChromaDB、Ollama embedding、BM25、RRF、关键词 rerank、质量评估、低质量重规划。
- 文档解析：PyMuPDF、python-docx，支持 `.pdf`、`.docx`、`.txt`。
- 数据文件分析：CSV、Excel、TXT、JSON，使用 Python 常用库与 `openpyxl`。
- 前端：原生 HTML/CSS/JavaScript，无构建步骤。
- 观测：Arize Phoenix + OpenTelemetry，可通过 WebUI 开关控制。

## 运行方式

推荐从项目根目录运行：

```powershell
python app.py
```

`app.py` 默认监听 `127.0.0.1`，优先使用端口 `18765`，若端口被占用会向后扫描最多 120 个端口。启动成功后控制台会输出 WebUI 地址。

也可以使用 Uvicorn：

```powershell
uvicorn app:app --host 127.0.0.1 --port 18765
```

运行前需要确保：

- 已安装依赖：`pip install -r requirements.txt`
- Ollama 服务可访问。
- Ollama 中已准备好 `qwen2.5:7b` 和 `qwen3-embedding:4b`。
- 默认 LLM 地址：`http://localhost:11434/api/generate`
- 默认 Embedding 地址：`http://localhost:11434/api/embed`

常用验证命令：

```powershell
python -m pytest
python utils\health_check.py
python utils\tool_smoke_check.py
```

## 主要目录与文件

- `app.py`：FastAPI 应用入口，注册路由、挂载静态资源、处理 reset pending 异常和端口选择。
- `config_runtime.py`：配置事实源，读取 `config/config.yaml`、`config/prompts.yaml`、`config/planner.yaml` 并导出运行常量。
- `api/`：HTTP 路由层，负责请求校验、错误映射和响应返回。
- `services/`：业务服务层，封装 Agent、Session、Task、File、Config、KnowledgeBase、Observability 等服务，并包含 `config_io.py`、`config_metadata.py`、`config_support.py`、`serializers.py`。
- `core/`：运行总线和基础设施门面，只保留 AgentCore、GraphAgent、FileWorkspace、ResetHandler 及 facade。
- `agent/brain/`：推理门面，包含 planner、decision、smalltalk、synthesis、memory query adapter、context judge、question classifier、terminology、prompt catalog 和 schema；负责提示词组织、LLM 调用与回答后处理 helper，不执行工具、不做数据库持久化。
- `agent/workflow/`：LangGraph 节点和 helper，包括 planner/decision/executor/solver/reviewer、条件路由、取消、补救、solver 输出和状态适配。
- `agent/policies/`：纯规则策略，不能调用 LLM、不能做 I/O；当前包含回答要求、可信度、补救状态、任务状态和回答相关性检查等规则。
- `agent/runtime/`：GraphRuntime、RuntimePersistence 和 request context。
- `agent/executor.py`：标准工具执行器和工具闭环评估。
- `capabilities/`：业务能力边界，当前包含 RAG、Memory、KG-RAG 骨架、AutoML 占位。
- `storage/`：SQLite、artifact、vector、graph 存储适配器。
- `tools/`：标准工具协议、统一工具注册、Planner 可见工具目录和薄 wrapper；RAG、Memory、KG-RAG、AutoML 等业务能力实现应保留在 `capabilities/`，由 capability 暴露工具入口。
- `static/`：原生 WebUI。
- `config/`：运行配置、提示词、Planner 配置和术语配置。
- `data/`：知识库源文档，当前包含 4 个 PDF 和 1 个 DOCX。
- `docs/`：本地文档资料，不上传 GitHub。
- `tests/`：本地 pytest 测试，不上传 GitHub。
- `workspace/`：本地上传文件和产物目录，不上传 GitHub。

## API 概览

聊天与初始化：

- `GET /`
- `GET /api/bootstrap`
- `POST /api/chat`

会话：

- `GET /api/sessions`
- `POST /api/sessions`
- `POST /api/sessions/{session_id}/switch`
- `PATCH /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`

后台任务：

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/retry`
- `POST /api/tasks/{task_id}/resume`
- `GET /api/tasks/{task_id}/artifacts`

文件与产物：

- `POST /api/files/upload`
- `GET /api/files`
- `GET /api/artifacts`
- `GET /api/artifacts/{artifact_id}`

知识库与系统：

- `POST /api/kb/sync`
- `GET /api/kb/status`
- `GET /api/kb/documents`
- `GET /api/kb/diagnostics`
- `POST /api/kb/rebuild`
- `POST /api/kb/upload`
- `POST /api/system/reset`
- `POST /api/system/shutdown`

配置与观测：

- `GET /api/config`
- `PUT /api/config`
- `POST /api/config/reset`
- `GET /api/config/export`
- `POST /api/config/import`
- `GET /api/observability/status`
- `POST /api/observability/toggle`
- `GET /api/health`

`/api/chat` 保持兼容字段：

- `answer`
- `sources`
- `trace`
- `session_id`

增强字段：

- `task_id`
- `execution_trace`
- `steps`
- `artifacts`

## Agent 工作流

同步问答流程：

1. `api/routes_chat.py` 接收 `/api/chat` 请求。
2. `RAGBridge` 懒加载或复用单个 `AgentCore`。
3. `AgentCore.chat_async()` 先处理闲聊、记忆查询和待确认工具调用。
4. 普通问题进入 `GraphRuntime.run_async()`，再委托 `GraphAgent.run_async()`。
5. LangGraph 执行 `planner -> decision -> executor -> solver -> reviewer`。
6. `AnswerSynthesisService` 在回答生成后更新短期记忆、摘要记忆和用户偏好。
7. 对话写入 SQLite。

后台任务流程：

1. WebUI 通过 `POST /api/tasks` 提交后台任务。
2. `TaskRunner` 使用本地 `ThreadPoolExecutor` 串行运行任务。
3. `TaskStore` 持久化任务、步骤和产物。
4. 前端轮询任务列表和任务详情，支持取消、重试、继续。
5. 应用重启后，之前处于 running 的任务会被标记为 `partial`。

## 可用工具

默认 Planner 工具来自统一 registry 动态注入，当前包括：

- `RAG`：知识库检索。
- `MEMORY`：摘要记忆、最近对话、短期记忆和偏好上下文。
- `LLM`：直接调用本地模型。
- `DISCOVERY`：扩大检索范围并生成深度洞察。
- `FILE_INSPECTOR`：查看上传文件信息和内容预览。
- `DATA_PROFILE`：统计分析上传数据文件并生成 Markdown 报告。

当前 Agent 不再提供专用计算工具；涉及简单计算或数学表达式的问题由 `LLM` 普通回答处理，不保证严格数值计算能力。

Planner 可见工具说明由 `tools/tool_catalog.py` 统一生成；`tools/registry.py` 负责工具实例注册与 capability 工具合并。不要在 Planner 提示词里手写一份长期漂移的工具清单。

默认禁用：

- `KG_RAG`：KG-RAG 混合检索工具骨架，位于 `capabilities/kg_rag/`，`enabled=False`。

修改工具范围时必须同步检查：

- `config/planner.yaml`
- `tools/registry.py`
- `capabilities/registry.py`
- `core/graph_agent.py`
- 相关测试

## RAG 与检索

知识库构建：

- 文档来源：`data/` 下的 `.pdf`、`.docx`、`.txt`。
- 加载器：`capabilities/rag/indexing/loader.py`。
- 切分器：`capabilities/rag/indexing/chunker.py`。
- 指纹：`capabilities/rag/indexing/fingerprint.py`。
- 向量库：`storage/vector/vector_store.py`。

检索流程：

- 主入口：`capabilities/rag/retrieval/pipeline.py`。
- 支持 hybrid / vector / bm25 检索。
- 默认融合向量检索与 BM25，并用 RRF 合并结果。
- 支持 query rewrite、dual query、rerank、fast path、质量评估和检索指标记录。
- 当前 rerank 策略：`keyword`。
- 检索缓存 TTL：900 秒，最大 512 条。
- 低质量检索可触发 GraphAgent 重规划。

## 文件工作区

文件工作区位于 `workspace/`：

- `workspace/uploads/`：上传文件。
- `workspace/artifacts/`：分析报告等产物。
- `workspace/files_index.json`：本地上传和产物索引。

安全边界：

- 数据文件仅支持 `.csv/.xlsx/.xls/.txt/.json`。
- 知识库上传仅支持 `.pdf/.docx/.txt`。
- 单文件上限 20MB。
- 上传文件名会安全化处理。
- 文件读取限制在 `workspace/uploads/`。
- 产物下载限制在 `workspace/artifacts/`。
- 不执行用户上传代码，不执行 Excel 宏。

## 当前关键配置

`config/config.yaml` 当前关键项：

- `agent.max_context_len: 16000`
- `agent.max_history_rounds: 8`
- `models.ollama.model: qwen2.5:7b`
- `models.ollama.temperature: 0.7`
- `models.ollama.timeout: 35`
- `models.ollama.stream_timeout: 70`
- `models.embedding_backend: ollama`
- `models.embedding: qwen3-embedding:4b`
- `models.embedding_ollama_batch_size: 16`
- `rag.search_top_k: 3`
- `rag.expansion_top_k: 4`
- `rag.rerank_strategy: keyword`
- `rag.quality_threshold: 0.45`
- `graph.replan_max_attempts: 2`
- `graph.replan_on_low_quality: true`
- `graph.replan_low_quality_threshold: 0.35`
- `graph.replan_require_expansion: true`
- `graph.step_result_max_chars: 9000`
- `retrieval.fast_path.enabled: true`
- `retrieval.metrics.enabled: true`
- `kb_watcher.enabled: true`
- `observability.enabled: false`

重要限制：

- 当前版本仅支持本地 Ollama；远程 API 配置项已移除。
- 如需未来重新启用远程兼容 API，需要重新设计配置、客户端调用、UI 暴露和测试边界。
- 配置保存后只有部分运行态字段会热更新；模型、embedding、检索索引等深层配置通常需要重新初始化 Agent 或重启应用。
- `config_runtime.py` 是唯一配置事实源；新增“运行中立即生效”的配置口径时，必须同时说明是轻量运行态热更新，还是需要重新初始化 Agent / 重启应用。

## 提示词与术语边界

主要提示词位置：

- `config/prompts.yaml`
- `config/planner.yaml`
- `config/terminology.yaml`
- `agent/brain/prompt_catalog.py`

回答要求：

- 使用中文。
- 地质灾害专业问题应尽量引用资料来源。
- 明确区分“资料支持”和“模型推断”。
- 不输出隐藏推理过程或完整 CoT。

InSAR 术语要求：

- InSAR 必须解释为“干涉合成孔径雷达（Interferometric Synthetic Aperture Radar）”。
- 禁止误写为热红外、光学、多光谱、地物成像等无关技术。
- 术语配置文件：`config/terminology.yaml`。
- 术语修正实现：`agent/brain/terminology.py`。

## 文档与测试

`docs/` 当前结构：

- `README.md`：文档导航。
- `migration_status.md`：迁移状态事实源。
- `architecture_boundaries.md`：当前边界开发准则。
- `architecture_target.md`：目标架构摘要。
- `architecture/`：Brain、Runtime、Storage、KG-RAG、Planner trace 等专题架构文档。
- `guides/`：能力开发指南和回归检查清单。
- `refactor/`：阶段九到十二及工具闭环、补救、证据校验、观测指标说明。
- `archive/`：早期阶段记录与兼容层删除前说明。
- `inventory/`：当前文件作用清单。

`docs/guides/regression_checklist.md` 给出最小手动回归项，包括 WebUI 启动、健康检查、会话管理、知识库问答、文件上传、DATA_PROFILE、任务工作台、配置导入导出、知识库同步/重建和 Phoenix 开关。

自动测试：

- 使用 `python -m pytest`。
- 当前测试目录包含 45 个测试文件。
- 本次更新后已运行全量回归：`267 collected, 266 passed, 1 failed, 148 warnings`。失败用例为 `tests/test_prompt_catalog.py::test_dialog_context_prompts_are_catalog_managed`，当前原因是测试期望 query expansion 提示词包含“提取 3-5 个关键词；短问题可 2-4 个。”，但实际配置为“提取 1-3 个关键词；短问题可 1-2 个。”。
- 当前常见 warnings 来自 Python 3.14 下 LangChain/Pydantic V1 兼容提示，以及 ChromaDB/FastAPI/Starlette 对 `asyncio.iscoroutinefunction` 的弃用提示。

## 版本控制与忽略规则

`.gitignore` 当前排除：

- Python 缓存：`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`
- 虚拟环境：`.venv/`、`venv/`、`env/`
- IDE/系统文件：`.idea/`、`.vscode/`、`.DS_Store`、`Thumbs.db`
- 运行日志：`logs/`、`*.log`
- 本地数据库和索引：`*.db`、`*.sqlite`、`*.sqlite3`、`vector_db/`、`chroma/`
- 文档指纹与 reset 标记：`doc_fingerprint.json`、`.need_reset`
- 模型与缓存：`models/`、`.cache/`
- 环境变量：`.env`、`.env.*`
- 临时和构建产物：`tmp/`、`temp/`、`build/`、`dist/`、`*.egg-info/`
- 工作区运行数据：`workspace/uploads/`、`workspace/artifacts/`、`workspace/files_index.json`
- 本地验证资料：`tests/`、`docs/`

注意：

- `docs/` 和 `tests/` 不上传 GitHub。
- `workspace/` 是本地运行数据，不应无明确要求清理。
- `data/` 当前未被忽略，表示知识库源文档会随项目版本化；若后续涉及大文件或非公开资料，应改用 Git LFS、对象存储或调整忽略规则。

## 开发注意事项

- 修改配置常量优先改 `config_runtime.py`。
- 修改提示词优先改 YAML 或 `agent/brain/prompt_catalog.py`。
- 修改 API 时检查 `api/`、`services/` 和 `services/serializers.py`。
- 修改 Brain 时检查 `agent/brain/`，不要让 Brain 承担工具执行、文件系统或数据库持久化。
- `agent/brain/synthesis.py` 当前允许保留 prompt 构造、上下文压缩、术语约束和回答后记忆副作用编排；不要继续扩张为工具执行、数据库持久化或通用业务副作用入口。
- 修改 Workflow 节点时检查 `agent/workflow/nodes/` 和 helper，保持 `core/graph_agent.py` 为装配门面。
- 修改 Policies 时保持纯规则、无 I/O、无 LLM 调用。
- 修改 Runtime 时不要把 RAG、工具业务或提示词推理塞入 Runtime。
- 修改 Storage 时先加 adapter 和测试，不要直接迁移真实 SQLite/ChromaDB 数据或改表结构。
- 修改工具协议时保持 `ToolInput`、`ToolResult`、`BaseTool` 兼容。
- 修改工具范围时同步 Planner 提示词、工具 registry、capability registry 和测试。
- 修改 RAG 时重点检查 `capabilities/rag/retrieval/pipeline.py`、`storage/vector/vector_store.py`、`storage/vector/rerank_types.py`、`capabilities/rag/rerank/rerank.py`。
- 修改 KG-RAG 时保持默认 disabled，除非明确要求开放 Planner 和工具注册。
- 修改后台任务时检查 `agent/task_runner.py`、`agent/task_store.py`、`agent/runtime/`、`agent/workflow/`、`api/routes_tasks.py` 和 `static/app.js`。
- 修改文件上传或产物下载时检查 `core/file_workspace.py`、`storage/artifacts/`、`tools/data_profile_tool.py`、`tools/file_inspector_tool.py`、`api/routes_files.py`。
- 不要重新引入已删除旧路径：`rag.*`、`knowledge.*`、`memory.*`、`core.chains`、`core.config`、`core.planner`、`core.question_classifier`、`core.context_judge`、`core.tools`、`agent.registry`。
- 若未来迁移 `core/` 剩余文件，先做只读设计评估，再引入转发层，最后才移动真实文件。
- 做较大改动后至少运行 `python -m pytest`，并参考 `docs/guides/regression_checklist.md` 做手动回归。

## 常用排查

- Ollama 连接失败：检查 `models.ollama.url` 和 Ollama 服务。
- 嵌入失败：检查 `models.embedding_backend`、`models.embedding` 和 `/api/embed`。
- 知识库没有命中：检查 `data/` 文档、向量索引、文档指纹，并尝试 `/api/kb/rebuild`。
- 回答没有引用：检查 RAG 检索是否返回 `kb_chunks`，以及 `config/prompts.yaml` 的回答提示词。
- 证据支撑强度低：检查检索质量、来源数量、是否触发重规划和 `graph.answer_confidence.*`。
- 后台任务卡住：检查 `/api/tasks/{task_id}`、`agent_tasks` 表、取消标记和 Ollama 请求超时。
- 产物下载失败：检查 `agent_artifacts`、`workspace/artifacts/` 和 `/api/artifacts/{artifact_id}`。
- 数据分析失败：检查是否已上传文件、请求是否附带 `file_id`、扩展名是否在白名单内。
- 文件索引异常：检查 `workspace/files_index.json`，必要时先备份再修复。
- KG-RAG 没被调用：当前是预期行为，`kg_rag` capability 默认 disabled。
- 配置修改不生效：确认是否属于热更新字段；深层配置通常需要重新初始化 Agent 或重启应用。
- Phoenix 未启动：检查 `observability.enabled` 和 `utils/phoenix_monitor.py` 状态；失败通常不影响主问答。
