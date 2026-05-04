const state = {
  sessions: [],
  currentSessionId: null,
  settingsItems: [],
  settingsData: {},
  defaultsData: {},
  configEffective: {},
  configMetadata: {},
  configCategories: [],
  selectedCategory: "",
  selectedPath: "",
  settingsDirty: false,
  kbDocs: [],
  kbSelectedDocName: "",
  observabilityEnabled: false,
  observabilityBusy: false,
  latestUpload: null,
  tasks: [],
  currentTaskId: "",
  currentTaskDetail: null,
  taskDetailLoading: false,
  taskPanelHtml: "",
  taskDetailHtml: "",
};
let pageScrollLockCount = 0;
let isAsking = false;
let activeChatController = null;
let activePendingBubble = null;
let taskPollTimer = null;
const PATH_SEGMENT_LABELS = {
  common: "常用设置",
  llm: "语言模型",
  model: "模型名称",
  provider: "服务商",
  api: "接口配置",
  key: "密钥",
  endpoint: "地址",
  base_url: "基础地址",
  embedding: "向量模型",
  embedding_backend: "向量后端",
  embedding_ollama_batch_size: "向量批处理大小",
  embedding_ollama_timeout: "向量请求超时",
  embedding_ollama_url: "向量服务地址",
  rerank: "重排模型",
  rerank_strategy: "重排策略",
  retrieval: "检索参数",
  retriever: "检索器",
  memory: "记忆管理",
  planner: "规划器",
  agent: "智能体",
  graph: "流程编排",
  kb_watcher: "知识库监测",
  keywords: "关键词规则",
  models: "模型设置",
  rag: "知识检索",
  synthesis: "回答生成",
  tool: "工具策略",
  vector_search: "向量检索",
  fast_path: "快速通道",
  pre_rerank: "预重排",
  cache: "缓存配置",
  ollama: "本地模型服务",
  system: "系统参数",
  logging: "日志设置",
  observability: "观测链路",
  timeout: "超时时间",
  temperature: "创造性",
  top_p: "采样范围",
  max_tokens: "最大输出",
  max_context_len: "上下文上限",
  max_history_rounds: "历史轮数上限",
  replan_low_quality_threshold: "低质量重规划阈值",
  replan_max_attempts: "重规划最大次数",
  replan_on_low_quality: "低质量触发重规划",
  replan_require_expansion: "重规划前要求扩展检索",
  step_result_max_chars: "步骤结果长度上限",
  enabled: "启用开关",
  notify_no_change: "无变更提示",
  poll_interval_seconds: "轮询间隔（秒）",
  settle_seconds: "稳定等待（秒）",
  analysis: "分析类词表",
  complex: "复杂问题词表",
  complex_calc: "复杂计算词表",
  math: "数学词表",
  memory_query: "记忆查询词表",
  small_talk: "闲聊词表",
  small_talk_punctuation: "闲聊标点词表",
  stream_timeout: "流式超时",
  url: "服务地址",
  batch_size: "批处理大小",
  expansion_min_improvement: "扩展检索最小提升",
  expansion_top_k: "扩展召回数量",
  max_chunk_length: "分块长度上限",
  quality_min_hits: "质量评估最少命中",
  quality_min_similarity: "质量评估最低相似度",
  quality_min_source_diversity: "质量评估来源多样性",
  quality_threshold: "质量阈值",
  search_top_k: "主检索召回数量",
  vector_collection_name: "向量集合名称",
  quality_margin: "质量边际",
  skip_for_complex_questions: "复杂问题跳过快速通道",
  max_evidence_chars: "证据长度上限",
  calculator_max_expression_len: "计算表达式长度上限",
  discovery_top_k: "深度洞察召回数量",
  rag_top_k: "RAG 工具召回数量",
  max_size: "缓存容量上限",
  ttl_seconds: "缓存有效期（秒）",
  candidate_multiplier: "候选扩展倍数",
  max_chunks_per_doc: "单文档最大分块数",
  max_workers: "并行任务数",
  max_per_doc: "单文档预重排上限",
  min_section_coverage: "最小章节覆盖率",
  rrf_k: "RRF 融合系数",
  chunk_size: "分块大小",
  chunk_overlap: "分块重叠",
  enable: "启用开关",
  path: "路径",
  host: "主机",
  port: "端口",
};
const TYPE_LABELS = {
  bool: "开关（是/否）",
  int: "整数",
  float: "小数",
  list: "列表",
  dict: "对象",
  str: "文本",
  string: "文本",
};

function qs(id) {
  return document.getElementById(id);
}

function setupMenu(toggleId, wrapId) {
  const toggle = qs(toggleId);
  const wrap = qs(wrapId);
  if (!toggle || !wrap) return;

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    wrap.classList.toggle("open");
  });

  wrap.addEventListener("click", (e) => {
    if (e.target.closest(".menu-item")) {
      wrap.classList.remove("open");
    }
  });

  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target)) {
      wrap.classList.remove("open");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      wrap.classList.remove("open");
    }
  });
}

function lockPageScroll() {
  pageScrollLockCount += 1;
  document.body.classList.add("scroll-locked");
}

function unlockPageScroll() {
  pageScrollLockCount = Math.max(0, pageScrollLockCount - 1);
  if (pageScrollLockCount === 0) {
    document.body.classList.remove("scroll-locked");
  }
}

function openDialog(options = {}) {
  const {
    title = "提示",
    message = "",
    input = false,
    defaultValue = "",
    okText = "确定",
    cancelText = "取消",
    showCancel = true,
  } = options;

  return new Promise((resolve) => {
    const mask = qs("dialogMask");
    const titleEl = qs("dialogTitle");
    const msgEl = qs("dialogMessage");
    const inputEl = qs("dialogInput");
    const okBtn = qs("dialogOkBtn");
    const cancelBtn = qs("dialogCancelBtn");

    titleEl.textContent = title;
    msgEl.textContent = String(message ?? "");
    okBtn.textContent = okText;
    cancelBtn.textContent = cancelText;
    cancelBtn.classList.toggle("hidden", !showCancel);

    if (input) {
      inputEl.classList.remove("hidden");
      inputEl.value = String(defaultValue ?? "");
    } else {
      inputEl.classList.add("hidden");
      inputEl.value = "";
    }

    lockPageScroll();
    mask.classList.remove("hidden");

    const cleanup = () => {
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      mask.removeEventListener("click", onMaskClick);
      document.removeEventListener("keydown", onKeyDown);
      mask.classList.add("hidden");
      unlockPageScroll();
    };

    const onOk = () => {
      const value = input ? inputEl.value : true;
      cleanup();
      resolve({ ok: true, value });
    };
    const onCancel = () => {
      cleanup();
      resolve({ ok: false, value: null });
    };
    const onMaskClick = (e) => {
      if (e.target === mask) onCancel();
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        onCancel();
      } else if (e.key === "Enter" && (document.activeElement === inputEl || !input)) {
        onOk();
      }
    };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    mask.addEventListener("click", onMaskClick);
    document.addEventListener("keydown", onKeyDown);

    if (input) inputEl.focus();
    else okBtn.focus();
  });
}

