import asyncio
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
CONFIG_PATH = APP_ROOT / "config" / "config.yaml"
DEFAULT_CONFIG_PATH = APP_ROOT / "config" / "config.default.yaml"
RAG_IMPORT_ERROR: Optional[str] = None
DEFAULT_WEB_PORT = 18765
PORT_SCAN_LIMIT = 120

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
try:
    from core.agent_core import AgentCore  # noqa: E402
except Exception as exc:  # pragma: no cover
    AgentCore = None  # type: ignore[assignment]
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

class CreateSessionRequest(BaseModel):
    title: str = "新对话"

class RenameSessionRequest(BaseModel):
    title: str

class SaveConfigRequest(BaseModel):
    data: Dict[str, Any]

class RAGBridge:
    def __init__(self) -> None:
        self._agent: Optional[Any] = None
        self._lock = threading.RLock()

    def get_agent(self):
        if AgentCore is None:
            raise RuntimeError(
                "RAG 能力加载失败，请检查项目依赖与目录结构。"
                f" APP_ROOT={APP_ROOT}; import_error={RAG_IMPORT_ERROR or 'unknown'}"
            )
        if self._agent is None:
            with self._lock:
                if self._agent is None:
                    self._agent = AgentCore()
        return self._agent

    def with_agent(self, fn):
        with self._lock:
            return fn(self.get_agent())

    def reset_agent(self) -> None:
        with self._lock:
            agent = self._agent
            if agent is not None:
                try:
                    if hasattr(agent, "vector_store") and hasattr(agent.vector_store, "close"):
                        agent.vector_store.close()
                except Exception:
                    pass
                try:
                    if hasattr(agent, "db_manager") and hasattr(agent.db_manager, "close"):
                        agent.db_manager.close()
                except Exception:
                    pass
            self._agent = None


