# GeoClaw-LS 项目信息

## 项目概览

GeoClaw-LS 是一个面向地质滑坡防治领域的本地智能助手。项目核心目标是把本地地质灾害资料构建为知识库，并结合 RAG（检索增强生成）、长期记忆、任务规划、工具调用、后台任务和上传文件分析，为用户提供中文专业问答、资料引用、计算、对话回顾、深度洞察和数据文件概览。

当前应用形态是 FastAPI + 原生 WebUI。主入口仍是 `app.py`，但 HTTP 路由已经拆分到 `api/` 目录。核心运行依赖本地 Ollama，后端会维护 SQLite 会话历史与任务记录、ChromaDB 向量索引、知识库文档指纹、文件工作区索引，以及可选 Phoenix 观测链路。

当前 Git 信息：

- 当前分支：`main`
- 远程仓库：`origin -> https://github.com/wwei-coder/GeoClaw-LS.git`
- `main` 跟踪 `origin/main`
- 当前工作区检查结果：`workspace/` 为未跟踪目录；开发时不要误删、清理或回滚本地运行数据。
- 本地存在 `.need_reset` 标记文件，它属于运行状态文件，不应作为源码手动改写。

## 技术栈

- 后端：FastAPI、Uvicorn、Pydantic、python-multipart。
- Agent 编排：LangGraph、自定义 Chain、Planner、标准化 Agent 任务/步骤状态、工具注册表。
- 后台任务：本地 `ThreadPoolExecutor` 串行执行，任务、步骤和产物持久化到 SQLite。
- RAG 检索：ChromaDB、向量检索、BM25、RRF 融合、关键词或模型重排序、检索质量评估、低质量重规划。
- 嵌入模型：当前配置使用 Ollama embedding，模型为 `qwen3-embedding:4b`。
- 生成模型：当前强制本地 Ollama，默认模型为 `qwen2.5:7b`。
- 文档解析：PyMuPDF 解析 PDF，python-docx 解析 Word，支持 `.pdf`、`.docx`、`.txt`。
- 数据文件分析：支持上传 `.csv`、`.xlsx`、`.xls`、`.txt`、`.json`，使用内置 Python 解析和 `openpyxl`。
- 前端：原生 HTML/CSS/JavaScript 静态 WebUI，无构建步骤。
- 观测：Arize Phoenix + OpenTelemetry，可通过 WebUI 开关控制。
- 存储：SQLite 保存会话历史和 Agent 任务，ChromaDB 保存知识库向量索引，JSON 保存文档指纹和文件工作区索引。

## 运行方式

推荐从项目根目录运行：

```powershell
python app.py
```

`app.py` 默认监听 `127.0.0.1`，优先使用端口 `18765`，如果端口被占用会向后扫描最多 120 个端口。启动成功后控制台会输出 WebUI 地址。

也可以使用 Uvicorn：

```powershell
uvicorn app:app --host 127.0.0.1 --port 18765
```

运行前需要确保：

- Python 依赖已安装：`pip install -r requirements.txt`
- Ollama 服务可访问。
- Ollama 中已准备好回复模型 `qwen2.5:7b`。
- Ollama 中已准备好嵌入模型 `qwen3-embedding:4b`。
- 当前默认访问地址：
  - LLM：`http://localhost:11434/api/generate`
  - Embedding：`http://localhost:11434/api/embed`

健康检查脚本：

```powershell
python utils\health_check.py
```

自动测试命令：

```powershell
python -m pytest
```

当前仓库已有 `tests/` 目录，覆盖 Agent 状态、计算器工具、配置辅助函数、文件工作区、Planner JSON 解析和 ToolResult 等基础行为。

## 主要目录与文件

