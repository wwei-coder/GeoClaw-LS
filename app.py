import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from api.context import (
    ChatRequest,
    CreateSessionRequest,
    CreateTaskRequest,
    DEFAULT_WEB_PORT,
    ObservabilityToggleRequest,
    PORT_SCAN_LIMIT,
    RenameSessionRequest,
    RetryTaskRequest,
    STATIC_DIR,
    SaveConfigRequest,
    ResetPendingError,
    bridge,
    logger,
    read_observability_enabled_from_config,
)
from api.routes_chat import router as chat_router
from api.routes_config import router as config_router
from api.routes_files import router as files_router
from api.routes_health import router as health_router
from api.routes_kb import router as kb_router
from api.routes_observability import router as observability_router
from api.routes_sessions import router as sessions_router
from api.routes_tasks import router as tasks_router

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        from core.reset_handler import consume_reset_flag_once

        consume_reset_flag_once()
    except OSError as exc:
        logger.warning("系统重置标记消费失败，启动继续: %s", exc)

    try:
        desired_enabled = read_observability_enabled_from_config()
        from utils.phoenix_monitor import launch_phoenix_monitor, shutdown_phoenix_monitor

        if desired_enabled:
            launch_phoenix_monitor()
        else:
            shutdown_phoenix_monitor()
    except ImportError as exc:
        logger.warning("观测链路组件未安装，跳过启动: %s", exc)
    except OSError as exc:
        logger.warning("观测链路启动环境不可用，跳过启动: %s", exc)
    yield

app = FastAPI(title="GeoClaw-LS WebUI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(chat_router)
app.include_router(files_router)
app.include_router(tasks_router)
app.include_router(sessions_router)
app.include_router(config_router)
app.include_router(kb_router)
app.include_router(observability_router)
app.include_router(health_router)

@app.exception_handler(ResetPendingError)
async def handle_reset_pending(_request: Request, exc: ResetPendingError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})

def _is_port_available(bind_host: str, bind_port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, bind_port))
            return True
        except OSError:
            return False

def _pick_available_port(bind_host: str, preferred_port: int, max_attempts: int) -> int:
    for offset in range(max_attempts):
        candidate = preferred_port + offset
        if _is_port_available(bind_host, candidate):
            return candidate
    raise RuntimeError(
        f"端口占用：从 {preferred_port} 起连续 {max_attempts} 个端口均不可用，请释放端口后重试。"
    )

if __name__ == "__main__":
    server_host = "127.0.0.1"
    server_port = _pick_available_port(server_host, DEFAULT_WEB_PORT, PORT_SCAN_LIMIT)
    print(f"[GeoClaw-LS] WebUI 启动地址: http://{server_host}:{server_port}/")
    uvicorn.run("app:app", host=server_host, port=server_port, reload=False)

#  自检代码(终端执行)   Invoke-RestMethod http://127.0.0.1:18765/api/health