async function uiConfirm(message, title = "请确认") {
  const result = await openDialog({ title, message, showCancel: true });
  return result.ok;
}

async function uiPrompt(message, defaultValue = "", title = "请输入") {
  const result = await openDialog({
    title,
    message,
    input: true,
    defaultValue,
    okText: "确定",
    cancelText: "取消",
    showCancel: true,
  });
  if (!result.ok) return null;
  return String(result.value ?? "");
}

async function uiAlert(message, title = "提示") {
  await openDialog({
    title,
    message,
    showCancel: false,
    okText: "我知道了",
  });
}

function closeUiAfterReset() {
  // 浏览器可能阻止直接关闭当前页，因此提供兜底降级为跳转空白页。
  window.open("", "_self");
  window.close();
  setTimeout(() => {
    if (!window.closed) {
      window.location.replace("about:blank");
    }
  }, 120);
}

async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `请求失败: ${res.status}`);
  }
  const type = res.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

function setStatus(text) {
  qs("statusText").textContent = text;
}

function renderObservabilityButton() {
  const btn = qs("openObservabilityBtn");
  if (!btn) return;
  const enabled = !!state.observabilityEnabled;
  btn.textContent = state.observabilityBusy
    ? `观测：${enabled ? "开" : "关"}（切换中）`
    : `观测：${enabled ? "开" : "关"}`;
  btn.classList.toggle("btn-green", enabled);
  btn.classList.toggle("btn-outline", !enabled);
  btn.disabled = !!state.observabilityBusy;
  btn.title = enabled ? "点击关闭观测链路以减少运行开销" : "点击开启观测链路用于追踪";
}

function applyObservabilityPayload(data) {
  const enabled = !!(data && data.enabled);
  state.observabilityEnabled = enabled;
  renderObservabilityButton();
}

async function loadObservabilityStatus() {
  try {
    const data = await api("/api/observability/status");
    applyObservabilityPayload(data);
  } catch (_err) {
    state.observabilityEnabled = false;
    renderObservabilityButton();
  }
}

async function toggleObservability() {
  if (state.observabilityBusy) return;
  const targetEnabled = !state.observabilityEnabled;
  const confirmText = targetEnabled
    ? "开启观测会增加少量运行开销，确定开启吗？"
    : "关闭观测可减少运行开销，确定关闭吗？";
  const confirmTitle = targetEnabled ? "开启观测链路" : "关闭观测链路";
  if (!(await uiConfirm(confirmText, confirmTitle))) return;

  state.observabilityBusy = true;
  renderObservabilityButton();
  setStatus(targetEnabled ? "正在开启观测链路..." : "正在关闭观测链路...");
  try {
    const data = await api("/api/observability/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: targetEnabled }),
    });
    applyObservabilityPayload(data);
    if (targetEnabled && data && data.status && data.status.url) {
      window.open(data.status.url, "_blank", "noopener");
    }
  } catch (err) {
    await uiAlert(`观测链路切换失败: ${err.message}`, "操作失败");
  } finally {
    state.observabilityBusy = false;
    renderObservabilityButton();
    setStatus("就绪");
  }
}

function updateSendButtonState() {
  const btn = qs("sendBtn");
  if (!btn) return;
  if (isAsking) {
    btn.textContent = "停止";
    btn.classList.remove("btn-green");
    btn.classList.add("btn-outline", "danger");
    btn.title = "停止当前回答";
    return;
  }
  btn.textContent = "发送";
  btn.classList.remove("btn-outline", "danger");
  btn.classList.add("btn-green");
  btn.title = "发送问题";
}

function stopAnswering() {
  if (!isAsking || !activeChatController) return;
  activeChatController.abort();
  setStatus("已停止");
  if (activePendingBubble) {
    activePendingBubble.textContent = "已停止本次回答。";
  }
}

function asPrettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (_err) {
    return String(value ?? "");
  }
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(text) {
  return escapeHtml(String(text ?? ""))
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeSegment(segment = "") {
  return String(segment || "").trim().toLowerCase();
}

function toReadableLabel(raw = "") {
  const segment = normalizeSegment(raw);
  if (!segment) return "";
  if (PATH_SEGMENT_LABELS[segment]) return PATH_SEGMENT_LABELS[segment];
  const cleaned = segment.replaceAll("_", " ");
  return cleaned.replace(/\b[a-z]/g, (ch) => ch.toUpperCase());
}

function getDisplayName(item) {
  if (!item) return "";
  if (item.metadata && item.metadata.label) return item.metadata.label;
  if (item.hint && item.hint.title) return String(item.hint.title).replace(/^作用：/, "");
  const parts = item.path.split(".");
  const tail = parts[parts.length - 1] || "";
  return toReadableLabel(tail) || tail;
}

function getItemMeta(item) {
  if (!item) return {};
  if (item.metadata) return item.metadata;
  const byPath = (state.configMetadata && state.configMetadata.by_path) || {};
  return byPath[item.path] || {};
}

function stringifyValue(value) {
  if (typeof value === "object" && value !== null) {
    try {
      return JSON.stringify(value);
    } catch (_err) {
      return String(value);
    }
  }
  return String(value ?? "");
}

function formatFileSize(size) {
  const n = Number(size) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDocStatus(status) {
  const key = String(status || "").toLowerCase();
  if (key === "synced") return "已同步";
  if (key === "updated") return "已更新";
  if (key === "added") return "已新增";
  if (key === "removed") return "已删除";
  if (!key || key === "unknown") return "未知";
  return key;
}

function getSelectedKbDoc() {
  const name = String(state.kbSelectedDocName || "");
  if (!name) return null;
  return state.kbDocs.find((d) => String(d.name || "") === name) || null;
}

function renderKbGraphPanel() {
  const titleEl = qs("kbGraphTitle");
  const canvasEl = qs("kbGraphCanvas");
  const noteEl = qs("kbGraphNote");
  const actionBtn = qs("kbGraphActionBtn");
  if (!titleEl || !canvasEl || !noteEl || !actionBtn) return;

  const selected = getSelectedKbDoc();
  if (!selected) {
    titleEl.textContent = "知识图谱";
    canvasEl.textContent = "请先在左侧选择一篇文档";
    noteEl.textContent = "当前为按文档切换图谱视图（占位模式），后续可接入实体关系图。";
    actionBtn.textContent = "图谱构建中";
    return;
  }

  const docName = String(selected.name || "未命名文档");
  const chunkCount = Number(selected.indexed_chunks ?? 0);
  const status = formatDocStatus(selected.fingerprint_status);
  titleEl.textContent = `${docName} · 知识图谱`;
  canvasEl.textContent = `《${docName}》图谱预览区（待接入）`;
  noteEl.textContent = `当前文档：${docName}；分块：${chunkCount}；状态：${status}。`;
  actionBtn.textContent = "该文档图谱";
}

function renderKbDocsContent() {
  const el = qs("kbDocsContent");
  if (!el) return;
  if (!state.kbDocs.length) {
    state.kbSelectedDocName = "";
    renderKbGraphPanel();
    el.innerHTML = `<div class="kb-doc-empty">暂无文档索引信息</div>`;
    return;
  }
  const selectedName = String(state.kbSelectedDocName || "");
  el.innerHTML = `
    <div class="kb-doc-list">
      ${state.kbDocs
        .map((d) => {
          const name = escapeHtml(d.name || "未命名文档");
          const rawName = String(d.name || "");
          const chunks = Number(d.indexed_chunks ?? 0);
          const status = formatDocStatus(d.fingerprint_status);
          const sizeText = formatFileSize(d.size);
          const active = rawName === selectedName ? " active" : "";
          return `
            <div class="kb-doc-item${active}" data-doc-name="${escapeAttr(rawName)}">
              <div class="kb-doc-name" title="${name}">${name}</div>
              <div class="kb-doc-meta">
                <span>分块：${chunks}</span>
                <span>状态：${status}</span>
                <span>大小：${sizeText}</span>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
  renderKbGraphPanel();
}


function renderBubble(text, role = "assistant") {
  const chat = qs("chatArea");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.innerHTML = escapeHtml(text);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function formatStepStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "success") return "成功";
  if (s === "failed") return "失败";
  if (s === "running") return "执行中";
  if (s === "skipped") return "跳过";
  return "待执行";
}

function formatTaskStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "success") return "成功";
  if (s === "partial") return "部分成功";
  if (s === "failed") return "失败";
  if (s === "running") return "执行中";
  if (s === "canceled") return "已取消";
  return "待执行";
}

function formatProgress(progress) {
  const p = progress && typeof progress.percent === "number" ? progress.percent : 0;
  return `${Math.max(0, Math.min(100, Math.round(p)))}%`;
}

function renderExecutionPanel(data, anchorBubble) {
  const chat = qs("chatArea");
  if (!chat || !anchorBubble) return;
  const trace = Array.isArray(data.execution_trace) ? data.execution_trace : [];
  const steps = Array.isArray(data.steps) ? data.steps : [];
  if (!trace.length && !steps.length) return;

  const panel = document.createElement("div");
  panel.className = "execution-panel";
  const title = document.createElement("div");
  title.className = "execution-title";
  title.textContent = `执行过程（${steps.length || trace.length} 步）`;
  panel.appendChild(title);

  const list = document.createElement("ul");
  list.className = "execution-list";
  const sourceItems = steps.length ? steps : trace;
  sourceItems.forEach((item, idx) => {
    const li = document.createElement("li");
    const toolName = item.tool_name || item.tool || "UNKNOWN";
    const instruction = item.instruction || item.task || "";
    const statusText = formatStepStatus(item.status);
    const errorText = item.error ? `：${item.error}` : "";
    li.textContent = `${idx + 1}. ${toolName} ${statusText}${instruction ? ` - ${instruction}` : ""}${errorText}`;
    list.appendChild(li);
  });
  panel.appendChild(list);

  chat.appendChild(panel);
  chat.scrollTop = chat.scrollHeight;
}

function renderArtifacts(data) {
  const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
  if (!artifacts.length) return;
  const links = artifacts
    .map((a) => {
      const name = escapeHtml(a.name || a.id || "分析产物");
      const url = a.url || (a.id ? `/api/artifacts/${encodeURIComponent(a.id)}` : "");
      if (!url) return "";
      return `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${name}</a>`;
    })
    .filter(Boolean);
  if (!links.length) return;
  renderBubble(`分析产物：${links.join("，")}`, "system");
}

function renderTaskPanel() {
  const listEl = qs("taskList");
  if (!listEl) return;
  const tasks = Array.isArray(state.tasks) ? state.tasks : [];
  const nextHtml = !tasks.length
    ? `<div class="task-empty">暂无任务</div>`
    : tasks
        .map((t) => {
          const id = String(t.id || "");
          const active = id && id === state.currentTaskId ? " active" : "";
          const q = escapeHtml(String(t.user_query || "未命名任务"));
          const status = escapeHtml(formatTaskStatus(t.status));
          return `<button class="task-item${active}" data-task-id="${escapeAttr(id)}" title="${q}"><span class="task-item-q">${q}</span><span class="task-item-status">${status}</span></button>`;
        })
        .join("");
  if (state.taskPanelHtml === nextHtml) {
    return;
  }
  const workbenchEl = qs("taskWorkbench");
  const workbenchScrollTop = workbenchEl ? workbenchEl.scrollTop : 0;
  listEl.innerHTML = nextHtml;
  state.taskPanelHtml = nextHtml;
  if (workbenchEl) workbenchEl.scrollTop = workbenchScrollTop;
}