- `app.py`：FastAPI 应用组装入口，负责生命周期、静态资源挂载、路由注册和端口选择；保留部分历史兼容导入。
- `api/`：FastAPI 路由层，当前拆分为 chat、sessions、files、tasks、kb、config、observability、health 等模块。
- `api/context.py`：API 共享上下文，包含 `RAGBridge`、请求模型、配置读写、序列化工具、可调配置过滤逻辑。
- `static/index.html`：WebUI 页面结构。
- `static/app.js`：前端状态管理、聊天请求、后台任务工作台、文件上传、执行过程展示、产物链接、会话操作、配置编辑和知识库控制台逻辑。
- `static/styles.css`：WebUI 样式。
- `config/config.yaml`：当前运行配置。
- `config/config.default.yaml`：默认配置模板。
- `config/prompts.yaml`：问答、检索改写、关键词扩展、审查、深度洞察、术语修正等提示词。
- `config/planner.yaml`：Planner 提示词，要求输出工具步骤 JSON，目前支持 `RAG`、`MEMORY`、`CALCULATOR`、`DISCOVERY`、`LLM`、`DATA_PROFILE`、`FILE_INSPECTOR`。
- `core/agent_core.py`：Agent 核心，整合数据库、任务存储、任务运行器、向量库、Chains、LangGraph、知识库同步、会话管理、术语修正、文件工作区和回答流程。
- `core/graph_agent.py`：LangGraph 工作流，包含 planner、decision、executor、solver、reviewer 节点，并支持取消信号、低质量检索重规划、回答可信度、执行轨迹和 artifacts。
- `core/chains.py`：SmallTalk、MemoryQuery、Planner、HeuristicDecision、Retriever、Synthesis 等链路实现。
- `core/tools.py`：兼容层工具注册表，包含旧工具函数和标准 `ToolResult` 协议适配。
- `core/file_workspace.py`：上传文件和分析产物工作区，负责白名单校验、安全文件名、索引读写和路径边界检查。
- `core/config.py`：集中读取 YAML 配置并导出运行常量。
- `core/planner.py`：调用 LLM 生成任务计划并解析 JSON。
- `core/question_classifier.py`：闲聊、记忆查询、复杂问题、追问识别。
- `core/context_judge.py`：判断当前问题与历史摘要的上下文相关性。
- `core/reset_handler.py`：系统重置标记和执行逻辑。
- `agent/state.py`：标准化 Agent 数据模型，包括 `AgentTask`、`AgentStep`、`AgentState`、`Artifact`。
- `agent/executor.py`：标准 Agent 执行器，按 Planner 步骤执行工具并生成执行状态。
- `agent/registry.py`：Agent 工具注册入口。
- `agent/task_store.py`：基于 SQLite 的任务、步骤和产物持久化存储。
- `agent/task_runner.py`：轻量后台任务运行器，支持提交、取消、重试、继续运行，并在启动时标记被中断任务。
- `tools/base.py`：标准工具协议，定义 `ToolInput`、`ToolResult`、`BaseTool`。
- `tools/registry.py`：标准工具注册中心，统一注册 `RAG`、`MEMORY`、`LLM`、`CALCULATOR`、`DISCOVERY`、`DATA_PROFILE`、`FILE_INSPECTOR`。
- `tools/data_profile_tool.py`：上传数据文件概览工具，生成统计摘要和 Markdown 报告产物。
- `tools/file_inspector_tool.py`：上传文件检查工具，返回基础信息和内容预览。
- `tools/calculator_tool.py`、`tools/rag_tool.py`、`tools/memory_tool.py`、`tools/llm_tool.py`、`tools/discovery_tool.py`：标准工具包装。
- `rag/`：RAG 相关 wrapper/re-export 目录，用于向新结构迁移，旧实现仍部分保留在 `knowledge/` 和 `memory/`。
- `knowledge/knowledge_loader.py`：加载 PDF、DOCX、TXT 文档。
- `knowledge/knowledge_chunker.py`：按章节/段落拆分文档，生成 parent-child 知识块并写入元数据。
- `memory/vector_store.py`：ChromaDB 向量库、Ollama embedding 客户端、BM25、RRF 融合、缓存、检索诊断和索引维护。
- `memory/rerank.py`：关键词或模型重排序策略。
- `memory/database_manager.py`：SQLite 会话和对话历史。
- `memory/summary_memory.py`：对话摘要和用户偏好抽取。
- `memory/doc_fingerprint.py`：知识库源文档指纹，用于增量同步。
- `utils/ollama_client.py`：Ollama/兼容 API 调用封装，支持同步、异步、流式、重试和本地兜底。
- `utils/phoenix_monitor.py`：Phoenix 观测后台启动、关闭、状态查询和 OpenTelemetry 导出。
- `utils/health_check.py`：健康检查脚本。
- `utils/tool_smoke_check.py`：工具冒烟检查脚本。
- `docs/`：Agent 化改造阶段说明、目标架构和回归检查清单。
- `tests/`：pytest 测试目录。

## 数据与生成物

知识库源文档位于 `data/`，当前有：

