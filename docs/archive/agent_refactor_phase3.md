# GeoClaw-LS Agent 化改造（Phase 3）

## 本阶段新增能力
- 引入数据文件工作区：`workspace/uploads/` 与 `workspace/artifacts/`。
- 新增上传与文件查询 API，支持 CSV/Excel/TXT/JSON。
- 新增数据工具：
  - `DATA_PROFILE`：数据概览、缺失统计、数值统计、异常提示。
  - `FILE_INSPECTOR`：文件信息与内容预览。
- `DATA_PROFILE` 会生成 Markdown 报告 Artifact，并可下载。

## 文件工作区说明
- `workspace/uploads/`：用户上传文件存储目录。
- `workspace/artifacts/`：分析报告等产物目录。
- `workspace/files_index.json`：上传文件与产物元数据索引。
- 安全边界：
  - 仅允许白名单扩展名。
  - 文件名会安全化处理。
  - 访问路径限制在工作区目录内，禁止任意路径穿越。

## 上传 API
- `POST /api/files/upload`
  - 表单字段：`file`
  - 允许扩展名：`.csv/.xlsx/.xls/.txt/.json`
  - 单文件上限：20MB
  - 返回：`file_id/original_name/saved_name/relative_path/size/extension/uploaded_at`
- `GET /api/files`
  - 返回已上传文件列表
- `GET /api/artifacts/{artifact_id}`
  - 下载指定分析产物

## 新工具行为
- `FILE_INSPECTOR`
  - 输入：包含 `file_id` 的指令（或使用当前会话最近 `file_id`）
  - 输出：文件基础信息、类型、大小与内容预览
- `DATA_PROFILE`
  - 支持 CSV / Excel（首个 sheet）/ JSON / TXT
  - 表格输出：行列规模、字段统计、缺失率、数值列统计、类别列高频值、重复行、简单异常提示
  - 文本输出：字符数、行数、前几行与高频词
  - 生成报告：`data_profile_<file_id>.md`

## /api/chat 扩展
- 请求新增可选字段：
  - `file_id`
  - `files`
- 响应保持兼容并继续返回：
  - `answer/sources/trace/session_id`
- 响应可选增强字段继续可用：
  - `task_id/execution_trace/steps/artifacts`

## GraphAgent 兼容策略
- 保留原有工具与流程不变（RAG/MEMORY/LLM/CALCULATOR/DISCOVERY）。
- 在明确文件分析意图且存在 `file_id` 时，决策层可轻量补充 `FILE_INSPECTOR -> DATA_PROFILE`。
- 普通知识库问答不强制触发数据工具。

## 前端最小增强
- 聊天输入区新增“上传数据”按钮。
- 上传成功后展示 `file_id` 提示。
- 用户提问“分析这个文件”等数据分析意图时，前端自动附带最近 `file_id`。
- 若响应包含 `artifacts`，消息区显示下载链接。

## 安全边界
- 不执行用户代码，不开放任意 Python Sandbox。
- 不执行 Excel 宏/脚本，仅读取单元格值。
- JSON 仅解析数据，不执行表达式。
- 文件读取限定在 `workspace/uploads/`；产物下载限定在 `workspace/artifacts/`。

## 第四阶段建议
- 增强统计分析与图表产物（趋势图、分布图）。
- 任务持久化与可回放执行历史。
- 增加多文件关联分析与轻量工作台视图。
