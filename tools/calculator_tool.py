from __future__ import annotations
import ast
from typing import Any
from core.config import CALCULATOR_MAX_EXPRESSION_LEN
from tools.base import BaseTool, ToolInput, ToolResult

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

class CalculatorTool(BaseTool):
    name = "CALCULATOR"

    def run(self, tool_input: ToolInput, agent: Any) -> ToolResult:
        try:
            query = tool_input.task or ""
            if len(query) > CALCULATOR_MAX_EXPRESSION_LEN:
                return ToolResult(success=True, content="[计算错误] 表达式过长，请简化。", metadata={"tool": self.name})

            query = query.replace("加", "+").replace("减", "-").replace("乘", "*").replace("除", "/")
            safe_chars = set("0123456789.+-*/() ")
            cleaned = "".join([c for c in query if c in safe_chars])
            if not cleaned.strip():
                return ToolResult(success=True, content="[计算错误] 未找到有效的数学表达式", metadata={"tool": self.name})

            if "**" in cleaned:
                return ToolResult(success=True, content="[计算错误] 不支持幂运算 (**)，请使用乘法。", metadata={"tool": self.name})

            result = _safe_eval_expression(cleaned)
            content = f"[计算器] {cleaned} = {result}"
            return ToolResult(success=True, content=content, metadata={"tool": self.name})
        except Exception as exc:  # pragma: no cover
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name})