- `地质灾害人工智能大语言模型研究展望.pdf`
- `赣南滑坡知识.docx`
- `重大滑坡隐患分析方法综述_朱庆.pdf`

运行数据和生成物：

- `vector_db/`：ChromaDB 向量库持久化目录。
- `long_term_memory.db`：SQLite 会话、对话历史、Agent 任务、步骤和产物数据库。
- `doc_fingerprint.json`：记录 `data/` 中文档的大小和修改时间，用于判断新增、变更、删除。
- `logs/retrieval_metrics.jsonl`：检索指标日志。
- `workspace/uploads/`：用户上传的数据文件。
- `workspace/artifacts/`：数据分析报告等工具产物。
- `workspace/files_index.json`：上传文件和产物索引。
- `.pytest_cache/`、`.ruff_cache/`、`__pycache__/`：本地缓存目录。

这些运行数据通常不应当作为源代码手动编辑。若需要重建知识库，优先使用 WebUI 的知识库重建功能或调用 `/api/kb/rebuild`。

## API 概览

主要后端接口：

- `GET /`：返回 WebUI 首页。
- `GET /api/bootstrap`：初始化前端，返回会话列表、当前会话和历史消息。
- `POST /api/chat`：同步聊天问答入口，支持可选 `file_id` 和 `files`。
- `POST /api/tasks`：创建后台任务，当前支持 `run_mode=background`。
- `GET /api/tasks`：列出任务，可按 `session_id` 过滤。
- `GET /api/tasks/{task_id}`：获取任务详情、步骤、产物和进度。
- `POST /api/tasks/{task_id}/cancel`：请求取消后台任务。
- `POST /api/tasks/{task_id}/retry`：重试任务，可选指定步骤。
- `POST /api/tasks/{task_id}/resume`：继续已失败、取消或部分完成的任务。
- `GET /api/tasks/{task_id}/artifacts`：列出指定任务产物。
- `POST /api/files/upload`：上传 `.csv/.xlsx/.xls/.txt/.json` 数据文件，单文件上限 20MB。
- `GET /api/files`：列出已上传文件。
- `GET /api/artifacts`：列出任务产物。
- `GET /api/artifacts/{artifact_id}`：下载指定分析产物，兼容文件工作区产物和任务存储产物。
- `GET /api/sessions`：获取会话列表。
- `POST /api/sessions`：新建会话。
- `POST /api/sessions/{session_id}/switch`：切换会话。
- `PATCH /api/sessions/{session_id}`：重命名会话。
- `DELETE /api/sessions/{session_id}`：删除会话。
- `GET /api/config`：读取当前配置、默认配置和可编辑配置项。
- `PUT /api/config`：保存配置。
- `POST /api/config/reset`：恢复默认配置。
- `GET /api/config/export`：导出 YAML 配置。
- `POST /api/config/import`：导入 YAML 配置。
- `POST /api/kb/sync`：同步知识库。
- `GET /api/kb/status`：获取知识库状态。
- `GET /api/kb/documents`：获取文档索引状态。
- `GET /api/kb/diagnostics`：获取检索诊断信息。
- `POST /api/kb/rebuild`：强制重建知识库。
- `POST /api/system/reset`：触发系统重置并重新初始化 Agent。
- `GET /api/observability/status`：获取 Phoenix 观测链路状态。
- `POST /api/observability/toggle`：启用或关闭 Phoenix 观测链路，并写回配置。
- `GET /api/health`：返回应用根目录、配置路径和 Agent 导入状态。

`/api/chat` 响应保持兼容字段：

- `answer`
- `sources`
- `trace`
- `session_id`

同时可返回增强字段：

- `task_id`
- `execution_trace`
- `steps`
- `artifacts`

## Agent 工作流

同步问答流程：

1. `api/routes_chat.py` 的 `/api/chat` 接收问题，可附带当前会话、`file_id` 和上传文件信息。
2. `RAGBridge` 懒加载或复用单个 `AgentCore` 实例。
3. `AgentCore.chat_async()` 先处理闲聊、记忆查询和待确认工具调用。
4. 普通问题进入 `GraphAgent.run_async()`。
5. `GraphAgent` 依次执行：
   - `planner`：基于 `config/planner.yaml` 拆解工具步骤。
   - `decision`：结合上下文、问题类型、Planner 结果和文件意图决策是否强制使用 RAG、计算器或数据工具。
   - `executor`：通过 `agent/executor.py` 执行工具，更新 `AgentTask`、`AgentStep`、`ToolResult`、执行轨迹和产物。
   - `solver`：综合工具结果生成最终回答，并计算证据可信度。
   - `reviewer`：审核回答，不通过时可重新规划；审核临时失败时会降级放行。
