from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from services.config_support import COMMON_PREFIXES, HIDDEN_PREFIXES, PARAM_HINTS, iter_leaf_items

CATEGORY_LABELS: Dict[str, str] = {
    "basic": "基础设置",
    "model": "模型设置",
    "embedding": "Embedding 设置",
    "rag": "知识库 / RAG",
    "agent": "Agent / Planner",
    "tools": "工具与能力",
    "workspace": "文件与工作区",
    "observability": "观测与日志",
    "system": "系统维护",
    "developer": "开发者高级项",
}

EFFECT_LABELS: Dict[str, str] = {
    "immediate": "即时生效",
    "agent_restart": "需重建 Agent",
    "kb_rebuild": "需重建知识库",
    "service_restart": "需重启服务",
    "internal": "内部配置",
}

RISK_LABELS: Dict[str, str] = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "internal": "内部",
}

LEVEL_LABELS: Dict[str, str] = {
    "basic": "基础",
    "advanced": "高级",
    "developer": "开发者",
}

@dataclass(frozen=True)
class ItemDoc:
    prefix: str
    label: str
    description: str
    recommendation: str = ""
    effect: str | None = None
    risk: str | None = None


ITEM_DOCS: Tuple[ItemDoc, ...] = (
    ItemDoc("agent.max_context_len", "上下文容量（最大上下文长度）", "控制单轮问答可携带的总上下文大小。增大可减少“忘上下文”，但会增加耗时和资源占用。", "通常保持 12000~20000。不是越大越好，先优先优化问题表达与检索命中。"),
    ItemDoc("agent.max_history_rounds", "携带历史轮数", "控制每次回答会带入多少轮历史对话。", "历史轮数太高会引入旧信息干扰；出现答非所问时可适度调低。"),
    ItemDoc("models.ollama.url", "本地模型服务地址", "回答模型请求地址，通常指向本机 Ollama generate 接口。", "本机默认 http://localhost:11434/api/generate；改动后建议重建 Agent。"),
    ItemDoc("models.ollama.model", "回答模型", "用于生成最终回答的本地模型名称。", "切换模型后建议做一次问答回归，关注术语准确性和响应速度。"),
    ItemDoc("models.ollama.temperature", "回答发散程度", "控制回答的稳定性与创造性。数值越低越稳，越高越灵活。", "知识问答通常 0.2~0.7；需要更保守结论可降低。"),
    ItemDoc("models.ollama.timeout", "模型请求超时", "非流式请求最大等待时间（秒）。", "遇到模型慢响应或超时中断时再调高，过高会延长异常等待。"),
    ItemDoc("models.ollama.stream_timeout", "流式输出超时", "流式回答模式下的最大等待时间（秒）。", "模型较慢时可略调高；若频繁卡住请先检查 Ollama 服务负载。"),
    ItemDoc("models.embedding", "知识库向量模型", "知识库分块向量化使用的模型，决定检索语义空间。", "修改后需要重建知识库，否则新旧向量语义空间可能不一致。", effect="kb_rebuild", risk="high"),
    ItemDoc("models.embedding_backend", "向量生成方式", "选择向量生成后端（如 Ollama 或 sentence-transformers）。", "后端切换后建议重建知识库并回归检索质量。", effect="kb_rebuild", risk="high"),
    ItemDoc("models.embedding_ollama_batch_size", "向量化批量大小", "控制每批发送到向量模型的文本数量。", "批量过大可能导致内存峰值上升；资源紧张时可下调。"),
    ItemDoc("rag.search_top_k", "知识库召回数量", "首轮检索返回的候选片段数量。", "偏小可能漏召回，偏大可能引入噪声；常用范围 3~8。"),
    ItemDoc("rag.expansion_top_k", "扩展召回数量", "低质量时二次扩展检索的候选数量。", "当问题跨度大、首轮命中不足时可增大。"),
    ItemDoc("rag.quality_threshold", "检索质量阈值", "判断检索结果是否足够可靠的阈值。", "调高会更严格、触发更多重检索；调低会更宽松。"),
    ItemDoc("rag.rerank_strategy", "检索重排策略", "控制召回结果的排序方式（如 keyword/model）。", "策略变化会影响答案证据顺序，调整后建议做问答回归。"),
    ItemDoc("graph.replan_on_low_quality", "低质量检索重规划", "检索质量不足时是否自动重规划执行步骤。", "开启可提升稳健性，但会增加延迟与 token 成本。"),
    ItemDoc("graph.replan_max_attempts", "重规划最大次数", "限制单次任务最多触发几次重规划。", "次数越高，复杂问题恢复能力越强，但整体耗时更长。"),
    ItemDoc("graph.replan_low_quality_threshold", "低质量判定阈值", "低于该值即视为检索质量不足。", "可与 `rag.quality_threshold` 联动调节，避免过度重试。"),
    ItemDoc("graph.replan_require_expansion", "重规划前要求扩展检索", "重规划前先尝试扩展召回，提高补救命中率。", "若强调响应速度可关闭；若强调完整性建议保持开启。"),
    ItemDoc("graph.step_result_max_chars", "步骤结果长度上限", "限制单个执行步骤可写入的文本长度。", "过小会截断证据，过大可能拖慢任务详情展示。"),
    ItemDoc("retrieval.fast_path.enabled", "快速检索路径", "开启后对高把握问题走更短检索链路以降低延迟。", "追求稳定优先可关闭；追求速度可开启。"),
    ItemDoc("retrieval.metrics.enabled", "检索指标日志", "记录检索指标到日志，便于排查命中质量。", "生产环境可按磁盘与观测需求决定是否开启。"),
    ItemDoc("kb_watcher.enabled", "知识库自动监听", "自动监测 `data/` 目录变化并触发同步。", "关闭后需手动同步知识库，适合希望严格控制刷新时机的场景。"),
    ItemDoc("observability.enabled", "Phoenix 观测开关", "控制 OpenTelemetry / Phoenix 链路是否启用。", "开启会增加少量开销，但更利于诊断执行链路。"),
)

