import os
import yaml
from utils.logger import logger
# Base Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
# Database Paths
DB_PATH = os.path.join(BASE_DIR, "long_term_memory.db")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "vector_db")
FINGERPRINT_PATH = os.path.join(BASE_DIR, "doc_fingerprint.json")
# Load Config
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.yaml")
PROMPTS_PATH = os.path.join(BASE_DIR, "config", "prompts.yaml")
PLANNER_PATH = os.path.join(BASE_DIR, "config", "planner.yaml")

def load_yaml(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"[Config] Failed to load {path}: {e}")
            return {}
    return {}

_config = load_yaml(CONFIG_PATH)
_prompts_config = load_yaml(PROMPTS_PATH)
_planner_config = load_yaml(PLANNER_PATH)

# Helper to safely get nested config
def get_config(path, default=None):

    keys = path.split('.')
    value = _config
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default
    return value if value is not None else default

def to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default

# System - Set Hugging Face Mirror
os.environ["HF_ENDPOINT"] = get_config("system.hf_endpoint", "https://hf-mirror.com")

# Model Configuration
# Logic: Try to find the model in local MODELS_DIR first (using the last part of the name),
# otherwise use the full name from config (which might be a huggingface repo ID).
_embedding_model_name = get_config("models.embedding", "BAAI/bge-small-zh-v1.5")
EMBEDDING_BACKEND = str(get_config("models.embedding_backend", "sentence_transformers")).strip().lower()
# Extract folder name from repo ID (e.g., "bge-small-zh-v1.5" from "BAAI/bge-small-zh-v1.5")
_local_embedding_folder = _embedding_model_name.split('/')[-1]
_local_embedding_path = os.path.join(MODELS_DIR, _local_embedding_folder)

# Maintain backward compatibility variable EMBEDDING_MODEL_BGE pointing to local path
EMBEDDING_MODEL_BGE = _local_embedding_path

if EMBEDDING_BACKEND == "sentence_transformers" and os.path.exists(_local_embedding_path):
    DEFAULT_EMBEDDING_MODEL = _local_embedding_path
else:
    DEFAULT_EMBEDDING_MODEL = _embedding_model_name
EMBEDDING_OLLAMA_URL = str(get_config("models.embedding_ollama_url", "http://localhost:11434/api/embed")).strip()
EMBEDDING_OLLAMA_TIMEOUT = int(get_config("models.embedding_ollama_timeout", 60))
EMBEDDING_OLLAMA_BATCH_SIZE = int(get_config("models.embedding_ollama_batch_size", 16))

# LLM Provider Configuration
# Force local-only mode: always use Ollama and ignore remote provider overrides.
LLM_PROVIDER = "ollama"

# Ollama Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", get_config("models.ollama.url", "http://localhost:11434/api/generate"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", get_config("models.ollama.model", "deepseek-r1:7b"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", get_config("models.ollama.temperature", 0.7)))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", get_config("models.ollama.timeout", 60)))
OLLAMA_STREAM_TIMEOUT = int(os.getenv("OLLAMA_STREAM_TIMEOUT", get_config("models.ollama.stream_timeout", 120)))

# OpenAI-compatible API Configuration (disabled in local-only mode)
LLM_API_BASE_URL = ""
LLM_API_KEY = ""
LLM_API_MODEL = OLLAMA_MODEL
LLM_API_TIMEOUT = OLLAMA_TIMEOUT
LLM_API_STREAM_TIMEOUT = OLLAMA_STREAM_TIMEOUT
LLM_API_MAX_TOKENS = 0

# Vector Store Configuration
VECTOR_COLLECTION_NAME = get_config("rag.vector_collection_name", "knowledge_base")
VECTOR_BATCH_SIZE = get_config("rag.batch_size", 500)
VECTOR_SEARCH_TOP_K = int(os.getenv("VECTOR_SEARCH_TOP_K", get_config("rag.search_top_k", 4)))
RAG_MAX_CHUNK_LENGTH = int(get_config("rag.max_chunk_length", 2000))
RAG_QUALITY_THRESHOLD = float(get_config("rag.quality_threshold", 0.55))
RAG_QUALITY_MIN_HITS = int(get_config("rag.quality_min_hits", 2))
RAG_QUALITY_MIN_SIMILARITY = float(get_config("rag.quality_min_similarity", 0.45))
RAG_QUALITY_MIN_SOURCE_DIVERSITY = float(get_config("rag.quality_min_source_diversity", 0.5))
RAG_EXPANSION_TOP_K = int(get_config("rag.expansion_top_k", 8))
RAG_EXPANSION_MIN_IMPROVEMENT = float(get_config("rag.expansion_min_improvement", 0.08))
RERANK_STRATEGY = get_config("rag.rerank_strategy", "model")
RERANK_MODEL_NAME = get_config("models.rerank", "BAAI/bge-reranker-base")

