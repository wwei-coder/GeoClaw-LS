import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"
RAG_IMPORT_ERROR: Optional[str] = None
DEFAULT_WEB_PORT = 18765
PORT_SCAN_LIMIT = 120
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
logger = logging.getLogger(__name__)
RESET_PENDING_MESSAGE = "系统已标记重置，请重启服务后继续使用。"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
AGENT_CORE_CTOR: Optional[type[Any]] = None
try:
    from core.agent_core import AgentCore as ImportedAgentCore  # noqa: E402

    AGENT_CORE_CTOR = ImportedAgentCore
except (ImportError, ModuleNotFoundError, AttributeError, RuntimeError, OSError) as exc:  # pragma: no cover
    RAG_IMPORT_ERROR = str(exc)

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

class ResetPendingError(RuntimeError):
    pass

class RAGBridge:
    def __init__(self) -> None:
        self._agent: Optional[Any] = None
        self._lock = threading.RLock()
        self._reset_pending = False

    def _ensure_available(self) -> None:
        if self._reset_pending:
            raise ResetPendingError(RESET_PENDING_MESSAGE)

    def get_agent(self) -> Any:
        from core.reset_handler import consume_reset_flag_once

        self._ensure_available()
        consume_reset_flag_once()
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
            self._ensure_available()
            return fn(self.get_agent())

    def with_agent_readonly(self, fn: Callable[[Any], Any]) -> Any:
        """执行只读调用：仅保证 agent 已初始化，不持有全局执行锁。"""
        self._ensure_available()
        agent = self.get_agent()
        return fn(agent)

    def reset_agent(self) -> None:
        self._close_agent_resources()

    def enter_reset_pending(self) -> None:
        with self._lock:
            self._close_agent_resources()
            self._reset_pending = True

    def is_reset_pending(self) -> bool:
        with self._lock:
            return self._reset_pending

    def _close_agent_resources(self) -> None:
        with self._lock:
            agent = self._agent
            if agent is not None:
                try:
                    if hasattr(agent, "task_runner") and agent.task_runner is not None:
                        agent.task_runner.shutdown(wait=False)
                except (AttributeError, OSError, RuntimeError, TypeError):
                    pass
                try:
                    if hasattr(agent, "vector_store") and hasattr(agent.vector_store, "close"):
                        agent.vector_store.close()
                except (AttributeError, OSError, RuntimeError):
                    pass
                try:
                    if hasattr(agent, "db_manager") and hasattr(agent.db_manager, "close"):
                        agent.db_manager.close()
                except (AttributeError, OSError, RuntimeError):
                    pass
            self._agent = None

bridge = RAGBridge()
