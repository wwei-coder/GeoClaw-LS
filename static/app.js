const state = {
  sessions: [],
  currentSessionId: null,
  settingsItems: [],
  settingsData: {},
  defaultsData: {},
  selectedPrefix: "",
  selectedPath: "",
  settingsDirty: false,
  kbDocs: [],
};
let pageScrollLockCount = 0;
let isAsking = false;
let activeChatController = null;
let activePendingBubble = null;
let expandedTreePrefixes = new Set([""]);
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

function formatPathLabel(path = "") {
  const parts = String(path || "").split(".");
  const useful = parts[0] === "config" ? parts.slice(1) : parts;
  if (!useful.length) return "全部设置";
  return useful.map((seg) => toReadableLabel(seg) || seg).join(" / ");
}

function getDisplayName(item) {
  if (!item) return "";
  if (item.hint && item.hint.title) return item.hint.title;
  const parts = item.path.split(".");
  const tail = parts[parts.length - 1] || "";
  return toReadableLabel(tail) || tail;
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

function renderKbDocsContent() {
  const el = qs("kbDocsContent");
  if (!el) return;
  if (!state.kbDocs.length) {
    el.innerHTML = `<div class="kb-doc-empty">暂无文档索引信息</div>`;
    return;
  }
  el.innerHTML = `
    <div class="kb-doc-list">
      ${state.kbDocs
        .map((d) => {
          const name = escapeHtml(d.name || "未命名文档");
          const chunks = Number(d.indexed_chunks ?? 0);
          const status = formatDocStatus(d.fingerprint_status);
          const sizeText = formatFileSize(d.size);
          return `
            <div class="kb-doc-item">
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
}

function splitConfigPath(path = "") {
  const parts = String(path || "").split(".");
  return parts[0] === "config" ? parts.slice(1) : parts;
}

function getPathPrefixAtDepth(path = "", depth = 0) {
  const parts = splitConfigPath(path);
  if (!parts.length || depth < 0 || depth >= parts.length) return "";
  return parts.slice(0, depth + 1).join(".");
}

function getTreeChildrenMap(items = []) {
  const map = new Map();
  map.set("", new Set());
  for (const item of items) {
    const parts = splitConfigPath(item.path);
    for (let i = 0; i < parts.length; i++) {
      const parent = parts.slice(0, i).join(".");
      const child = parts.slice(0, i + 1).join(".");
      if (!map.has(parent)) map.set(parent, new Set());
      map.get(parent).add(child);
      if (!map.has(child)) map.set(child, new Set());
    }
  }
  return map;
}

function getPrefixDepth(prefix = "") {
  if (!prefix) return 0;
  return splitConfigPath(prefix).length;
}

function getPrefixLabel(prefix = "") {
  if (!prefix) return "全部设置";
  const parts = splitConfigPath(prefix);
  const tail = parts[parts.length - 1] || "";
  return toReadableLabel(tail) || tail;
}

function ensureTreeExpandedDefaults(treeChildrenMap) {
  if (expandedTreePrefixes.size > 1) return;
  expandedTreePrefixes = new Set([""]);
  const topChildren = [...(treeChildrenMap.get("") || [])];
  topChildren.forEach((prefix) => expandedTreePrefixes.add(prefix));
}

function expandSelectedAncestors(prefix = "") {
  const parts = splitConfigPath(prefix);
  for (let i = 0; i < parts.length - 1; i++) {
    expandedTreePrefixes.add(parts.slice(0, i + 1).join("."));
  }
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
  renderSessions();
  qs("chatArea").innerHTML = "";
  const history = data.history_messages || [];
  if (!history.length) {
    renderBubble("此对话暂无消息。", "assistant");
    return;
  }
  for (const m of history) {
    renderBubble(m.text, m.role === "user" ? "user" : "assistant");
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
  const treeChildrenMap = getTreeChildrenMap(state.settingsItems);
  ensureTreeExpandedDefaults(treeChildrenMap);
  expandSelectedAncestors(state.selectedPrefix);

  const renderNode = (prefix) => {
    const children = [...(treeChildrenMap.get(prefix) || [])];
    children.sort((a, b) => getPrefixLabel(a).localeCompare(getPrefixLabel(b), "zh-CN"));
    return children
      .map((childPrefix) => {
        const depth = getPrefixDepth(childPrefix);
        const childChildren = [...(treeChildrenMap.get(childPrefix) || [])];
        const hasChildren = childChildren.length > 0;
        const expanded = expandedTreePrefixes.has(childPrefix);
        const caret = hasChildren ? (expanded ? "▾" : "▸") : "•";
        const row = `
          <div
            class="tree-item${childPrefix === state.selectedPrefix ? " active" : ""}"
            data-prefix="${childPrefix}"
            data-has-children="${hasChildren ? "1" : "0"}"
            style="padding-left:${8 + depth * 14}px"
          >
            <span class="tree-caret">${caret}</span>
            <span class="tree-label">${escapeHtml(getPrefixLabel(childPrefix))}</span>
          </div>
        `;
        if (!hasChildren || !expanded) return row;
        return `${row}${renderNode(childPrefix)}`;
      })
      .join("");
  };

  panel.innerHTML = `
    <div class="tree-item${state.selectedPrefix === "" ? " active" : ""}" data-prefix="" data-has-children="1">
      <span class="tree-caret">${expandedTreePrefixes.has("") ? "▾" : "▸"}</span>
      <span class="tree-label">全部设置</span>
    </div>
    ${expandedTreePrefixes.has("") ? renderNode("") : ""}
  `;
}

function filteredSettingItems() {
  const kw = qs("settingSearch").value.trim().toLowerCase();
  return state.settingsItems.filter((item) => {
    if (state.selectedPrefix && !item.path.startsWith(state.selectedPrefix)) return false;
    if (!kw) return true;
    const value = getNested(state.settingsData, item.path);
    const displayName = getDisplayName(item);
    const hintTitle = item.hint && item.hint.title ? item.hint.title : "";
    const hintRecommend = item.hint && item.hint.recommend ? item.hint.recommend : "";
    return (
      item.path.toLowerCase().includes(kw) ||
      stringifyValue(value).toLowerCase().includes(kw) ||
      displayName.toLowerCase().includes(kw) ||
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
      const displayName = getDisplayName(item);
      return `
        <div class="setting-row" data-row-path="${item.path}">
          <div class="setting-label">${escapeHtml(displayName)}</div>
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
  const lines = [
    `参数名称：${displayName}`,
    `配置路径：${item.path}`,
    `数据类型：${typeLabel}`,
    `当前值：${stringifyValue(value)}`,
    `默认值：${stringifyValue(defaultValue)}`,
  ];
  if (item.hint) {
    lines.push(`作用说明：${item.hint.title}`);
    lines.push(`调整建议：${item.hint.recommend}`);
  }
  el.innerHTML = `<pre>${escapeHtml(lines.join("\n"))}</pre>`;
}

function markSettingsDirty(flag = true) {
  state.settingsDirty = flag;
  qs("settingsStatus").textContent = flag ? "有修改待保存" : "已保存";
  qs("settingsStatus").style.color = flag ? "#ef4444" : "#10b981";
}

async function loadSettings() {
  const data = await api("/api/config");
  state.settingsItems = data.items || [];
  state.settingsData = data.data || {};
  state.defaultsData = data.defaults || {};
  state.selectedPrefix = "";
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
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: state.currentSessionId }),
      signal: activeChatController.signal,
    });
    pending.textContent = data.answer || "";
    if ((data.sources || []).length) {
      renderBubble(`参考来源: ${data.sources.join(", ")}`, "system");
    }
    if (data.trace) {
      renderBubble(`执行轨迹: ${data.trace}`, "system");
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

async function refreshKbConsole() {
  const docs = await api("/api/kb/documents");
  state.kbDocs = (docs && docs.documents) || [];
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

  qs("sendBtn").addEventListener("click", () => {
    if (isAsking) {
      stopAnswering();
      return;
    }
    sendQuestion();
  });
  qs("questionInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (isAsking) return;
      sendQuestion();
    }
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
  qs("kbResetBtn").addEventListener("click", async () => {
    if (!(await uiConfirm("确定执行系统重置吗？会清空会话与索引缓存。", "系统重置"))) return;
    try {
      setStatus("系统重置中...");
      await api("/api/system/reset", { method: "POST" });
      await reloadSessions();
      qs("chatArea").innerHTML = "";
      renderBubble("系统已重置，请继续提问。", "system");
      await refreshKbConsole();
    } catch (err) {
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
  qs("closeSettingsBtn").addEventListener("click", async () => {
    if (state.settingsDirty && !(await uiConfirm("有未保存修改，确定关闭？", "关闭设置"))) return;
    qs("settingsPanel").classList.add("hidden");
    unlockPageScroll();
  });

  qs("settingSearch").addEventListener("input", renderSettingsForm);
  qs("treePanel").addEventListener("click", (e) => {
    const item = e.target.closest(".tree-item");
    if (!item) return;
    const prefix = item.dataset.prefix || "";
    const hasChildren = item.dataset.hasChildren === "1";
    state.selectedPrefix = prefix;
    if (hasChildren) {
      if (expandedTreePrefixes.has(prefix)) expandedTreePrefixes.delete(prefix);
      else expandedTreePrefixes.add(prefix);
    }
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
    await api("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: state.settingsData }),
    });
    markSettingsDirty(false);
    await uiAlert("参数已保存，部分参数需重启后生效。", "保存成功");
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
  setStatus("就绪");
}

init().catch((err) => {
  setStatus("初始化失败");
  renderBubble(`初始化失败: ${err.message}`, "system");
});