TOOL_RAG_TOP_K = int(get_config("tool.rag_top_k", VECTOR_SEARCH_TOP_K))
TOOL_DISCOVERY_TOP_K = int(get_config("tool.discovery_top_k", RAG_EXPANSION_TOP_K))
CALCULATOR_MAX_EXPRESSION_LEN = int(get_config("tool.calculator_max_expression_len", 100))
SYNTHESIS_MAX_EVIDENCE_CHARS = int(get_config("synthesis.max_evidence_chars", 800))

LLM_TEMPERATURE_KEYWORD_EXPANSION = float(get_config("llm.temperatures.keyword_expansion", 0.1))
LLM_TEMPERATURE_SEMANTIC_REWRITE = float(get_config("llm.temperatures.semantic_rewrite", 0.2))
LLM_TEMPERATURE_METADATA_FILTER = float(get_config("llm.temperatures.metadata_filter", 0.1))
LLM_TEMPERATURE_DISCOVERY = float(get_config("llm.temperatures.discovery", 0.6))
LLM_TEMPERATURE_TERMINOLOGY_REWRITE = float(get_config("llm.temperatures.terminology_rewrite", 0.1))
LLM_TEMPERATURE_TERMINOLOGY_FIX_INSAR = float(get_config("llm.temperatures.terminology_fix_insar", 0.2))

GRAPH_REPLAN_MAX_ATTEMPTS = int(get_config("graph.replan_max_attempts", 2))
GRAPH_REPLAN_ON_LOW_QUALITY = to_bool(get_config("graph.replan_on_low_quality", True), True)
GRAPH_REPLAN_LOW_QUALITY_THRESHOLD = float(get_config("graph.replan_low_quality_threshold", 0.3))
GRAPH_REPLAN_REQUIRE_EXPANSION = to_bool(get_config("graph.replan_require_expansion", True), True)
GRAPH_STEP_RESULT_MAX_CHARS = int(get_config("graph.step_result_max_chars", 9000))
ANSWER_CONFIDENCE_HIGH_THRESHOLD = float(get_config("graph.answer_confidence.high_threshold", 0.75))
ANSWER_CONFIDENCE_MEDIUM_THRESHOLD = float(get_config("graph.answer_confidence.medium_threshold", 0.45))
ANSWER_CONFIDENCE_NO_KB_FLOOR = float(get_config("graph.answer_confidence.no_kb_floor", 0.55))
ANSWER_CONFIDENCE_NEED_KB_RETRIEVAL_WEIGHT = float(get_config("graph.answer_confidence.need_kb_retrieval_weight", 0.65))
ANSWER_CONFIDENCE_NEED_KB_CONTEXT_WEIGHT = float(get_config("graph.answer_confidence.need_kb_context_weight", 0.35))
ANSWER_CONFIDENCE_REPLAN_PENALTY_STEP = float(get_config("graph.answer_confidence.replan_penalty_step", 0.08))
ANSWER_CONFIDENCE_REPLAN_PENALTY_CAP = float(get_config("graph.answer_confidence.replan_penalty_cap", 0.24))