@dataclass(frozen=True)
class MetadataRule:
    prefix: str
    category: str
    level: str
    effect: str
    risk: str
    description: str

RULES: Tuple[MetadataRule, ...] = (
    MetadataRule("agent.", "basic", "basic", "agent_restart", "medium", "控制上下文长度与历史轮数。"),
    MetadataRule("models.ollama.", "model", "basic", "agent_restart", "medium", "本地 Ollama 回复模型参数。"),
    MetadataRule("models.embedding", "embedding", "advanced", "kb_rebuild", "high", "Embedding 模型切换通常需要重建索引。"),
    MetadataRule("models.embedding_", "embedding", "advanced", "agent_restart", "medium", "Embedding 后端请求参数。"),
    MetadataRule("rag.", "rag", "advanced", "kb_rebuild", "high", "检索召回、质量与重排策略。"),
    MetadataRule("vector_search.", "rag", "advanced", "agent_restart", "medium", "向量检索融合和缓存参数。"),
    MetadataRule("graph.", "agent", "advanced", "agent_restart", "medium", "Agent 执行图与重规划控制。"),
    MetadataRule("llm.temperatures.", "agent", "developer", "agent_restart", "medium", "链路温度等内部提示参数。"),
    MetadataRule("tool.", "tools", "advanced", "agent_restart", "medium", "工具调用阈值与安全边界。"),
    MetadataRule("capabilities.", "tools", "developer", "agent_restart", "medium", "能力开关与声明。"),
    MetadataRule("kb_watcher.", "workspace", "advanced", "service_restart", "medium", "知识库文件监听与轮询参数。"),
    MetadataRule("observability.", "observability", "advanced", "service_restart", "medium", "观测链路开关与导出配置。"),
    MetadataRule("retrieval.metrics.", "observability", "developer", "internal", "internal", "检索指标内部日志配置。"),
    MetadataRule("system.", "system", "developer", "service_restart", "high", "系统级运行参数。"),
    MetadataRule("chunking.", "developer", "developer", "kb_rebuild", "high", "文档切分算法内部参数。"),
    MetadataRule("keyword_rerank.", "developer", "developer", "agent_restart", "medium", "关键词重排内部参数。"),
    MetadataRule("terminology.", "developer", "developer", "agent_restart", "medium", "术语修正规则。"),
)

def _is_hidden_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in HIDDEN_PREFIXES)

def _match_rule(path: str) -> MetadataRule | None:
    for rule in RULES:
        if path == rule.prefix or path.startswith(rule.prefix):
            return rule
    return None