function renderTaskDetail() {
  const detailEl = qs("taskDetail");
  if (!detailEl) return;
  let nextHtml = "";
  if (state.taskDetailLoading) {
    nextHtml = `<div class="task-empty">任务详情加载中...</div>`;
  } else {
    const detail = state.currentTaskDetail;
    if (!detail || !detail.task) {
      nextHtml = "暂无任务";
    } else {
      const task = detail.task || {};
      const steps = Array.isArray(detail.steps) ? detail.steps : [];
      const artifacts = Array.isArray(detail.artifacts) ? detail.artifacts : [];
      const progress = detail.progress || {};
      const isRunning = !!detail.is_running;
      const cancelRequested = !!detail.cancel_requested;
      const statusRaw = String(task.status || "").toLowerCase();
      const answerPreview = escapeHtml(String(task.answer_preview || ""));
      const stepsHtml = steps.length
        ? `<ul>${steps
            .map((s, i) => {
              const tool = escapeHtml(String(s.tool_name || s.tool || "UNKNOWN"));
              const status = escapeHtml(formatStepStatus(s.status));
              const instruction = escapeHtml(String(s.instruction || s.task || ""));
              return `<li>${i + 1}. ${tool} ${status}${instruction ? ` - ${instruction}` : ""}</li>`;
            })
            .join("")}</ul>`
        : `<div class="task-empty">暂无步骤</div>`;
      const artifactsHtml = artifacts.length
        ? `<ul>${artifacts
            .map((a) => {
              const name = escapeHtml(String(a.name || a.id || "产物"));
              const type = escapeHtml(String(a.type || a.kind || "unknown"));
              const url = a.download_url || a.url || (a.id ? `/api/artifacts/${encodeURIComponent(a.id)}` : "");
              const link = url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">下载</a>` : "";
              return `<li>${name}（${type}）${link ? ` - ${link}` : ""}</li>`;
            })
            .join("")}</ul>`
        : `<div class="task-empty">暂无产物</div>`;
      const actions = [];
      if (isRunning) {
        actions.push(`<button class="btn btn-outline small" data-task-action="cancel" data-task-id="${escapeAttr(String(task.id || ""))}" ${cancelRequested ? "disabled" : ""}>${cancelRequested ? "取消中" : "取消任务"}</button>`);
      }
      if (statusRaw === "failed" || statusRaw === "partial") {
        actions.push(`<button class="btn btn-outline small" data-task-action="retry" data-task-id="${escapeAttr(String(task.id || ""))}">重试任务</button>`);
      }
      if (statusRaw === "canceled" || statusRaw === "partial" || statusRaw === "failed") {
        actions.push(`<button class="btn btn-outline small" data-task-action="resume" data-task-id="${escapeAttr(String(task.id || ""))}">继续任务</button>`);
      }
      nextHtml = `
    <div class="task-detail-block"><strong>问题：</strong>${escapeHtml(String(task.user_query || ""))}</div>
    <div class="task-detail-block"><strong>状态：</strong>${escapeHtml(formatTaskStatus(task.status))}</div>
    <div class="task-detail-block"><strong>进度：</strong>${escapeHtml(formatProgress(progress))}</div>
    <div class="task-detail-block"><strong>回答摘要：</strong>${answerPreview || "暂无"}</div>
    <div class="task-detail-block task-detail-actions">${actions.join(" ") || "暂无可用操作"}</div>
    <div class="task-detail-block"><strong>步骤：</strong>${stepsHtml}</div>
    <div class="task-detail-block"><strong>产物：</strong>${artifactsHtml}</div>
  `;
    }
  }
  if (state.taskDetailHtml === nextHtml) {
    return;
  }
  const workbenchEl = qs("taskWorkbench");
  const workbenchScrollTop = workbenchEl ? workbenchEl.scrollTop : 0;
  detailEl.innerHTML = nextHtml;
  state.taskDetailHtml = nextHtml;
  if (workbenchEl) workbenchEl.scrollTop = workbenchScrollTop;
}

async function fetchTasks() {
  if (!state.currentSessionId) return;
  const data = await api(`/api/tasks?session_id=${encodeURIComponent(state.currentSessionId)}&limit=30`);
  state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
  if (!state.currentTaskId && state.tasks.length) {
    state.currentTaskId = String(state.tasks[0].id || "");
  }
  renderTaskPanel();
}

async function fetchTaskDetail(taskId, options = {}) {
  const { silent = false } = options;
  const id = String(taskId || "");
  if (!id) {
    state.taskDetailLoading = false;
    state.currentTaskDetail = null;
    renderTaskDetail();
    return;
  }
  state.currentTaskId = id;
  if (!silent) {
    state.currentTaskDetail = null;
    state.taskDetailLoading = true;
    renderTaskPanel();
    renderTaskDetail();
  }
  try {
    const detail = await api(`/api/tasks/${encodeURIComponent(id)}`);
    if (state.currentTaskId !== id) return;
    state.currentTaskDetail = detail || null;
  } finally {
    if (state.currentTaskId === id) {
      if (state.taskDetailLoading) state.taskDetailLoading = false;
      renderTaskPanel();
      renderTaskDetail();
    }
  }
}

async function sendBackgroundQuestion() {
  const input = qs("questionInput");
  const message = (input && input.value ? input.value.trim() : "");
  if (!message) return;
  input.value = "";
  renderBubble(message, "user");
  setStatus("后台任务创建中...");
  try {
    const payload = {
      message,
      session_id: state.currentSessionId,
      run_mode: "background",
    };
    if (shouldAttachLatestFile(message)) {
      payload.file_id = state.latestUpload.file_id;
    }
    const data = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderBubble(`后台任务已创建：${data.task_id}`, "system");
    await fetchTasks();
    if (data.task_id) {
      await fetchTaskDetail(data.task_id);
    }
  } catch (err) {
    await uiAlert(`后台任务创建失败：${err.message}`, "操作失败");
  } finally {
    setStatus("就绪");
  }
}

async function runTaskAction(action, taskId) {
  if (!taskId) return;
  const actionMap = {
    cancel: { url: `/api/tasks/${encodeURIComponent(taskId)}/cancel`, body: null, confirm: "确定取消该任务吗？", title: "取消任务" },
    retry: { url: `/api/tasks/${encodeURIComponent(taskId)}/retry`, body: {}, confirm: "确定重试该任务吗？", title: "重试任务" },
    resume: { url: `/api/tasks/${encodeURIComponent(taskId)}/resume`, body: null, confirm: "确定继续该任务吗？", title: "继续任务" },
  };
  const cfg = actionMap[action];
  if (!cfg) return;
  if (!(await uiConfirm(cfg.confirm, cfg.title))) return;
  setStatus("任务操作执行中...");
  try {
    const options = { method: "POST" };
    if (cfg.body !== null) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(cfg.body);
    }
    const data = await api(cfg.url, options);
    if (data && data.task_id) {
      state.currentTaskId = String(data.task_id);
    }
    await fetchTasks();
    if (state.currentTaskId) {
      await fetchTaskDetail(state.currentTaskId);
    }
  } catch (err) {
    await uiAlert(`任务操作失败：${err.message}`, "操作失败");
  } finally {
    setStatus("就绪");
  }
}

function startTaskPolling() {
  if (taskPollTimer) {
    clearInterval(taskPollTimer);
  }
  taskPollTimer = setInterval(async () => {
    try {
      const hasRunning = (state.tasks || []).some((t) => !!t.is_running || String(t.status || "").toLowerCase() === "running");
      if (!hasRunning && !state.currentTaskId) return;
      await fetchTasks();
      if (state.currentTaskId) {
        await fetchTaskDetail(state.currentTaskId, { silent: true });
      }
    } catch (_err) {
      // 轮询失败静默处理，避免打断用户聊天
    }
  }, 3000);
}

function shouldAttachLatestFile(question) {
  const q = String(question || "").toLowerCase();
  if (!state.latestUpload || !state.latestUpload.file_id) return false;
  if (/\bfile[_-]?id\s*[:：]?\s*[a-z0-9_-]+\b/i.test(q)) return false;
  const keywords = ["分析这个文件", "分析文件", "分析数据", "分析表格", "csv", "excel", "xlsx", "xls", "json", "txt", "数据文件"];
  return keywords.some((k) => q.includes(String(k).toLowerCase()));
}

function setHeaderTitle() {
  const current = state.sessions.find((s) => s.id === state.currentSessionId);
  qs("headerTitle").textContent = current ? `当前会话：${current.title}` : "当前会话";
}

function filterSessions() {
  const kw = qs("sessionSearch").value.trim().toLowerCase();
  if (!kw) return state.sessions;
  return state.sessions.filter((s) => (s.title || "").toLowerCase().includes(kw));
}

function renderSessions() {
  const list = qs("sessionList");
  list.innerHTML = "";
  const sessions = filterSessions();
  if (!sessions.length) {
    list.innerHTML = `<div class="status">暂无会话</div>`;
    setHeaderTitle();
    return;
  }
  for (const session of sessions) {
    const row = document.createElement("div");
    row.className = `session-item${session.id === state.currentSessionId ? " active" : ""}`;
    row.innerHTML = `
      <button class="session-title" data-act="switch" data-id="${session.id}">${escapeHtml(session.title)}</button>
      <button class="tiny-btn" data-act="rename" data-id="${session.id}" title="重命名会话">改</button>
      <button class="tiny-btn del" data-act="delete" data-id="${session.id}" title="删除会话">删</button>
    `;
    list.appendChild(row);
  }
  setHeaderTitle();
}

async function reloadSessions() {
  const data = await api("/api/sessions");
  state.sessions = data.sessions || [];
  if (!state.currentSessionId && state.sessions.length) {
    state.currentSessionId = state.sessions[0].id;
  }
  renderSessions();
}

async function switchSession(sessionId) {
  const data = await api(`/api/sessions/${sessionId}/switch`, { method: "POST" });
  state.currentSessionId = data.session_id;
  state.currentTaskId = "";
  state.currentTaskDetail = null;
  state.tasks = [];
  renderSessions();
  qs("chatArea").innerHTML = "";
  const history = data.history_messages || [];
  if (!history.length) {
    renderBubble("此对话暂无消息。", "assistant");
  } else {
    for (const m of history) {
      renderBubble(m.text, m.role === "user" ? "user" : "assistant");
    }
  }
  renderTaskPanel();
  renderTaskDetail();
  await fetchTasks();
  if (state.currentTaskId) {
    await fetchTaskDetail(state.currentTaskId);
  } else {
    renderTaskDetail();
  }
}

function getNested(data, path) {
  const keys = path.split(".");
  let cur = data;
  for (const k of keys) {
    if (typeof cur !== "object" || cur === null || !(k in cur)) return undefined;
    cur = cur[k];
  }
  return cur;
}

function setNested(data, path, value) {
  const keys = path.split(".");
  let cur = data;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (!cur[k] || typeof cur[k] !== "object") cur[k] = {};
    cur = cur[k];
  }
  cur[keys[keys.length - 1]] = value;
}

function parseByType(raw, type) {
  if (type === "bool") return raw === true || raw === "true";
  if (type === "int") return Number.parseInt(raw, 10) || 0;
  if (type === "float") return Number.parseFloat(raw) || 0;
  if (type === "list" || type === "dict") return JSON.parse(raw);
  return String(raw);
}

function valueToInput(item, value) {
  if (item.type === "bool") {
    return `
      <label class="switch-wrap">
        <input class="switch-input" type="checkbox" data-path="${item.path}" data-type="${item.type}" ${value ? "checked" : ""} />
        <span class="switch-slider" aria-hidden="true"></span>
      </label>
    `;
  }
  const safeVal =
    item.type === "list" || item.type === "dict"
      ? JSON.stringify(value)
      : String(value ?? "");
  return `<input class="input setting-input" data-path="${item.path}" data-type="${item.type}" value="${escapeAttr(safeVal)}" />`;
}

function renderTree() {
  const panel = qs("treePanel");
  const categories = state.configCategories || [];
  panel.innerHTML = [
    `<div class="tree-item${state.selectedCategory === "" ? " active" : ""}" data-category="">全部设置</div>`,
    ...categories.map(
      (c) =>
        `<div class="tree-item${state.selectedCategory === c.id ? " active" : ""}" data-category="${escapeAttr(
          c.id
        )}">${escapeHtml(c.label || c.id)}</div>`
    ),
  ].join("");
}