bridge = RAGBridge()
app = FastAPI(title="GeoClaw-LS WebUI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

@app.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/api/bootstrap")
def bootstrap():
    def _inner(agent: AgentCore):
        sessions = agent.db_manager.get_all_sessions()
        current_id = agent.get_active_session_id()
        history_text = agent.load_history_to_ui(limit=60, session_id=current_id) if current_id else ""
        return {
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": current_id,
            "history_messages": parse_history_text(history_text),
            "status": "就绪",
        }

    return bridge.with_agent(_inner)

@app.post("/api/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    def _inner(agent: AgentCore):
        if req.session_id:
            agent.switch_session(req.session_id)
        result = asyncio.run(agent.chat_async(question))
        return {
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "trace": result.get("trace", ""),
            "session_id": agent.get_active_session_id(),
        }

    return bridge.with_agent(_inner)

@app.get("/api/sessions")
def list_sessions():
    def _inner(agent: AgentCore):
        sessions = agent.db_manager.get_all_sessions()
        return {"sessions": [{"id": sid, "title": title} for sid, title, _ in sessions]}

    return bridge.with_agent(_inner)

@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    def _inner(agent: AgentCore):
        sid = agent.create_new_session(req.title.strip() or "新对话")
        return {"session_id": sid}

    return bridge.with_agent(_inner)

@app.post("/api/sessions/{session_id}/switch")
def switch_session(session_id: int):
    def _inner(agent: AgentCore):
        agent.switch_session(session_id)
        history = agent.load_history_to_ui(limit=60, session_id=session_id)
        return {"session_id": session_id, "history_messages": parse_history_text(history)}

    return bridge.with_agent(_inner)

@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: int, req: RenameSessionRequest):
    def _inner(agent: AgentCore):
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        agent.rename_session(session_id, title)
        return {"ok": True}

    return bridge.with_agent(_inner)

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    def _inner(agent: AgentCore):
        agent.delete_session(session_id)
        sessions = agent.db_manager.get_all_sessions()
        return {
            "ok": True,
            "sessions": [{"id": sid, "title": title} for sid, title, _ in sessions],
            "current_session_id": agent.get_active_session_id(),
        }

    return bridge.with_agent(_inner)

@app.get("/api/config")
def get_config():
    data = read_yaml(CONFIG_PATH)
    defaults = read_yaml(DEFAULT_CONFIG_PATH)
    return {
        "data": data,
        "defaults": defaults,
        "items": flatten_config(data),
    }


@app.put("/api/config")
def save_config(req: SaveConfigRequest):
    write_yaml(CONFIG_PATH, req.data)

    def _inner(agent: AgentCore):
        try:
            temp = req.data.get("models", {}).get("ollama", {}).get("temperature")
            if temp is not None:
                agent.temperature = float(temp)
        except Exception:
            pass
        return {"ok": True}

    return bridge.with_agent(_inner)

@app.post("/api/config/reset")
def reset_config():
    defaults = read_yaml(DEFAULT_CONFIG_PATH)
    if not defaults:
        raise HTTPException(status_code=404, detail="未找到默认配置")
    write_yaml(CONFIG_PATH, defaults)
    return {"ok": True}

@app.get("/api/config/export")
def export_config():
    data = read_yaml(CONFIG_PATH)
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return PlainTextResponse(content=dumped, media_type="text/yaml; charset=utf-8")

@app.post("/api/config/import")
async def import_config(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        loaded = yaml.safe_load(raw.decode("utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析 YAML 失败: {e}") from e
    if not isinstance(loaded, dict):
        raise HTTPException(status_code=400, detail="模板根节点必须是对象")
    write_yaml(CONFIG_PATH, loaded)
    return {"ok": True}

@app.post("/api/kb/sync")
def sync_kb():
    def _inner(agent: AgentCore):
        return agent.sync_knowledge_base_now()

    return bridge.with_agent(_inner)

@app.get("/api/kb/status")
def kb_status():
    def _inner(agent):
        return agent.get_knowledge_base_status()

    return bridge.with_agent(_inner)

@app.get("/api/kb/documents")
def kb_documents():
    def _inner(agent):
        return {"documents": agent.get_document_index_stats()}

    return bridge.with_agent(_inner)

@app.get("/api/kb/diagnostics")
def kb_diagnostics(limit: int = 20):
    safe_limit = max(1, min(limit, 100))

    def _inner(agent):
        return agent.get_retrieval_diagnostics(limit=safe_limit)

    return bridge.with_agent(_inner)

@app.post("/api/kb/rebuild")
def kb_rebuild():
    def _inner(agent):
        return agent.rebuild_knowledge_base_now()

    return bridge.with_agent(_inner)

@app.post("/api/system/reset")
def system_reset():
    def _inner(agent):
        agent.factory_reset()
        return {"ok": True, "message": "已触发系统重置，下一次请求将重新初始化引擎。"}

    result = bridge.with_agent(_inner)
    bridge.reset_agent()
    return result

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "app_root": str(APP_ROOT),
        "config_path": str(CONFIG_PATH),
        "default_config_path": str(DEFAULT_CONFIG_PATH),
        "config_exists": CONFIG_PATH.exists(),
        "agent_import_ok": AgentCore is not None,
        "agent_import_error": RAG_IMPORT_ERROR,
    }

def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False

def _pick_available_port(host: str, preferred_port: int, max_attempts: int) -> int:
    for offset in range(max_attempts):
        candidate = preferred_port + offset
        if _is_port_available(host, candidate):
            return candidate
    raise RuntimeError(
        f"端口占用：从 {preferred_port} 起连续 {max_attempts} 个端口均不可用，请释放端口后重试。"
    )

if __name__ == "__main__":
    host = "127.0.0.1"
    port = _pick_available_port(host, DEFAULT_WEB_PORT, PORT_SCAN_LIMIT)
    print(f"[GeoClaw-LS] WebUI 启动地址: http://{host}:{port}/")
    uvicorn.run("app:app", host=host, port=port, reload=False)
