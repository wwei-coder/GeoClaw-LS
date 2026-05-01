from utils.ollama_client import ask_ollama, ask_ollama_async
import json
import re
from core.config import PLANNER_PROMPT
from utils.logger import logger

ALLOWED_TOOLS = {"RAG", "MEMORY", "LLM", "CALCULATOR", "DISCOVERY", "DATA_PROFILE", "FILE_INSPECTOR"}
DATA_TOOLS = {"DATA_PROFILE", "FILE_INSPECTOR"}


def _has_file_signal(text: str) -> bool:
    q = (text or "").lower()
    keywords = [
        "file_id",
        "上传",
        "已上传",
        "这个文件",
        "该文件",
        "数据文件",
        "csv",
        "excel",
        "xlsx",
        "xls",
        "json",
        "txt",
        "表格",
    ]
    if any(k in q for k in keywords):
        return True
    return bool(re.search(r"\bfile[_-]?id\b", q, flags=re.IGNORECASE))


def _process_planner_response(raw_response: str, question: str) -> dict:
    """Helper to process and sanitize LLM response for planning.

    容错策略：
    - 清理 Markdown 代码块与不可见字符；
    - 解析失败时尝试截取最外层 JSON；
    - 非法工具自动回退 LLM；
    - 文件工具在无 file 信号时自动回退 LLM。
    """
    raw = raw_response.strip()
    
    # Clean up markdown code block syntax more robustly
    if "```json" in raw:
        raw = raw.split("```json")[-1]
    if "```" in raw:
        raw = raw.split("```")[0]

    text = raw.strip()
    sanitized = "".join(ch for ch in text if (ord(ch) >= 32) or ch in "\n\r\t")
    sanitized = sanitized.replace("\u2028", "").replace("\u2029", "").strip()
    
    plan = {}
    try:
        plan = json.loads(sanitized)
    except Exception as e:
        logger.warning(f"[Planner] 首次 JSON 解析失败: {e}")
        start = sanitized.find("{")
        end = sanitized.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                plan = json.loads(sanitized[start:end + 1])
            except Exception as e:
                logger.warning(f"[Planner] 二次 JSON 解析失败: {e}")
        
    if not plan:
         # Fallback if JSON parsing fails completely
         return {
             "intent": "unknown",
             "need_kb": False,
             "steps": [{"task": question, "tool": "LLM"}]
         }

    if "need_kb" not in plan:
        plan["need_kb"] = False

    steps = plan.get("steps")
    if not isinstance(steps, list):
        steps = []

    cleaned = []
    file_signal = _has_file_signal(question)
    for s in steps:
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool", "LLM")).upper().strip()
        task = str(s.get("task", "")).strip()
        
        # 1. 自动修正工具名称（模糊匹配）
        if "CALC" in tool or "MATH" in tool:
            tool = "CALCULATOR"
        elif "MEM" in tool or "HIST" in tool:
            tool = "MEMORY"
        elif "RAG" in tool or "SEARCH" in tool or "KB" in tool:
            tool = "RAG"
        elif "DISC" in tool or "ANALY" in tool:
            tool = "DISCOVERY"
            
        if not task or "要做什么" in task or "给工具的输入" in task:
            task = question
            
        if tool not in ALLOWED_TOOLS:
            tool = "LLM"
        if tool in DATA_TOOLS and not file_signal:
            logger.info("[Planner] 数据工具缺少文件意图信号，降级为 LLM")
            tool = "LLM"
        cleaned.append({"tool": tool, "task": task})

    if not cleaned:
        cleaned = [{"task": question, "tool": "LLM"}]

    plan["steps"] = cleaned
    return plan

async def plan_task_async(question: str):
    """Async version of plan_task"""
    prompt = PLANNER_PROMPT.format(question=question)
    raw = await ask_ollama_async(prompt)
    return _process_planner_response(raw, question)

def plan_task(question: str):
    prompt = PLANNER_PROMPT.format(question=question)
    raw = ask_ollama(prompt)
    return _process_planner_response(raw, question)