6. `SynthesisChain` 会更新短期记忆、摘要记忆，并在达到阈值后压缩历史。
7. 对话最终写入 SQLite。

后台任务流程：

1. 前端任务工作台通过 `POST /api/tasks` 提交后台任务。
2. `TaskRunner` 在本地线程池中串行运行任务，并向 `TaskStore` 写入任务状态。
3. 前端轮询 `/api/tasks` 和 `/api/tasks/{task_id}` 展示任务列表、步骤、进度、回答摘要和产物。
4. 支持取消、重试、继续任务；应用重启后，之前处于 running 的任务会被标记为 `partial`。

可用工具：

- `RAG`：从知识库检索相关资料。
- `MEMORY`：读取摘要记忆、最近对话和短期记忆。
- `LLM`：直接调用本地模型。
- `CALCULATOR`：安全解析加减乘除表达式，不支持任意代码执行。
- `DISCOVERY`：扩大检索范围后用深度洞察提示词生成交叉分析和科学假设。
- `FILE_INSPECTOR`：检查上传文件信息和内容预览。
- `DATA_PROFILE`：对上传数据文件做统计概览，生成 Markdown 报告产物。

## RAG 与检索机制

知识库构建：

- `knowledge_loader` 从 `data/` 加载 `.pdf`、`.docx`、`.txt`。
- `knowledge_chunker` 先按章节/段落切分，再生成 parent-child 结构。
- chunk 元数据包含 `doc_name`、`parent_id`、`section_idx`、`type`、`active`，可从文档名或文本中提取年份。
- PDF 默认标记为 `report`，DOCX 默认标记为 `paper`，TXT/MD 默认标记为 `knowledge`。
- `AgentCore` 启动时会根据 `doc_fingerprint.json` 和向量库 collection 状态判断是否全量重建或增量同步。

检索：

- `VectorStore.search()` 支持 `hybrid`、`vector`、`bm25` 模式。
- 默认融合向量检索与 BM25，并用 RRF 合并结果。
- 支持预重排序约束、每文档 chunk 数限制、检索缓存和诊断信息。
- 当前配置启用检索缓存：TTL 900 秒，最大 512 条。
- 当前配置 `rag.rerank_strategy` 为 `keyword`，不是模型 reranker。
- `RetrieverChain` 会评估命中数、平均相似度和来源多样性；质量不足时可进行语义改写、关键词扩展和二次检索。
- 低质量检索可触发 GraphAgent 重新规划，最大次数由 `graph.replan_max_attempts` 控制。
- 检索指标写入 `logs/retrieval_metrics.jsonl`。

## 文件工作区与数据工具

文件工作区位于 `workspace/`：

- `workspace/uploads/` 保存上传文件。
- `workspace/artifacts/` 保存分析报告等产物。
- `workspace/files_index.json` 保存文件和产物元数据。

安全边界：

- 仅允许 `.csv/.xlsx/.xls/.txt/.json`。
- 单文件上限 20MB。
- 上传文件名会安全化处理。
- 文件读取限定在 `workspace/uploads/`。
- 产物下载限定在 `workspace/artifacts/`。
- 不执行用户上传代码，不执行 Excel 宏，JSON 只做数据解析。

数据工具行为：

- `FILE_INSPECTOR`：返回 file_id、扩展名、大小和内容预览。
- `DATA_PROFILE`：支持 CSV、Excel 首个 sheet、JSON 和 TXT；输出行列规模、字段摘要、缺失率、数值统计、类别高频值、重复行和简单异常提示；同时生成 `data_profile_<file_id>.md` 报告。

## 当前关键配置

当前 `config/config.yaml` 中的重要设置：

- `agent.max_context_len: 16000`
- `agent.max_history_rounds: 8`
- `models.provider: ollama`
- `models.ollama.model: qwen2.5:7b`
- `models.ollama.temperature: 0.7`
- `models.embedding_backend: ollama`
- `models.embedding: qwen3-embedding:4b`
- `models.embedding_ollama_batch_size: 16`
- `rag.search_top_k: 3`
- `rag.expansion_top_k: 4`
- `rag.rerank_strategy: keyword`
- `rag.quality_threshold: 0.45`
- `graph.replan_max_attempts: 2`
- `graph.replan_on_low_quality: true`
- `graph.replan_low_quality_threshold: 0.3`
- `graph.replan_require_expansion: true`
- `graph.step_result_max_chars: 9000`
- `retrieval.fast_path.enabled: true`
- `kb_watcher.enabled: true`
- `observability.enabled: false`

