import importlib
import os
import sqlite3
import sys
from typing import Iterable, List, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logger import logger
from config_runtime import (
    DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_BACKEND,
    FINGERPRINT_PATH,
    LLM_PROVIDER,
    OLLAMA_URL,
    VECTOR_DB_PATH,
)

LEGACY_TOP_LEVEL_PATHS = ("rag/", "knowledge/", "memory/")


def check_file(path: str, desc: str) -> bool:
    if os.path.exists(path):
        logger.info(f"✅ {desc} 存在: {path}")
        return True
    logger.error(f"❌ {desc} 缺失: {path}")
    return False


def check_import(module_name: str, desc: str, pip_hint: str | None = None) -> bool:
    try:
        importlib.import_module(module_name)
        logger.info(f"✅ 依赖可导入: {desc} ({module_name})")
        return True
    except Exception as exc:
        hint = f" | 安装: {pip_hint}" if pip_hint else ""
        logger.error(f"❌ 依赖导入失败: {desc} ({module_name}) -> {exc}{hint}")
        return False

def collect_boundary_paths() -> List[Tuple[str, str]]:
    return [
        ("api", "API 路由层目录"),
        ("services", "服务编排层目录"),
        ("agent/brain", "Brain 边界目录"),
        ("agent/runtime", "Runtime 边界目录"),
        ("agent/workflow", "Workflow 边界目录"),
        ("agent/policies", "Policies 边界目录"),
        ("tools", "工具层目录"),
        ("capabilities", "能力层目录"),
        ("storage", "存储层目录"),
        ("config_runtime.py", "运行配置事实源"),
        ("app.py", "应用入口"),
        ("config/config.yaml", "主配置文件"),
        ("config/prompts.yaml", "提示词配置"),
        ("config/planner.yaml", "Planner 配置"),
        ("data", "知识库目录"),
    ]

def _join_project_path(relative_path: str) -> str:
    return os.path.join(PROJECT_ROOT, relative_path.replace("/", os.sep))


def _build_optional_status_checks() -> List[Tuple[str, str]]:
    return [
        (os.path.join(PROJECT_ROOT, "workspace"), "workspace 运行目录"),
        (VECTOR_DB_PATH, "vector_db 运行目录"),
        (DB_PATH, "long_term_memory.db 数据库"),
        (FINGERPRINT_PATH, "doc_fingerprint.json 指纹文件"),
    ]

def _check_optional_runtime_state(paths: Iterable[Tuple[str, str]]) -> None:
    logger.info("[正在检查运行数据状态（只读，不修改）...]")
    for path, desc in paths:
        if os.path.exists(path):
            logger.info(f"✅ {desc} 已存在: {path}")
        else:
            logger.warning(f"⚠️ {desc} 当前不存在: {path}（首次运行或尚未生成时可接受）")

def _check_local_embedding_model() -> bool:
    if EMBEDDING_BACKEND != "sentence_transformers":
        logger.info(f"✅ 当前嵌入后端为 {EMBEDDING_BACKEND}，无需检查本地 sentence-transformers 模型目录")
        return True
    if check_file(DEFAULT_EMBEDDING_MODEL, "本地嵌入模型"):
        return True
    logger.warning("⚠️ 本地嵌入模型缺失；若当前环境依赖 sentence-transformers，本项属于真实故障")
    return False