VECTOR_SEARCH_CANDIDATE_MULTIPLIER = int(get_config("vector_search.candidate_multiplier", 2))
VECTOR_SEARCH_RRF_K = int(get_config("vector_search.rrf_k", 60))
VECTOR_SEARCH_MAX_CHUNKS_PER_DOC = int(get_config("vector_search.max_chunks_per_doc", 2))
VECTOR_SEARCH_PRERERANK_MAX_PER_DOC = int(get_config("vector_search.pre_rerank.max_per_doc", max(2, VECTOR_SEARCH_MAX_CHUNKS_PER_DOC + 1)))
_PRERERANK_MIN_SECTION_COVERAGE_RAW = float(get_config("vector_search.pre_rerank.min_section_coverage", 0.6))
VECTOR_SEARCH_PRERERANK_MIN_SECTION_COVERAGE = max(0.0, min(1.0, _PRERERANK_MIN_SECTION_COVERAGE_RAW))
VECTOR_SEARCH_MAX_WORKERS = int(get_config("vector_search.max_workers", 4))
VECTOR_SEARCH_CACHE_ENABLED = to_bool(get_config("vector_search.cache.enabled", True), True)
VECTOR_SEARCH_CACHE_TTL_SECONDS = int(get_config("vector_search.cache.ttl_seconds", 900))
VECTOR_SEARCH_CACHE_MAX_SIZE = int(get_config("vector_search.cache.max_size", 512))
VECTOR_HNSW_M = int(get_config("vector_search.hnsw.m", 32))
VECTOR_HNSW_EF_CONSTRUCTION = int(get_config("vector_search.hnsw.ef_construction", 200))
VECTOR_HNSW_EF_SEARCH = int(get_config("vector_search.hnsw.ef_search", 80))
VECTOR_HNSW_SPACE = str(get_config("vector_search.hnsw.space", "cosine"))
RETRIEVAL_METRICS_ENABLED = to_bool(get_config("retrieval.metrics.enabled", True), True)
RETRIEVAL_METRICS_WINDOW = int(get_config("retrieval.metrics.window", 200))
RETRIEVAL_METRICS_LOG_PATH = str(get_config("retrieval.metrics.log_path", os.path.join(BASE_DIR, "logs", "retrieval_metrics.jsonl")))
RETRIEVAL_FAST_PATH_ENABLED = to_bool(get_config("retrieval.fast_path.enabled", True), True)
RETRIEVAL_FAST_PATH_QUALITY_MARGIN = float(get_config("retrieval.fast_path.quality_margin", 0.1))
RETRIEVAL_FAST_PATH_SKIP_COMPLEX = to_bool(get_config("retrieval.fast_path.skip_for_complex_questions", True), True)
KB_WATCHER_ENABLED = to_bool(get_config("kb_watcher.enabled", True), True)
KB_WATCHER_POLL_INTERVAL_SECONDS = float(get_config("kb_watcher.poll_interval_seconds", 3.0))
KB_WATCHER_SETTLE_SECONDS = float(get_config("kb_watcher.settle_seconds", 2.0))
KB_WATCHER_NOTIFY_NO_CHANGE = to_bool(get_config("kb_watcher.notify_no_change", False), False)

KEYWORD_RERANK_STOP_WORDS = set(get_config("keyword_rerank.stop_words", {"的", "了", "和", "是", "就", "都", "而", "及", "与", "在", "这", "那", "有", "个", "之", "吗", "呢", "啊"}))

CHUNK_DYNAMIC_BASE_RATIO = float(get_config("chunking.dynamic.base_ratio", 0.12))
CHUNK_DYNAMIC_MAX_RATIO = float(get_config("chunking.dynamic.max_ratio", 0.28))
CHUNK_DYNAMIC_MIN_OVERLAP = int(get_config("chunking.dynamic.min_overlap", 30))
CHUNK_DYNAMIC_DIGIT_RATIO_THRESHOLD = float(get_config("chunking.dynamic.digit_ratio_threshold", 0.15))
CHUNK_DYNAMIC_SHORT_LINE_BONUS = int(get_config("chunking.dynamic.short_line_bonus", 30))
CHUNK_DYNAMIC_TABLE_BONUS = int(get_config("chunking.dynamic.table_bonus", 40))
CHUNK_DYNAMIC_DIGIT_BONUS = int(get_config("chunking.dynamic.digit_bonus", 30))
CHUNK_PARENT_LARGE_THRESHOLD = int(get_config("chunking.parent.large_threshold", 2200))
CHUNK_PARENT_LARGE_SIZE = int(get_config("chunking.parent.large_chunk_size", 1800))
CHUNK_PARENT_DEFAULT_SIZE = int(get_config("chunking.parent.default_chunk_size", 1300))
CHUNK_CHILD_NUMERIC_THRESHOLD = int(get_config("chunking.child.numeric_threshold", 60))
CHUNK_CHILD_NUMERIC_SIZE = int(get_config("chunking.child.numeric_chunk_size", 360))
CHUNK_CHILD_DEFAULT_SIZE = int(get_config("chunking.child.default_chunk_size", 420))

# Agent Configuration
MAX_CONTEXT_LEN = get_config("agent.max_context_len", 12000)
MAX_HISTORY_ROUNDS = get_config("agent.max_history_rounds", 8)

# Keywords & Rules
COMPLEX_KEYWORDS = get_config("keywords.complex", ["滑坡", "地质", "灾害", "诱发", "防治", "监测", "降雨"])

