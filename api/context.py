import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import yaml
from pydantic import BaseModel

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"
CONFIG_PATH = APP_ROOT / "config" / "config.yaml"
DEFAULT_CONFIG_PATH = APP_ROOT / "config" / "config.default.yaml"
RAG_IMPORT_ERROR: Optional[str] = None
DEFAULT_WEB_PORT = 18765
PORT_SCAN_LIMIT = 120
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
logger = logging.getLogger(__name__)

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
AGENT_CORE_CTOR: Optional[type[Any]] = None
try:
    from core.agent_core import AgentCore as ImportedAgentCore  # noqa: E402

    AGENT_CORE_CTOR = ImportedAgentCore
except (ImportError, ModuleNotFoundError, AttributeError, RuntimeError, OSError) as exc:  # pragma: no cover
    RAG_IMPORT_ERROR = str(exc)

COMMON_PREFIXES = (
    "agent.max_context_len",
    "agent.max_history_rounds",
    "models.provider",
    "models.api.base_url",
    "models.api.api_key",
    "models.api.model",
    "models.api.timeout",
    "models.api.stream_timeout",
    "models.api.max_tokens",
    "models.ollama.url",
    "models.ollama.model",
    "models.ollama.temperature",
    "models.ollama.timeout",
    "models.ollama.stream_timeout",
    "rag.search_top_k",
    "rag.quality_threshold",
    "rag.rerank_strategy",
    "rag.expansion_top_k",
    "rag.expansion_min_improvement",
    "tool.rag_top_k",
    "tool.discovery_top_k",
    "vector_search.candidate_multiplier",
    "vector_search.rrf_k",
    "vector_search.max_chunks_per_doc",
)

HIDDEN_PREFIXES = (
    "models.provider",
    "models.api.",
    "llm.temperatures.",
    "vector_search.hnsw.",
    "graph.answer_confidence.",
    "chunking.",
    "keyword_rerank.",
    "retrieval.metrics.",
    "terminology.",
    "system.hf_endpoint",
)

PARAM_HINTS = {
    "models.provider": ("作用：选择大模型提供方", "建议：本地用 ollama；云端接口用 openai_compatible"),
    "models.api.base_url": ("作用：远程 API 基础地址", "建议：填写服务商提供的 v1 地址"),
    "models.api.api_key": ("作用：远程 API 鉴权密钥", "建议：填写后妥善保管"),
    "models.api.model": ("作用：远程 API 模型名", "建议：填写服务商可用模型"),
    "models.api.timeout": ("作用：远程 API 非流式超时（秒）", "建议：30~180；网络不稳可调高"),
    "models.api.stream_timeout": ("作用：远程 API 流式超时（秒）", "建议：60~300；长回答建议更高"),
    "models.api.max_tokens": ("作用：远程 API 最大输出 token", "建议：0 表示由服务端默认控制"),
    "models.ollama.model": ("作用：选择回复模型", "建议：优先 7B/14B 常用模型"),
    "models.ollama.url": ("作用：Ollama 服务地址", "建议：本机默认 http://localhost:11434/api/generate"),
    "models.ollama.temperature": ("作用：控制回答发散度", "建议：0.2~0.8"),
    "rag.search_top_k": ("作用：首轮召回片段数量", "建议：3~8"),
    "rag.quality_threshold": ("作用：检索质量阈值", "建议：0.45~0.70"),
}

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[int] = None
    file_id: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None

class CreateTaskRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    file_id: Optional[str] = None
    run_mode: str = "background"

class RetryTaskRequest(BaseModel):
    step_id: Optional[str] = None

class CreateSessionRequest(BaseModel):
    title: str = "新对话"

class RenameSessionRequest(BaseModel):
    title: str

class SaveConfigRequest(BaseModel):
    data: Dict[str, Any]

class ObservabilityToggleRequest(BaseModel):
    enabled: bool

class RAGBridge:
    def __init__(self) -> None:
        self._agent: Optional[Any] = None
        self._lock = threading.RLock()

    def get_agent(self) -> Any:
        if AGENT_CORE_CTOR is None:
            raise RuntimeError(
                "RAG 能力加载失败，请检查项目依赖与目录结构。"
                f" APP_ROOT={APP_ROOT}; import_error={RAG_IMPORT_ERROR or 'unknown'}"
            )
        if self._agent is None:
            with self._lock:
                if self._agent is None:
                    self._agent = AGENT_CORE_CTOR()
        return self._agent

    def with_agent(self, fn: Callable[[Any], Any]) -> Any:
        with self._lock:
            return fn(self.get_agent())

    def reset_agent(self) -> None:
        with self._lock:
            agent = self._agent
            if agent is not None:
                try:
                    if hasattr(agent, "vector_store") and hasattr(agent.vector_store, "close"):
                        agent.vector_store.close()
                except (AttributeError, OSError, RuntimeError):
                    pass
                try:
                    if hasattr(agent, "task_runner") and agent.task_runner is not None:
                        agent.task_runner.shutdown()
                except (AttributeError, OSError, RuntimeError):
                    pass
                try:
                    if hasattr(agent, "db_manager") and hasattr(agent.db_manager, "close"):
                        agent.db_manager.close()
                except (AttributeError, OSError, RuntimeError):
                    pass
            self._agent = None

