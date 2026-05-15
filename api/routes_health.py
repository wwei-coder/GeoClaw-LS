from fastapi import APIRouter
from api.context import AGENT_CORE_CTOR, APP_ROOT, RAG_IMPORT_ERROR
from services.config_io import CONFIG_PATH, DEFAULT_CONFIG_PATH
from core.reset_handler import is_reset_pending
from utils.logger import logger

router = APIRouter()

@router.get("/api/health")
def health():
    payload = {
        "ok": True,
        "app_root": str(APP_ROOT),
        "config_path": str(CONFIG_PATH),
        "default_config_path": str(DEFAULT_CONFIG_PATH),
        "config_exists": CONFIG_PATH.exists(),
        "agent_import_ok": AGENT_CORE_CTOR is not None,
        "agent_import_error": RAG_IMPORT_ERROR,
        "reset_pending": is_reset_pending(),
    }
    logger.info(
        "[Health] /api/health accessed | app_root={} | config_exists={} | agent_import_ok={}",
        payload["app_root"],
        payload["config_exists"],
        payload["agent_import_ok"],
    )
    return payload