重要注意：

- 虽然配置文件和 WebUI 中保留了 `models.api.*` 远程 API 字段，但 `core/config.py` 当前写死 `LLM_PROVIDER = "ollama"`，并清空 API 配置。因此实际运行是本地 Ollama-only 模式。
- 如果要启用 OpenAI-compatible API，不能只改 YAML，还需要修改 `core/config.py` 中的本地强制逻辑。
- WebUI 配置页会隐藏部分高级配置，隐藏逻辑在 `api/context.py` 的 `HIDDEN_PREFIXES`。
- `api/routes_config.py` 保存配置后只会即时更新部分运行态字段，例如温度；更深层配置变更可能需要重新初始化 Agent 或重启应用。

## 提示词与专业边界

项目主要提示词位于 `config/prompts.yaml` 和 `config/planner.yaml`。回答要求偏专业、中文、引用资料来源，并明确区分资料支持和资料未提及内容。

特别注意 InSAR 术语：

- 项目配置要求 InSAR 必须解释为“干涉合成孔径雷达（Interferometric Synthetic Aperture Radar）”。
- 禁止误写为热红外、光学、多光谱、地物成像等无关技术。
- `AgentCore` 和相关提示词有术语修正逻辑，回答后可能会二次修正。

## 前端功能

WebUI 提供：

- 新建、搜索、切换、重命名、删除会话。
- 同步发送问题并展示回答、来源和状态。
- 创建后台任务，并在任务工作台展示最近任务、任务详情、步骤状态、进度、产物、取消、重试和继续操作。
- 上传数据文件，并在数据分析提问时自动附带最近 `file_id`。
- 显示 Agent 执行过程、步骤状态和工具产物下载链接。
- 在线编辑部分配置项，支持导入、导出、恢复默认配置。
- 知识库控制台：查看文档索引、同步和重建。
- Phoenix 观测链路开关。
- 系统重置入口。

前端是原生 JavaScript，没有构建步骤。

## 文档与测试

`docs/` 当前包含：

- `agent_refactor_phase1.md`
- `agent_refactor_phase2.md`
- `agent_refactor_phase3.md`
- `agent_refactor_phase4.md`
- `agent_refactor_phase5.md`
- `architecture_target.md`
- `regression_checklist.md`

`docs/regression_checklist.md` 给出了最小手动回归项，包括 WebUI 启动、健康检查、会话管理、知识库问答、文件上传、DATA_PROFILE、任务工作台、配置导入导出、知识库同步/重建和 Phoenix 开关。

自动测试：

- 使用 `python -m pytest`。
- 当前测试文件包括 `test_agent_state.py`、`test_calculator_tool.py`、`test_config_helpers.py`、`test_file_workspace.py`、`test_planner_parse.py`、`test_tool_result.py`。

## 版本控制与忽略规则

仓库已设置 `.gitignore`，用于排除本地运行产物和敏感配置。当前应避免纳入版本控制的内容包括：

- Python 缓存：`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`
- 虚拟环境：`.venv/`、`venv/`、`env/`
- IDE 和系统文件：`.idea/`、`.vscode/`、`.DS_Store`、`Thumbs.db`
- 运行日志：`logs/`、`*.log`
- 本地数据库：`*.db`、`*.sqlite`、`*.sqlite3`
- 向量索引：`vector_db/`、`chroma/`
- 文档指纹：`doc_fingerprint.json`
- 系统重置标记：`.need_reset`
- 本地模型和缓存：`models/`、`.cache/`
- 环境变量和密钥：`.env`、`.env.*`
- 临时文件和构建产物：`tmp/`、`temp/`、`build/`、`dist/`、`*.egg-info/`
- 上传文件和分析产物：`workspace/uploads/`、`workspace/artifacts/`

注意：

- `workspace/files_index.json` 当前没有被忽略，开发时要谨慎处理；如果只记录本地上传状态，后续可以考虑加入 `.gitignore`。
- `workspace/` 下还可能存在测试上传样例或临时 CSV，这些是本地运行数据，不应在无明确要求时清理。
- `data/` 当前未被忽略，表示知识库源文档会随项目版本化。如果后续文档体积变大或涉及非公开资料，应改用 Git LFS、对象存储或在 `.gitignore` 中排除 `data/`，并用 README/脚本说明数据获取方式。