function filteredSettingItems() {
  const kw = qs("settingSearch").value.trim().toLowerCase();
  return state.settingsItems.filter((item) => {
    const meta = getItemMeta(item);
    if (state.selectedCategory && meta.category !== state.selectedCategory) return false;
    if (!kw) return true;
    const value = getNested(state.settingsData, item.path);
    const displayName = getDisplayName(item);
    const desc = String(meta.description || "");
    const hintTitle = item.hint && item.hint.title ? item.hint.title : "";
    const hintRecommend = item.hint && item.hint.recommend ? item.hint.recommend : "";
    return (
      item.path.toLowerCase().includes(kw) ||
      stringifyValue(value).toLowerCase().includes(kw) ||
      displayName.toLowerCase().includes(kw) ||
      desc.toLowerCase().includes(kw) ||
      hintTitle.toLowerCase().includes(kw) ||
      hintRecommend.toLowerCase().includes(kw)
    );
  });
}

function renderSettingsForm() {
  const panel = qs("formPanel");
  const items = filteredSettingItems();
  if (!items.length) {
    panel.innerHTML = `<div class="status">没有匹配到参数</div>`;
    return;
  }
  panel.innerHTML = items
    .map((item) => {
      const value = getNested(state.settingsData, item.path);
      const defaultValue = getNested(state.defaultsData, item.path);
      const displayName = getDisplayName(item);
      const meta = getItemMeta(item);
      return `
        <div class="setting-row" data-row-path="${item.path}">
          <div class="setting-label">${escapeHtml(displayName)}</div>
          <div class="setting-path">配置路径：${escapeHtml(item.path)}</div>
          <div class="setting-meta">
            <span class="meta-pill">${escapeHtml(meta.category_label || "未分类")}</span>
            <span class="meta-pill">${escapeHtml(meta.level_label || "未分级")}</span>
            <span class="meta-pill effect-${escapeHtml(meta.effect || "agent_restart")}">${escapeHtml(meta.effect_label || "需重启")}</span>
            <span class="meta-pill risk-${escapeHtml(meta.risk || "medium")}">风险：${escapeHtml(meta.risk_label || "中")}</span>
          </div>
          <div class="setting-help">当前值：${escapeHtml(stringifyValue(value))} ｜ 默认值：${escapeHtml(stringifyValue(defaultValue))}</div>
          ${meta.description ? `<div class="setting-help">${escapeHtml(meta.description)}</div>` : ""}
          ${meta.hints && meta.hints.recommend ? `<div class="setting-help">${escapeHtml(meta.hints.recommend)}</div>` : ""}
          ${valueToInput(item, value)}
        </div>
      `;
    })
    .join("");
}