def _build_dependency_checks() -> Sequence[Tuple[str, str]]:
    checks: List[Tuple[str, str]] = [
        ("requests", "HTTP 请求"),
        ("yaml", "YAML 解析"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("chromadb", "向量数据库"),
        ("jieba", "中文分词"),
        ("fitz", "PDF 解析 (PyMuPDF)"),
        ("docx", "Word 解析（python-docx）"),
        ("langgraph", "LangGraph 编排"),
    ]
    if EMBEDDING_BACKEND == "sentence_transformers":
        checks.append(("sentence_transformers", "Embedding 模型"))
    return checks

def _check_runtime_config_import() -> bool:
    logger.info("[正在检查 config_runtime 关键常量...]")
    try:
        runtime = importlib.import_module("config_runtime")
        required = [
            "CONFIG_PATH",
            "PROMPTS_PATH",
            "PLANNER_PATH",
            "DATA_DIR",
            "DB_PATH",
            "VECTOR_DB_PATH",
            "OLLAMA_URL",
            "LLM_PROVIDER",
        ]
        missing = [name for name in required if not hasattr(runtime, name)]
        if missing:
            logger.error(f"❌ config_runtime 缺少关键常量: {missing}")
            return False
        logger.info("✅ config_runtime 关键常量可导入")
        logger.info(f"✅ 模型提供方配置可读: LLM_PROVIDER={LLM_PROVIDER}, OLLAMA_URL={OLLAMA_URL}")
        return True
    except Exception as exc:
        logger.error(f"❌ config_runtime 导入失败: {exc}")
        return False

def _check_app_entrypoint() -> bool:
    logger.info("[正在检查 app.py 可导入状态...]")
    try:
        module = importlib.import_module("app")
        app_obj = getattr(module, "app", None)
        if app_obj is None:
            logger.error("❌ app.py 已导入，但未暴露 app 对象")
            return False
        try:
            fastapi_module = importlib.import_module("fastapi")
            fastapi_cls = getattr(fastapi_module, "FastAPI", None)
            if fastapi_cls is not None and not isinstance(app_obj, fastapi_cls):
                logger.error("❌ app.py 已导入，但 app 不是 FastAPI 实例")
                return False
        except Exception:
            logger.warning("⚠️ FastAPI 类型校验跳过：无法导入 fastapi 类型")
        logger.info("✅ app.py 可导入，且暴露 FastAPI app")
        return True
    except Exception as exc:
        logger.error(f"❌ app.py 导入失败: {exc}")
        return False

def _check_boundary_imports() -> bool:
    logger.info("[正在尝试导入当前主边界模块...]")
    modules = [
        "api.routes_health",
        "services.agent_service",
        "agent.brain",
        "agent.runtime",
        "agent.workflow",
        "agent.policies",
        "tools.registry",
        "capabilities.registry",
        "storage.sqlite.task_repository",
    ]
    ok = True
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            logger.info(f"✅ 边界模块可导入: {module_name}")
        except Exception as exc:
            logger.error(f"❌ 边界模块导入失败: {module_name} -> {exc}")
            ok = False
    return ok

def _build_ollama_tags_url() -> str:
    if OLLAMA_URL.endswith("/api/generate"):
        return OLLAMA_URL[: -len("/api/generate")] + "/api/tags"
    return OLLAMA_URL.rstrip("/") + "/api/tags"

def _check_llm_config_and_optional_probe() -> bool:
    logger.info("[正在检查模型访问配置...]")
    if not OLLAMA_URL:
        logger.error("❌ 当前使用 Ollama，但 OLLAMA_URL 不可读")
        return False

    logger.info(f"✅ Ollama 地址配置可读: {OLLAMA_URL}")
    try:
        requests = importlib.import_module("requests")
        tags_url = _build_ollama_tags_url()
        resp = requests.get(tags_url, timeout=3)
        if resp.status_code == 200:
            logger.info(f"✅ Ollama 服务可访问: {tags_url}")
        else:
            logger.warning(f"⚠️ Ollama 返回状态码 {resp.status_code}: {tags_url}（环境提示，不视为结构故障）")
    except Exception as exc:
        logger.warning(f"⚠️ Ollama 当前不可访问: {exc}（环境提示，不视为结构故障）")
    return True


def _check_sqlite_runtime_pragmas() -> bool:
    logger.info("[正在检查 SQLite 运行时 PRAGMA...]")
    if not os.path.exists(DB_PATH):
        logger.warning("⚠️ SQLite 数据库文件当前不存在，跳过 PRAGMA 检查（首次运行时可接受）")
        return True
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=1.0)
        try:
            pragmas = {}
            for name in ("busy_timeout", "journal_mode", "synchronous"):
                row = conn.execute(f"PRAGMA {name}").fetchone()
                pragmas[name] = row[0] if row else None
            logger.info(
                "✅ SQLite PRAGMA 可读: "
                f"busy_timeout={pragmas['busy_timeout']}, "
                f"journal_mode={pragmas['journal_mode']}, "
                f"synchronous={pragmas['synchronous']}"
            )
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"⚠️ SQLite PRAGMA 检查失败: {exc}（环境提示，不视为结构故障）")
        return True

def run_health_check() -> bool:
    logger.info("====== 开始系统完整性检查 ======")
    logger.info(f"🐍 Python 解释器路径: {sys.executable}")
    logger.info(f"🐍 Python 版本: {sys.version.split()[0]}")

    all_ok = True

    logger.info("[正在检查当前主边界文件与目录...]")
    for relative_path, desc in collect_boundary_paths():
        if any(relative_path.startswith(prefix) for prefix in LEGACY_TOP_LEVEL_PATHS):
            logger.error(f"❌ 健康检查仍引用旧顶层路径: {relative_path}")
            all_ok = False
            continue
        if not check_file(_join_project_path(relative_path), desc):
            all_ok = False

    _check_optional_runtime_state(_build_optional_status_checks())

    logger.info("[正在检查第三方依赖...]")
    pip_prefix = f'"{sys.executable}" -m pip install '
    for module_name, desc in _build_dependency_checks():
        if not check_import(module_name, desc, pip_prefix + module_name):
            all_ok = False

    if not _check_runtime_config_import():
        all_ok = False
    if not _check_app_entrypoint():
        all_ok = False
    if not _check_boundary_imports():
        all_ok = False
    if not _check_local_embedding_model():
        all_ok = False
    if not _check_llm_config_and_optional_probe():
        all_ok = False
    if not _check_sqlite_runtime_pragmas():
        all_ok = False

    logger.info("====== 检查结束 ======")
    return all_ok

if __name__ == "__main__":
    ok = run_health_check()
    if ok:
        logger.info("✅ 健康检查通过（HEALTH CHECK PASS）")
        sys.exit(0)
    logger.error("❌ 健康检查失败（HEALTH CHECK FAIL）")
    sys.exit(1)
