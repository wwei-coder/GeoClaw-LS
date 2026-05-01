from fastapi import APIRouter
from api.context import AGENT_CORE_CTOR, APP_ROOT, CONFIG_PATH, DEFAULT_CONFIG_PATH, RAG_IMPORT_ERROR

router = APIRouter()


@router.get("/api/health")
def health():
    return {
        "ok": True,
        "app_root": str(APP_ROOT),
        "config_path": str(CONFIG_PATH),
        "default_config_path": str(DEFAULT_CONFIG_PATH),
        "config_exists": CONFIG_PATH.exists(),
        "agent_import_ok": AGENT_CORE_CTOR is not None,
        "agent_import_error": RAG_IMPORT_ERROR,
    }