function renderHint(path) {
  const el = qs("hintContent");
  const item = state.settingsItems.find((x) => x.path === path);
  if (!item) {
    el.textContent = "在中间列表中选择参数，可查看用途、类型、默认值和调整建议。";
    return;
  }
  const value = getNested(state.settingsData, item.path);
  const defaultValue = getNested(state.defaultsData, item.path);
  const typeLabel = TYPE_LABELS[item.type] || item.type;
  const displayName = getDisplayName(item);
  const meta = getItemMeta(item);
  const lines = [
    `参数名称：${displayName}`,
    `配置路径：${item.path}`,
    `数据类型：${typeLabel}`,
    `分类：${meta.category_label || "未分类"}`,
    `层级：${meta.level_label || "未分级"}`,
    `生效方式：${meta.effect_label || "未知"}`,
    `风险等级：${meta.risk_label || "未知"}`,
    `当前值：${stringifyValue(value)}`,
    `默认值：${stringifyValue(defaultValue)}`,
  ];
  if (meta.disabled_reason) {
    lines.push(`受限说明：${meta.disabled_reason}`);
  }
  const hints = meta.hints || item.hint || {};
  if (hints.title) {
    lines.push(`参数定位：${hints.title}`);
  }
  if (hints.recommend) {
    lines.push(`调参建议：${hints.recommend}`);
  }
  if (Array.isArray(hints.notes)) {
    hints.notes.filter(Boolean).forEach((note) => {
      lines.push(`注意事项：${note}`);
    });
  }
  el.innerHTML = `<pre>${escapeHtml(lines.join("\n"))}</pre>`;
}

function markSettingsDirty(flag = true) {
  state.settingsDirty = flag;
  qs("settingsStatus").textContent = flag ? "有修改待保存" : "已保存";
  qs("settingsStatus").style.color = flag ? "#ef4444" : "#10b981";
}

function renderConfigRuntimeNotice() {
  const box = qs("configRuntimeNotice");
  if (!box) return;
  const effective = state.configEffective || {};
  if (!effective.provider_locked) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  const provider = String(effective.effective_provider || "ollama");
  const reason = String(effective.provider_lock_reason || "");
  const ignored = Array.isArray(effective.ignored_paths) ? effective.ignored_paths.join(", ") : "";
  const parts = [
    `当前实际生效 provider：${provider}`,
    reason || "当前版本存在 provider 锁定。",
  ];
  if (ignored) {
    parts.push(`已忽略配置路径：${ignored}`);
  }
  box.textContent = parts.join("；");
  box.classList.remove("hidden");
}

async function loadSettings() {
  const data = await api("/api/config");
  state.settingsItems = data.editable_items_enriched || data.items || [];
  state.settingsData = data.data || {};
  state.defaultsData = data.defaults || {};
  state.configMetadata = data.metadata || {};
  state.configCategories = data.categories || (data.metadata && data.metadata.categories) || [];
  state.configEffective = data.effective || {};
  state.selectedCategory = "";
  renderConfigRuntimeNotice();
  renderTree();
  renderSettingsForm();
  renderHint("");
  markSettingsDirty(false);
}

