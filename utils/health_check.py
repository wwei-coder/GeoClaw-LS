import os
import sys
import importlib
from utils.logger import logger
from core.config import (
    EMBEDDING_BACKEND,
    DEFAULT_EMBEDDING_MODEL,
    LLM_PROVIDER,
    OLLAMA_URL,
    LLM_API_BASE_URL,
    LLM_API_KEY,
)

def check_file(path, desc):
    if os.path.exists(path):
        logger.info(f"✅ {desc} 存在: {os.path.basename(path)}")
        return True
    else:
        logger.error(f"❌ {desc} 缺失: {path}")
        return False

def check_import(module_name, desc, pip_hint=None):
    try:
        importlib.import_module(module_name)
        logger.info(f"✅ 依赖可导入: {desc} ({module_name})")
        return True
    except Exception as e:
        hint = f" | 安装: {pip_hint}" if pip_hint else ""
        logger.error(f"❌ 依赖导入失败: {desc} ({module_name}) -> {e}{hint}")
        return False

def run_health_check():
    logger.info("====== 开始系统完整性检查 ======")
    logger.info(f"🐍 Python 解释器路径: {sys.executable}")
    logger.info(f"🐍 Python 版本: {sys.version.split()[0]}")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    files_to_check = [
        ("core/agent_core.py", "核心逻辑"),
        ("core/config.py", "系统配置"),
        ("core/graph_agent.py", "图代理逻辑"),
        ("core/planner.py", "规划器模块"),
        ("memory/vector_store.py", "向量库模块"),
        ("memory/rerank.py", "重排序模块"),
        ("knowledge/knowledge_loader.py", "知识库解析"),
        ("utils/download_model.py", "模型下载脚本"),
        ("utils/ollama_client.py", "LLM 客户端"),
    ]

    all_ok = True
    for fname, desc in files_to_check:
        if not check_file(os.path.join(base_dir, fname), desc):
            all_ok = False

    if EMBEDDING_BACKEND == "sentence_transformers":
        model_path = DEFAULT_EMBEDDING_MODEL
        if not check_file(model_path, "本地嵌入模型"):
            logger.warning("⚠️ 提示: 本地模型缺失，请运行 'python utils\\download_model.py' 进行下载。")
            all_ok = False

    logger.info("[正在检查第三方依赖...]")
    pip_prefix = f'"{sys.executable}" -m pip install '
    deps = [
        ("requests", "HTTP 请求", pip_prefix + "requests"),
        ("chromadb", "向量数据库", pip_prefix + "chromadb"),
        ("sentence_transformers", "Embedding 模型", pip_prefix + "sentence-transformers"),
        ("jieba", "中文分词", pip_prefix + "jieba"),
        ("fitz", "PDF 解析 (PyMuPDF)", pip_prefix + "pymupdf"),
        ("docx", "Word 解析（python-docx）", pip_prefix + "python-docx"),
        ("langchain", "LangChain 框架", pip_prefix + "langchain"),
        ("langgraph", "LangGraph 编排", pip_prefix + "langgraph"),
        ("customtkinter", "UI 框架", pip_prefix + "customtkinter"),
    ]

    for module_name, desc, hint in deps:
        if not check_import(module_name, desc, hint):
            all_ok = False

    if LLM_PROVIDER in {"openai", "openai_compatible", "api", "remote"}:
        logger.info("[正在检查 API 模型配置...]")
        if not LLM_API_BASE_URL:
            logger.error("❌ 当前使用 API 模型，但 models.api.base_url 未配置")
            all_ok = False
        else:
            logger.info(f"✅ API Base URL 已配置: {LLM_API_BASE_URL}")
        if not LLM_API_KEY:
            logger.error("❌ 当前使用 API 模型，但 models.api.api_key 未配置")
            all_ok = False
        else:
            logger.info("✅ API Key 已配置")
    else:
        logger.info("[正在检查 Ollama 服务...]")
        try:
            requests = importlib.import_module("requests")
            tags_url = OLLAMA_URL.replace("/api/generate", "/api/tags")
            resp = requests.get(tags_url, timeout=3)
            if resp.status_code == 200:
                logger.info(f"✅ Ollama 服务可访问: {tags_url}")
            else:
                logger.warning(f"⚠️ Ollama 返回状态码: {resp.status_code}")
                all_ok = False
        except Exception as e:
            logger.error(f"❌ Ollama 不可访问: {e}")
            logger.warning("⚠️ 提示: 请确认已启动 Ollama 服务")
            all_ok = False

    logger.info("[正在尝试导入核心模块...]")
    # Add project root to path
    sys.path.append(base_dir)
    try:
        importlib.import_module("core.agent_core")
        importlib.import_module("memory.vector_store")
        importlib.import_module("utils.ollama_client")
        logger.info("✅ 核心模块导入成功")
    except ImportError as e:
        logger.error(f"❌ 导入失败 (缺包?): {e}")
        all_ok = False
    except Exception as e:
        logger.error(f"❌ 导入时发生错误: {e}")
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