def _match_item_doc(path: str) -> ItemDoc | None:
    for doc in ITEM_DOCS:
        if path == doc.prefix or path.startswith(doc.prefix):
            return doc
    return None

def _fallback_category(path: str) -> str:
    head = (path.split(".", 1)[0] or "").lower()
    if head in {"models"}:
        return "model"
    if head in {"rag", "vector_search"}:
        return "rag"
    if head in {"agent", "graph", "llm"}:
        return "agent"
    if head in {"tool", "capabilities"}:
        return "tools"
    if head in {"observability", "retrieval", "logging"}:
        return "observability"
    if head in {"kb_watcher"}:
        return "workspace"
    if head in {"system"}:
        return "system"
    return "basic"

def build_item_metadata(path: str, value: Any, default_value: Any = None) -> Dict[str, Any]:
    hint = PARAM_HINTS.get(path)
    rule = _match_rule(path)
    item_doc = _match_item_doc(path)
    category = rule.category if rule else _fallback_category(path)
    level = rule.level if rule else ("basic" if any(path.startswith(p) for p in COMMON_PREFIXES) else "advanced")
    effect = item_doc.effect if item_doc and item_doc.effect else (rule.effect if rule else "agent_restart")
    risk = item_doc.risk if item_doc and item_doc.risk else (rule.risk if rule else "medium")
    description = item_doc.description if item_doc else (rule.description if rule else "")
    hidden = _is_hidden_path(path)

    reasons: List[str] = []
    if hidden:
        reasons.append("该项属于隐藏前缀，默认不在普通设置页展示。")
    display_label = item_doc.label if item_doc else (hint[0] if hint else path.split(".")[-1])
    recommend_text = item_doc.recommendation if item_doc else (hint[1] if hint else "")
    title_text = item_doc.label if item_doc else (hint[0] if hint else "")

    return {
        "path": path,
        "label": display_label,
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category),
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level),
        "effect": effect,
        "effect_label": EFFECT_LABELS.get(effect, effect),
        "risk": risk,
        "risk_label": RISK_LABELS.get(risk, risk),
        "description": description or title_text,
        "hints": {
            "title": title_text,
            "recommend": recommend_text,
            "notes": reasons,
        },
        "hidden": hidden,
        "editable": (not hidden) and effect != "internal",
        "current_value": value,
        "default_value": default_value,
        "disabled_reason": "",
    }

def build_metadata_payload(data: Dict[str, Any], defaults: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    defaults_map = dict(iter_leaf_items(defaults))
    item_map: Dict[str, Dict[str, Any]] = {}
    for row in items:
        path = str(row.get("path") or "")
        if not path:
            continue
        item_map[path] = build_item_metadata(path, row.get("value"), defaults_map.get(path))

    hidden_items: List[Dict[str, Any]] = []
    for path, value in iter_leaf_items(data):
        if path in item_map:
            continue
        if not _is_hidden_path(path):
            continue
        hidden_items.append(build_item_metadata(path, value, defaults_map.get(path)))

    editable_items_enriched = [dict(row, metadata=item_map.get(str(row.get("path") or ""), {})) for row in items]
    categories = [{"id": key, "label": label} for key, label in CATEGORY_LABELS.items()]
    effects = [{"id": key, "label": label} for key, label in EFFECT_LABELS.items()]
    risks = [{"id": key, "label": label} for key, label in RISK_LABELS.items()]
    levels = [{"id": key, "label": label} for key, label in LEVEL_LABELS.items()]

    return {
        "categories": categories,
        "effects": effects,
        "risks": risks,
        "levels": levels,
        "by_path": item_map,
        "hidden_items": hidden_items,
        "ollama_only_notice": "当前版本仅使用本地 Ollama。",
        "editable_items_enriched": editable_items_enriched,
    }

def apply_editable_subset(current: Dict[str, Any], incoming: Dict[str, Any], editable_paths: List[str]) -> Dict[str, Any]:
    merged = dict(current)
    editable_set = set(editable_paths)
    for path, value in iter_leaf_items(incoming):
        if path not in editable_set:
            continue
        cursor = merged
        keys = path.split(".")
        for key in keys[:-1]:
            node = cursor.get(key)
            if not isinstance(node, dict):
                node = {}
                cursor[key] = node
            cursor = node
        cursor[keys[-1]] = value
    return merged