bridge = RAGBridge()

def read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} 根节点必须为对象")
    return loaded

def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

def read_observability_enabled_from_config() -> bool:
    data = read_yaml(CONFIG_PATH)
    obs = data.get("observability", {})
    if not isinstance(obs, dict):
        return False
    return bool(obs.get("enabled", False))

def write_observability_enabled_to_config(enabled: bool) -> None:
    data = read_yaml(CONFIG_PATH)
    obs = data.get("observability")
    if not isinstance(obs, dict):
        obs = {}
    obs["enabled"] = bool(enabled)
    data["observability"] = obs
    write_yaml(CONFIG_PATH, data)

def iter_leaf_items(node: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    if isinstance(node, dict):
        out: List[Tuple[str, Any]] = []
        for key, value in node.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(iter_leaf_items(value, next_prefix))
        return out
    return [(prefix, node)]

def parse_history_text(history_text: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    lines = (history_text or "").split("\n")
    role = None
    buf = ""
    for line in lines:
        if line.startswith("用户："):
            if role and buf.strip():
                messages.append({"role": role, "text": buf.strip()})
            role = "user"
            buf = line[3:]
        elif line.startswith("助手："):
            if role and buf.strip():
                messages.append({"role": role, "text": buf.strip()})
            role = "assistant"
            buf = line[3:]
        else:
            buf = f"{buf}\n{line}" if buf else line
    if role and buf.strip():
        messages.append({"role": role, "text": buf.strip()})
    return messages

def serialize_task(task: Any) -> Dict[str, Any]:
    if task is None:
        return {}
    if hasattr(task, "to_dict"):
        payload = task.to_dict()
    elif isinstance(task, dict):
        payload = dict(task)
    else:
        payload = {}
    payload["answer_preview"] = str(payload.get("final_answer", "") or "")[:200]
    return payload

def compute_progress(task: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_status = str((task or {}).get("status") or "pending").lower()
    total = len(steps or [])
    completed = 0
    failed = 0
    running = 0
    for s in steps or []:
        status = str((s or {}).get("status") or "pending").lower()
        if status == "success":
            completed += 1
        elif status == "failed":
            failed += 1
        elif status == "running":
            running += 1
    if task_status == "pending":
        percent = 0
    elif task_status == "success":
        percent = 100
    elif total <= 0:
        percent = 0 if task_status in {"pending", "running"} else 100
    else:
        percent = int(max(0.0, min(100.0, ((completed + failed) / float(total)) * 100.0)))
        if task_status == "running":
            percent = max(1, min(99, percent))
    return {
        "total_steps": total,
        "completed_steps": completed,
        "failed_steps": failed,
        "running_steps": running,
        "percent": percent,
    }

def serialize_step(step: Any) -> Dict[str, Any]:
    if step is None:
        return {}
    if hasattr(step, "to_dict"):
        return step.to_dict()
    if isinstance(step, dict):
        return dict(step)
    return {}

def serialize_artifact(artifact: Any) -> Dict[str, Any]:
    if artifact is None:
        return {}
    if hasattr(artifact, "to_dict"):
        payload = artifact.to_dict()
    elif isinstance(artifact, dict):
        payload = dict(artifact)
    else:
        payload = {}
    artifact_id = str(payload.get("id") or "")
    url = str(payload.get("url") or f"/api/artifacts/{artifact_id}" if artifact_id else "")
    payload["url"] = url
    payload["download_url"] = url
    raw_path = str(payload.get("path") or "")
    if ":" in raw_path or raw_path.startswith("/"):
        payload["path"] = Path(raw_path).name
    return payload

def is_tunable(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in HIDDEN_PREFIXES)

def infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"

def flatten_config(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for top_key, top_value in data.items():
        items = iter_leaf_items(top_value, top_key) if isinstance(top_value, dict) else [(top_key, top_value)]
        for full_path, value in items:
            if not is_tunable(full_path):
                continue
            hint = PARAM_HINTS.get(full_path)
            rows.append(
                {
                    "group": str(top_key),
                    "path": full_path,
                    "value": value,
                    "type": infer_type(value),
                    "is_common": any(full_path.startswith(prefix) for prefix in COMMON_PREFIXES),
                    "hint": {"title": hint[0], "recommend": hint[1]} if hint else None,
                }
            )
    return rows