## 开发注意事项

- 不要随意删除或改写 `data/`、`vector_db/`、`long_term_memory.db`、`doc_fingerprint.json`、`workspace/uploads/`、`workspace/artifacts/`，除非任务明确要求重建、重置或清理数据。
- 当前工作区存在本地运行数据，执行 Git 操作时不要使用 `git reset --hard` 或回滚未明确要求的文件。
- 修改配置时优先考虑 `config/config.yaml` 和 `config/config.default.yaml` 是否需要同步。
- 修改提示词时优先改 YAML；`core/prompts.py` 会从配置中读取提示词常量。
- 修改 API 时重点检查 `api/` 对应路由和 `api/context.py` 的共享模型/序列化逻辑。
- 修改 Planner 工具范围时同步检查 `config/planner.yaml`、`core/tools.py`、`agent/registry.py`、`tools/registry.py` 和 `core/graph_agent.py`。
- 修改工具协议时优先保持 `ToolInput`、`ToolResult`、`BaseTool` 的兼容性，并同步测试。
- 修改后台任务时重点检查 `agent/task_runner.py`、`agent/task_store.py`、`core/graph_agent.py`、`static/app.js` 和 `/api/tasks` 路由。
- 修改检索逻辑时重点检查 `memory/vector_store.py`、`memory/rerank.py`、`rag/` 和 `core/chains.py` 的 `RetrieverChain`。
- 修改 Agent 流程时重点检查 `core/graph_agent.py`、`core/agent_core.py`、`agent/executor.py` 和 `agent/state.py`。
- 修改模型调用时重点检查 `utils/ollama_client.py` 和 `core/config.py`。
- 修改文件上传或产物下载时重点检查 `core/file_workspace.py`、`tools/data_profile_tool.py`、`tools/file_inspector_tool.py`、`api/routes_files.py` 和 `app.py` 路由注册。
- `api/context.py` 中 `RAGBridge` 使用线程锁复用单个 Agent 实例，改并发逻辑时要注意线程安全。
- SQLite 连接使用 `check_same_thread=False`，数据库操作由 `DatabaseManager` 内部锁保护；`TaskStore` 也复用该锁。
- `VectorStore` 内部有检索缓存、BM25 缓存和 collection 版本，改索引更新逻辑时要同步失效缓存。
- 做较大改动后至少运行 `python -m pytest`，并参考 `docs/regression_checklist.md` 手动验证 WebUI 的聊天、后台任务、知识库状态、配置保存、文件上传和数据分析。

## 常用排查

- Ollama 连接失败：检查 `models.ollama.url`，并确认 Ollama 服务已启动。
- 嵌入失败：检查 `models.embedding_backend`、`models.embedding` 和 `/api/embed` 是否可用。
- 知识库没有命中：检查 `data/` 文档、`doc_fingerprint.json`、`vector_db/`，并尝试 `/api/kb/rebuild`。
- 回答没有引用：检查 `RetrieverChain` 是否返回 `kb_chunks`，以及 `config/prompts.yaml` 的 `final_answer` 提示词。
- 后台任务卡住：检查 `/api/tasks/{task_id}` 状态、`agent_tasks` 表记录、取消标记，以及 Ollama 请求是否超时。
- 任务产物下载失败：检查 `agent_artifacts` 记录、产物路径是否在 `workspace/artifacts/` 内，以及 `/api/artifacts/{artifact_id}` 是否能解析到文件。
- 数据文件分析失败：检查是否已上传文件、请求是否附带 `file_id`、文件扩展名是否在白名单内、Excel 是否可由 `openpyxl` 读取。
- 文件工作区索引异常：检查 `workspace/files_index.json` 是否存在不完整条目，必要时先备份再修复。
- 配置 UI 不显示某些参数：`api/context.py` 中 `HIDDEN_PREFIXES` 会隐藏一部分高级配置。
- 配置修改不生效：确认是否属于运行时可热更新字段；模型、embedding、检索索引等深层配置通常需要重新初始化 Agent 或重启应用。
- Phoenix 未启动：检查 `observability.enabled`、`utils/phoenix_monitor.py` 状态和端口；失败通常只影响观测，不影响主问答。