# Sets
SMALL_TALK_KEYWORDS = set(get_config("keywords.small_talk", {"在吗", "你是谁", "你好", "hi", "hello", "unknown", "未知"}))
SMALL_TALK_PUNCTUATION = set(get_config("keywords.small_talk_punctuation", {"?", "？", "!", "！", ".", "。", "...", "…"}))
MEMORY_QUERY_KEYWORDS = set(get_config("keywords.memory_query", {
    "我刚才", "刚才问", "上一个问题", "前面问", "你刚才", "你刚刚",
    "复述", "回顾", "我们聊了什么", "总结一下我们的对话", "总结我们刚才",
    "上次", "上一轮", "之前问", "之前说", "问了什么", "说了什么", "问了啥", "说了啥"
}))

MATH_KEYWORDS = get_config("keywords.math", ["计算", "多少", "+", "-", "*", "/", "加", "减", "乘", "除", "等于", "几"])
ANALYSIS_KEYWORDS = get_config("keywords.analysis", ["分析", "预测", "模型", "数据", "csv", "xlsx", "随机森林", "深度学习", "机器学习", "导入"])
COMPLEX_CALC_KEYWORDS = get_config("keywords.complex_calc", ["公式", "参数", "系数", "模型", "依据", "根据", "查", "资料"])

# Terminology Fixes
_replacements_raw = get_config("terminology.replacements", [])
if not _replacements_raw:
    # Default fallback if config is missing this section
    TERMINOLOGY_REPLACEMENTS = [
        ("地成学（InSAR）", "干涉合成孔径雷达（InSAR）"),
        ("InSAR（地物成像技术）", "干涉合成孔径雷达（InSAR）"),
        ("InSAR（热红外成像）", "干涉合成孔径雷达（InSAR）")
    ]
else:
    # Convert list of lists to list of tuples for compatibility
    TERMINOLOGY_REPLACEMENTS = [tuple(item) for item in _replacements_raw]

ALLOWED_ENGLISH_WORDS = set(get_config("terminology.allowed_english_words", {"InSAR", "SAR", "DNA", "GPS", "AI"}))
INSAR_BAD_PHRASES = set(get_config("terminology.insar_bad_phrases", {"热红外", "室内扫描", "地物成像", "多光谱", "光学", "红外", "地成学"}))

# Prompts Configuration
# Logic: Try to load from prompts.yaml first (preferred), then from config.yaml (legacy support)
_prompts_from_yaml = _prompts_config.get("prompts", {})
if not _prompts_from_yaml:
    _prompts_from_yaml = get_config("prompts", {})

PROMPTS = _prompts_from_yaml

# Planner Prompt
# Logic: Try to load from planner.yaml (preferred), then prompts.yaml (legacy), then default
_planner_prompts = _planner_config.get("prompts", {})
_planner_task_prompt = _planner_prompts.get("planner_task")

if not _planner_task_prompt:
    # Fallback to prompts.yaml if not in planner.yaml
    _planner_task_prompt = PROMPTS.get("planner_task")

PLANNER_PROMPT = _planner_task_prompt if _planner_task_prompt else """
你是一个 Tool Agent 的 Planner。

请将用户问题拆解为【步骤】，并为每一步选择最合适的工具：
可选工具：
- RAG（知识库检索）
- MEMORY（历史记忆）
- CALCULATOR（数学计算）
- DISCOVERY（深度洞察与新知推导）
- LLM（直接生成）

只输出 JSON，不要解释。

JSON 格式：
{{
  "intent": "...",
  "need_kb": true/false,
  "steps": [
    {{
      "task": "要做什么（给工具的输入）",
      "tool": "RAG / MEMORY / LLM / CALCULATOR / DISCOVERY"
    }}
  ]
}}

规则：
- 若问题涉及具体事实、论文/报告内容、定义/数据、需要引用资料，请将 need_kb 设为 true，并在 steps 里包含至少一步 RAG。
- 若问题是对先前对话的承接/追问（如“那…/刚才说的…/继续/再解释…”），请在 steps 中优先加入 MEMORY，用于提取相关上下文，再决定是否需要 RAG。
- 若问题是在询问对话本身（如“我刚才问了什么/你刚才说了什么/复述/回顾/总结我们刚才聊了什么/上次说了什么”），请使用 MEMORY（可直接一步 MEMORY），need_kb 设为 false。
- 若问题包含具体的数学算式（如“计算...”、“...等于多少”），请在 steps 中使用 CALCULATOR。
- 若用户明确要求“推导”、“分析”、“新发现”、“盲点”、“潜在规律”、“未知关联”或“深度洞察”，请务必使用 DISCOVERY，并将 need_kb 设为 true.
- 若主要是闲聊或纯创作且无需资料，need_kb 设为 false。

用户问题：
{question}
"""
