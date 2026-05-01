from tools.base import ToolInput
from tools.calculator_tool import CalculatorTool


def test_calculator_safe_expression():
    tool = CalculatorTool()
    result = tool.run(ToolInput(task="1+2*3"), agent=None)
    assert result.success is True
    assert "[计算器]" in result.content
    assert "= 7" in result.content


def test_calculator_rejects_power_operator():
    tool = CalculatorTool()
    result = tool.run(ToolInput(task="2**10"), agent=None)
    assert result.success is True
    assert "不支持幂运算" in result.content


def test_calculator_blocks_code_execution_payload():
    tool = CalculatorTool()
    result = tool.run(ToolInput(task="__import__('os').system('whoami')"), agent=None)
    assert result.success is False or "[计算错误]" in result.content
