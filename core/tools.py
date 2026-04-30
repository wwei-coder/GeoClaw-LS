from typing import Dict, Any
import ast
from core.config import (
    RAG_MAX_CHUNK_LENGTH,
    TOOL_RAG_TOP_K,
    CALCULATOR_MAX_EXPRESSION_LEN,
    TOOL_DISCOVERY_TOP_K,
    LLM_TEMPERATURE_DISCOVERY
)
from utils.logger import logger


_ALLOWED_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}

_ALLOWED_UNARY_OPS = {
    ast.UAdd: lambda x: +x,
    ast.USub: lambda x: -x,
}
_NUM_NODE_TYPES = tuple(t for t in (getattr(ast, "Num", None),) if t)


def _safe_eval_node(node):
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("仅支持数字常量")
    if _NUM_NODE_TYPES and isinstance(node, _NUM_NODE_TYPES):
        return node.n
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARY_OPS.get(type(node.op))
        if not op:
            raise ValueError("仅支持正负号")
        return op(_safe_eval_node(node.operand))
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BIN_OPS.get(type(node.op))
        if not op:
            raise ValueError("仅支持加减乘除")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return op(left, right)
    raise ValueError("表达式包含不支持的语法")


def _safe_eval_expression(expr: str):
    parsed = ast.parse(expr, mode="eval")
    return _safe_eval_node(parsed)

def tool_rag(query: str, agent) -> str:
    chunks = agent.vector_store.search(query, top_k=TOOL_RAG_TOP_K)
    if not chunks:
        return "[RAG] 未检索到相关资料"
    lines = []
    for c in chunks:
        content = c.get("content", "")
        if len(content) > RAG_MAX_CHUNK_LENGTH:
            content = content[:RAG_MAX_CHUNK_LENGTH] + "…"
        cid = c.get("id", "")
        doc = c.get("doc_name", "")
        head = f"【{doc}｜{cid}】" if cid else f"【{doc}】"
        lines.append(head + "\n" + content)
    return "\n\n".join(lines)


def tool_memory(_query: str, agent) -> str:
    summary = getattr(agent, "summary_memory", "") or ""
    try:
        sid = agent.get_active_session_id() if hasattr(agent, "get_active_session_id") else getattr(agent, "session_id", None)
        recent = agent.load_history_to_ui(limit=6, session_id=sid)
    except Exception as e:
        logger.warning(f"[Tools] 读取最近对话失败: {e}")
        recent = ""
    short = "\n".join(getattr(agent, "short_memory", []) or [])

    parts = []
    if summary.strip():
        parts.append("【摘要记忆】\n" + summary.strip())
    if recent.strip():
        parts.append("【最近对话】\n" + recent.strip())
    if short.strip():
        parts.append("【短期记忆】\n" + short.strip())
    return "\n\n".join(parts)


def tool_llm(prompt: str, _agent) -> str:
    from utils.ollama_client import ask_ollama
    return ask_ollama(prompt)


def tool_calculator(query: str, _agent) -> str:
    try:
        if len(query) > CALCULATOR_MAX_EXPRESSION_LEN:
            return "[计算错误] 表达式过长，请简化。"

        query = query.replace("加", "+").replace("减", "-").replace("乘", "*").replace("除", "/")
        safe_chars = set("0123456789.+-*/() ")
        cleaned = "".join([c for c in query if c in safe_chars])
        if not cleaned.strip():
            return "[计算错误] 未找到有效的数学表达式"

        if "**" in cleaned:
             return "[计算错误] 不支持幂运算 (**)，请使用乘法。"

        result = _safe_eval_expression(cleaned)
        return f"[计算器] {cleaned} = {result}"
    except Exception as e:
        return f"[计算错误] {str(e)}"


def tool_discovery(query: str, agent) -> str:
    """
    Performs deep analysis and hypothesis generation based on broader retrieval.
    """
    # 1. Broad retrieval (Top-8) to capture more context and potential connections
    chunks = agent.vector_store.search(query, top_k=TOOL_DISCOVERY_TOP_K)
    if not chunks:
        return "[深度分析] 资料库为空或未匹配到相关内容，无法进行推导。"
    
    # 2. Format evidence with source tracking
    evidence = []
    for c in chunks:
        doc = c.get("doc_name", "未知来源")
        txt = c.get("content", "").strip()
        evidence.append(f"《{doc}》:\n{txt}")
    
    # 3. Call LLM with Discovery Prompt
    from core.prompts import DISCOVERY_PROMPT
    from utils.ollama_client import ask_ollama
    
    prompt = DISCOVERY_PROMPT.format(
        question=query,
        kb_evidence="\n----\n".join(evidence)
    )
    
    # Use higher temperature (0.6) to encourage creativity and hypothesis generation
    return ask_ollama(prompt, temperature=LLM_TEMPERATURE_DISCOVERY)




TOOL_REGISTRY: Dict[str, Any] = {
    "RAG": tool_rag,
    "MEMORY": tool_memory,
    "LLM": tool_llm,
    "CALCULATOR": tool_calculator,
    "DISCOVERY": tool_discovery
}