async function sendQuestion() {
  if (isAsking) return;
  const input = qs("questionInput");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  renderBubble(question, "user");
  const pending = renderBubble("正在思考...", "assistant");
  activePendingBubble = pending;
  activeChatController = new AbortController();
  isAsking = true;
  updateSendButtonState();
  setStatus("正在思考...");
  try {
    const payload = { question, session_id: state.currentSessionId };
    if (shouldAttachLatestFile(question)) {
      payload.file_id = state.latestUpload.file_id;
    }
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: activeChatController.signal,
    });
    pending.textContent = data.answer || "";
    renderExecutionPanel(data, pending);
    renderArtifacts(data);
    if ((data.sources || []).length) {
      renderBubble(`参考来源: ${data.sources.join(", ")}`, "system");
    }
    if (data.task_id) {
      await fetchTasks();
      await fetchTaskDetail(data.task_id);
    }
    if (data.session_id) state.currentSessionId = data.session_id;
    await reloadSessions();
  } catch (err) {
    if (err && err.name === "AbortError") {
      pending.textContent = "已停止本次回答。";
      return;
    }
    pending.textContent = `错误: ${err.message}`;
  } finally {
    activeChatController = null;
    activePendingBubble = null;
    isAsking = false;
    updateSendButtonState();
    setStatus("就绪");
  }
}

async function uploadDataFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  setStatus("上传数据中...");
  try {
    const data = await api("/api/files/upload", { method: "POST", body: form });
    const info = data.file || {};
    state.latestUpload = info;
    const hint = qs("uploadHint");
    if (hint && info.file_id) {
      hint.textContent = `已上传：${info.original_name}，file_id: ${info.file_id}。你可以输入“分析这个文件”。`;
    }
    renderBubble(`已上传数据文件：${info.original_name}（file_id: ${info.file_id}）`, "system");
  } catch (err) {
    await uiAlert(`上传失败：${err.message}`, "上传失败");
  } finally {
    setStatus("就绪");
  }
}

async function uploadKbDocument(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  setStatus("资料上传中...");
  try {
    const data = await api("/api/kb/upload", { method: "POST", body: form });
    const info = data.file || {};
    const originalName = info.original_name || file.name || "未命名文件";
    renderBubble(`已添加资料：${originalName}，正在增量更新索引...`, "system");
    await doKbSync(false);
    await refreshKbConsole();
    renderBubble(`知识库已更新：${originalName}`, "system");
  } catch (err) {
    await uiAlert(`添加资料失败：${err.message}`, "上传失败");
  } finally {
    setStatus("就绪");
  }
}

async function refreshKbConsole() {
  const docs = await api("/api/kb/documents");
  state.kbDocs = (docs && docs.documents) || [];
  if (!state.kbDocs.length) {
    state.kbSelectedDocName = "";
  } else {
    const keep = state.kbDocs.some((d) => String(d.name || "") === String(state.kbSelectedDocName || ""));
    if (!keep) {
      state.kbSelectedDocName = String(state.kbDocs[0].name || "");
    }
  }
  renderKbDocsContent();
}

async function openKbConsole() {
  qs("kbPanel").classList.remove("hidden");
  qs("kbDocsContent").innerHTML = `<div class="kb-doc-empty">加载中...</div>`;
  await refreshKbConsole();
}

async function doKbSync(showMessage = true) {
  setStatus("知识库刷新中...");
  const data = await api("/api/kb/sync", { method: "POST" });
  const changes = data.changes || {};
  if (showMessage) {
    renderBubble(
      `知识库更新完成：模式=${data.mode || "unknown"}，新增${changes.added || 0}，修改${changes.updated || 0}，删除${changes.removed || 0}`,
      "system"
    );
  }
  setStatus("就绪");
  return data;
}

function downloadYaml(name, text) {
  const blob = new Blob([text], { type: "text/yaml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  setupMenu("toggleKbMenuBtn", "kbMenuWrap");

  qs("sessionSearch").addEventListener("input", renderSessions);
  qs("newSessionBtn").addEventListener("click", async () => {
    const title = await uiPrompt("请输入对话标题", "新对话", "新建对话");
    if (title === null) return;
    const data = await api("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    state.currentSessionId = data.session_id;
    await reloadSessions();
    await switchSession(state.currentSessionId);
  });

  qs("sessionList").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const act = btn.dataset.act;
    if (act === "switch") {
      await switchSession(id);
    } else if (act === "rename") {
      const title = await uiPrompt("请输入新的会话标题", "", "重命名会话");
      if (!title) return;
      await api(`/api/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      await reloadSessions();
    } else if (act === "delete") {
      if (!(await uiConfirm("确定删除该会话吗？", "删除会话"))) return;
      const data = await api(`/api/sessions/${id}`, { method: "DELETE" });
      state.sessions = data.sessions || [];
      state.currentSessionId = data.current_session_id || (state.sessions[0] && state.sessions[0].id) || null;
      renderSessions();
      if (state.currentSessionId) await switchSession(state.currentSessionId);
      else qs("chatArea").innerHTML = "";
    }
  });
  qs("taskList").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-task-id]");
    if (!btn) return;
    const taskId = btn.getAttribute("data-task-id");
    if (!taskId) return;
    await fetchTaskDetail(taskId);
  });
  qs("taskDetail").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-task-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-task-action");
    const taskId = btn.getAttribute("data-task-id");
    await runTaskAction(action, taskId);
  });

  qs("sendBtn").addEventListener("click", () => {
    if (isAsking) {
      stopAnswering();
      return;
    }
    sendQuestion();
  });
  qs("sendBgBtn").addEventListener("click", async () => {
    if (isAsking) return;
    await sendBackgroundQuestion();
  });
  qs("questionInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (isAsking) return;
      sendQuestion();
    }
  });
  qs("uploadDataBtn").addEventListener("click", () => qs("dataFileInput").click());
  qs("dataFileInput").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) await uploadDataFile(file);
    e.target.value = "";
  });
  qs("clearSessionBtn").addEventListener("click", async () => {
    if (!state.currentSessionId) return;
    if (!(await uiConfirm("确定清除并删除当前会话吗？", "删除会话"))) return;
    const data = await api(`/api/sessions/${state.currentSessionId}`, { method: "DELETE" });
    state.sessions = data.sessions || [];
    state.currentSessionId = data.current_session_id || (state.sessions[0] && state.sessions[0].id) || null;
    renderSessions();
    qs("chatArea").innerHTML = "";
    if (state.currentSessionId) await switchSession(state.currentSessionId);
  });
  qs("syncKbBtn").addEventListener("click", async () => {
    try {
      await doKbSync(true);
    } catch (err) {
      renderBubble(`知识库刷新失败: ${err.message}`, "system");
      setStatus("就绪");
    }
  });
  qs("openKbConsoleBtn").addEventListener("click", async () => {
    await openKbConsole();
  });
  qs("closeKbBtn").addEventListener("click", () => {
    qs("kbPanel").classList.add("hidden");
  });
  qs("kbDocsContent").addEventListener("click", (e) => {
    const item = e.target.closest(".kb-doc-item");
    if (!item) return;
    const name = String(item.dataset.docName || "");
    if (!name) return;
    state.kbSelectedDocName = name;
    renderKbDocsContent();
  });
  qs("kbRefreshBtn").addEventListener("click", async () => {
    await refreshKbConsole();
  });
  qs("kbRebuildBtn").addEventListener("click", async () => {
    if (!(await uiConfirm("确定执行全量重建吗？这会较慢。", "全量重建"))) return;
    try {
      setStatus("知识库全量重建中...");
      await api("/api/kb/rebuild", { method: "POST" });
      await refreshKbConsole();
    } catch (err) {
      await uiAlert(`全量重建失败: ${err.message}`, "执行失败");
    } finally {
      setStatus("就绪");
    }
  });
  qs("kbAddDocBtn").addEventListener("click", () => qs("kbDocFileInput").click());
  qs("kbDocFileInput").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) await uploadKbDocument(file);
    e.target.value = "";
  });
  qs("kbResetBtn").addEventListener("click", async () => {
    if (!(await uiConfirm("确定执行系统重置吗？会清空会话与索引缓存。", "系统重置"))) return;
    try {
      setStatus("系统重置中...");
      await api("/api/system/reset", { method: "POST" });
      qs("chatArea").innerHTML = "";
      renderBubble("系统已触发重置，服务与页面即将关闭。", "system");
      await uiAlert("系统已重置，程序与页面即将关闭。", "重置完成");
      try {
        await api("/api/system/shutdown", { method: "POST" });
      } catch (_err) {
        // 服务可能在返回前已关闭，前端无需再报错打断用户。
      }
      closeUiAfterReset();
    } catch (err) {
      const msg = String(err && err.message ? err.message : "");
      if (msg.includes("系统已标记重置")) {
        await uiAlert("系统已进入重置状态，服务与页面即将关闭。", "重置处理中");
        try {
          await api("/api/system/shutdown", { method: "POST" });
        } catch (_err) {
          // 服务可能已在关闭流程中，忽略即可。
        }
        closeUiAfterReset();
        return;
      }
      await uiAlert(`系统重置失败: ${err.message}`, "执行失败");
    } finally {
      setStatus("就绪");
    }
  });

  qs("openSettingsBtn").addEventListener("click", async () => {
    lockPageScroll();
    qs("settingsPanel").classList.remove("hidden");
    await loadSettings();
  });
  qs("openObservabilityBtn").addEventListener("click", async () => {
    await toggleObservability();
  });
  qs("closeSettingsBtn").addEventListener("click", async () => {
    if (state.settingsDirty && !(await uiConfirm("有未保存修改，确定关闭？", "关闭设置"))) return;
    qs("settingsPanel").classList.add("hidden");
    unlockPageScroll();
  });

  qs("settingSearch").addEventListener("input", renderSettingsForm);
  qs("treePanel").addEventListener("click", (e) => {
    const item = e.target.closest(".tree-item");
    if (!item) return;
    state.selectedCategory = item.dataset.category || "";
    renderTree();
    renderSettingsForm();
  });
  qs("formPanel").addEventListener("input", (e) => {
    const input = e.target.closest("[data-path]");
    if (!input) return;
    const item = state.settingsItems.find((x) => x.path === input.dataset.path);
    if (!item) return;
    try {
      const raw = input.type === "checkbox" ? input.checked : input.value;
      const parsed = parseByType(raw, input.dataset.type);
      setNested(state.settingsData, item.path, parsed);
      markSettingsDirty(true);
      renderHint(item.path);
    } catch (err) {
      renderHint(item.path);
    }
  });
  qs("formPanel").addEventListener("click", (e) => {
    const row = e.target.closest(".setting-row");
    if (!row) return;
    state.selectedPath = row.dataset.rowPath;
    renderHint(state.selectedPath);
  });

  qs("saveSettingsBtn").addEventListener("click", async () => {
    const result = await api("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: state.settingsData }),
    });
    state.configEffective = result.effective || state.configEffective || {};
    renderConfigRuntimeNotice();
    markSettingsDirty(false);
    const lockReason = String((result && result.warning) || "");
    const msg = lockReason
      ? `参数已保存。${lockReason} 部分参数需重启后生效。`
      : "参数已保存，部分参数需重启后生效。";
    await uiAlert(msg, "保存成功");
  });

  qs("resetBtn").addEventListener("click", async () => {
    if (!(await uiConfirm("确定恢复默认参数吗？", "恢复默认"))) return;
    await api("/api/config/reset", { method: "POST" });
    await loadSettings();
  });
  qs("exportBtn").addEventListener("click", async () => {
    const text = await api("/api/config/export");
    downloadYaml("config.export.yaml", text);
  });
  qs("importBtn").addEventListener("click", () => qs("importFileInput").click());
  qs("importFileInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    await api("/api/config/import", { method: "POST", body: form });
    await loadSettings();
    e.target.value = "";
  });
}

async function init() {
  bindEvents();
  updateSendButtonState();
  renderObservabilityButton();
  setStatus("初始化中...");
  const data = await api("/api/bootstrap");
  state.sessions = data.sessions || [];
  state.currentSessionId = data.current_session_id;
  renderSessions();
  qs("chatArea").innerHTML = "";
  const history = data.history_messages || [];
  if (!history.length) {
    renderBubble("你好，我是 GeoClaw-LS。你可以直接询问滑坡机理、监测、预警和防治问题。", "assistant");
  } else {
    history.forEach((m) => renderBubble(m.text, m.role === "user" ? "user" : "assistant"));
  }
  await fetchTasks();
  if (state.currentTaskId) {
    await fetchTaskDetail(state.currentTaskId);
  } else {
    renderTaskDetail();
  }
  await loadObservabilityStatus();
  startTaskPolling();
  setStatus("就绪");
}

init().catch((err) => {
  setStatus("初始化失败");
  renderBubble(`初始化失败: ${err.message}`, "system");
});
