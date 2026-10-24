# -*- coding: utf-8 -*-
"""内置离线模拟引擎（SimulatedLLM）。

作用：
1. 没有 API Key 时，`python main.py run --sim` 也能把整条流水线真跑一遍，
   用于演示、录屏、以及 CI 里的回归测试；
2. `tests/` 下的自测直接用它，不消耗任何 token。

它替换的只是「大模型回复」这一段，引擎的调度、并行、条件分支、循环回退、
代码落盘与真实执行，全部照常发生。
"""

from __future__ import annotations

SRS = """# 需求规格说明书

## 1. 项目概述
提供一个中缀算术表达式计算器库，输入表达式字符串，返回计算结果。

## 2. 术语表
- 表达式：由数字、运算符、括号组成的单行字符串。
- 调度场算法：把中缀表达式转成逆波兰式的经典算法。

## 3. 功能需求
- FR-01 支持加(+)、减(-)、乘(*)、除(/)、取模(%)、幂(**) 六种运算
- FR-02 支持括号改变运算优先级，支持嵌套括号
- FR-03 支持一元正负号，且 `-2**2` 应等于 -4
- FR-04 支持整数、小数与科学计数法（如 1.5e2）
- FR-05 幂运算为右结合，即 `2**3**2` 应等于 512

## 4. 非功能需求
- NFR-01 仅使用 Python 标准库，不引入第三方依赖
- NFR-02 所有错误信息使用中文，便于定位问题
- NFR-03 单文件模块，便于分发

## 5. 输入输出约定
- 输入：`expression: str`
- 输出：`float`
- 异常：表达式非法时抛出 `ExpressionError`（继承自 `ValueError`）

## 6. 验收标准
- AC-01 `evaluate("2+3*4")` == 14（乘法优先级高于加法）
- AC-02 `evaluate("(2+3)*4")` == 20（括号优先）
- AC-03 `evaluate("2**3**2")` == 512（幂右结合）
- AC-04 `evaluate("1/0")` 抛出中文除零错误
- AC-05 `evaluate("(1+2")` 抛出中文括号不匹配错误
- AC-06 `evaluate("")` 抛出空表达式错误

## 7. 假设与约束
- 假设输入为单行表达式，不做多行处理。
- 假设数值范围在 Python float 可表示范围内，溢出不额外处理。
"""

DESIGN = """# 软件设计说明书

## 1. 架构总览
单模块 `solution.py`，采用经典三段式：词法分析 → 调度场算法（Shunting-yard）
转逆波兰式 → 逆波兰式求值。全程无外部依赖。

## 2. 模块划分
| 模块 | 职责 |
|------|------|
| 词法分析 `tokenize` | 把字符串切成 `(类型, 值)` 序列 |
| 中缀转后缀 `_shunting_yard` | 处理优先级与结合性 |
| 求值 `_eval_rpn` | 计算逆波兰式 |
| 对外入口 `evaluate` | 串起上述三步，做入参校验 |

## 3. 接口定义
```python
class ExpressionError(ValueError): ...

def tokenize(expression: str) -> list[tuple[str, str]]:
    \"\"\"把表达式切成 token 序列，类型取值为 'num' 或 'op'。\"\"\"

def evaluate(expression: str) -> float:
    \"\"\"计算中缀表达式的值，非法时抛 ExpressionError。\"\"\"
```

## 4. 核心数据结构
- 输出队列 `output: list`：存放数字(float)与运算符(str)的逆波兰序列
- 运算符栈 `stack: list`：暂存运算符与左括号
- 一元负号在栈中记为特殊运算符 `'u-'`，优先级 3，右结合

## 5. 关键流程
1. `tokenize` 用一条正则切出数字、`**`、其他运算符与括号；遇到无法识别的字符报错。
2. 扫描 token：数字直接进输出队列；运算符按优先级弹栈后再入栈；括号单独处理。
3. 收尾把栈中剩余运算符全部弹出，若遇到左括号说明括号不匹配。
4. 对逆波兰序列求值，栈最终必须只剩一个元素。

## 6. 异常与边界处理
| 场景 | 处理 |
|------|------|
| 非法字符 | 抛出「非法字符：x（位置 n）」 |
| 括号不匹配 | 区分「多余的右括号」与「缺少右括号」 |
| 除零 / 取模零 | 抛出中文除零错误 |
| 空表达式 | 抛 ExpressionError |
| 非字符串入参 | 抛 TypeError |

## 7. 测试要点
- 优先级：`2+3*4` == 14
- 结合性：`2**3**2` == 512、`8/4/2` == 1
- 一元号：`-3+5` == 2、`-2**2` == -4
- 异常路径：除零、括号不匹配、非法字符、空串
"""

SOLUTION_OK = '''"""中缀算术表达式计算器。

采用 词法分析 → 调度场算法 → 逆波兰求值 三段式实现。
"""

import re

__all__ = ["evaluate", "tokenize", "ExpressionError"]


class ExpressionError(ValueError):
    """表达式错误（中文提示）。"""


_TOKEN = re.compile(
    r"\\s*(?:(?P<number>\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)|(?P<pow>\\*\\*)|(?P<op>[+\\-*/%()]))"
)

# 运算符 -> (优先级, 结合性)；一元负号 'u-' 优先级 3，高于乘除、低于幂
_OPS = {"+": (1, "L"), "-": (1, "L"), "*": (2, "L"), "/": (2, "L"), "%": (2, "L"), "**": (4, "R")}

_UNARY_PREC = 3


def tokenize(expression: str) -> list:
    """把表达式字符串切成 token 列表。

    Args:
        expression: 待切分的表达式字符串。

    Returns:
        形如 [("num", "12"), ("op", "+"), ...] 的列表。

    Raises:
        ExpressionError: 遇到无法识别的字符。
    """
    tokens = []
    pos = 0
    while pos < len(expression):
        if expression[pos].isspace():
            pos += 1
            continue
        matched = _TOKEN.match(expression, pos)
        if not matched:
            raise ExpressionError("非法字符：%r（位置 %d）" % (expression[pos], pos))
        pos = matched.end()
        if matched.group("number") is not None:
            tokens.append(("num", matched.group("number")))
        elif matched.group("pow"):
            tokens.append(("op", "**"))
        else:
            tokens.append(("op", matched.group("op")))
    return tokens


def _apply(op: str, left: float, right: float) -> float:
    """执行一次二元运算。

    Args:
        op: 运算符字符串。
        left: 左操作数。
        right: 右操作数。

    Returns:
        运算结果。

    Raises:
        ExpressionError: 除零或不支持的运算符。
    """
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            raise ExpressionError("除零错误")
        return left / right
    if op == "%":
        if right == 0:
            raise ExpressionError("取模运算的除数为零")
        return left % right
    if op == "**":
        return left ** right
    raise ExpressionError("不支持的运算符：%s" % op)


def _shunting_yard(tokens: list) -> list:
    """把中缀 token 序列转成逆波兰式。

    Args:
        tokens: tokenize 的输出。

    Returns:
        逆波兰式列表，元素为 float 或运算符字符串。

    Raises:
        ExpressionError: 括号不匹配。
    """
    output: list = []
    stack: list = []
    prev = None  # 上一个 token 的类型，用于判定一元正负号

    for kind, value in tokens:
        if kind == "num":
            output.append(float(value))
            prev = "num"
        elif value == "(":
            stack.append(value)
            prev = "op"
        elif value == ")":
            while stack and stack[-1] != "(":
                output.append(stack.pop())
            if not stack:
                raise ExpressionError("括号不匹配：多余的右括号")
            stack.pop()
            prev = "num"
        else:
            # 一元正负号：出现在开头，或紧跟在另一个运算符 / 左括号之后
            if value in "+-" and (prev is None or prev == "op"):
                if value == "-":
                    stack.append("u-")
                prev = "op"
                continue
            prec, assoc = _OPS[value]
            while stack and stack[-1] != "(":
                top = stack[-1]
                top_prec = _UNARY_PREC if top == "u-" else _OPS[top][0]
                if top_prec > prec or (top_prec == prec and assoc == "L"):
                    output.append(stack.pop())
                else:
                    break
            stack.append(value)
            prev = "op"

    while stack:
        top = stack.pop()
        if top == "(":
            raise ExpressionError("括号不匹配：缺少右括号")
        output.append(top)
    return output


def _eval_rpn(rpn: list) -> float:
    """对逆波兰式求值。

    Args:
        rpn: _shunting_yard 的输出。

    Returns:
        计算结果。

    Raises:
        ExpressionError: 表达式不合法（缺操作数或多余操作数）。
    """
    stack: list = []
    for item in rpn:
        if isinstance(item, float):
            stack.append(item)
        elif item == "u-":
            if not stack:
                raise ExpressionError("一元负号缺少操作数")
            stack.append(-stack.pop())
        else:
            if len(stack) < 2:
                raise ExpressionError("运算符 %s 缺少操作数" % item)
            right = stack.pop()
            left = stack.pop()
            stack.append(_apply(item, left, right))
    if len(stack) != 1:
        raise ExpressionError("表达式不合法")
    return stack[0]


def evaluate(expression: str) -> float:
    """计算中缀算术表达式的值。

    Args:
        expression: 待计算的表达式字符串，如 "2+3*4"。

    Returns:
        表达式的计算结果（float）。

    Raises:
        ExpressionError: 表达式为空、括号不匹配、除零或含非法字符。
        TypeError: 入参不是字符串。
    """
    if not isinstance(expression, str):
        raise TypeError("表达式必须是字符串")
    if not expression.strip():
        raise ExpressionError("表达式为空")
    return _eval_rpn(_shunting_yard(tokenize(expression)))
'''

# 故意引入缺陷的版本：把幂运算也改成左结合且优先级相同，
# 会让 "2**3**2" 算成 64（正确值 512），从而在校验阶段失败并触发修复回边。
SOLUTION_BUGGY = SOLUTION_OK.replace(
    '_OPS = {"+": (1, "L"), "-": (1, "L"), "*": (2, "L"), "/": (2, "L"), "%": (2, "L"), "**": (4, "R")}',
    '_OPS = {"+": (1, "L"), "-": (1, "L"), "*": (2, "L"), "/": (2, "L"), "%": (2, "L"), "**": (1, "L")}',
)

TESTS = '''"""solution.py 的单元测试（覆盖正常 / 边界 / 异常三类路径）。"""

import unittest

from solution import ExpressionError, evaluate, tokenize


class TestBasicArithmetic(unittest.TestCase):
    """正常路径。"""

    def test_add(self):
        self.assertAlmostEqual(evaluate("1+2"), 3.0)

    def test_subtract(self):
        self.assertAlmostEqual(evaluate("10-4"), 6.0)

    def test_multiply(self):
        self.assertAlmostEqual(evaluate("6*7"), 42.0)

    def test_divide(self):
        self.assertAlmostEqual(evaluate("9/2"), 4.5)

    def test_mod(self):
        self.assertAlmostEqual(evaluate("7%3"), 1.0)

    def test_power(self):
        self.assertAlmostEqual(evaluate("2**10"), 1024.0)


class TestPrecedenceAndAssociativity(unittest.TestCase):
    """优先级与结合性。"""

    def test_multiply_before_add(self):
        self.assertAlmostEqual(evaluate("2+3*4"), 14.0)

    def test_parenthesis(self):
        self.assertAlmostEqual(evaluate("(2+3)*4"), 20.0)

    def test_nested_parenthesis(self):
        self.assertAlmostEqual(evaluate("((1+2)*(3+4))"), 21.0)

    def test_power_is_right_associative(self):
        # 右结合：2 ** (3 ** 2) = 512，而非 (2 ** 3) ** 2 = 64
        self.assertAlmostEqual(evaluate("2**3**2"), 512.0)

    def test_divide_is_left_associative(self):
        self.assertAlmostEqual(evaluate("8/4/2"), 1.0)


class TestUnaryAndNumberFormat(unittest.TestCase):
    """一元符号与数字格式（边界）。"""

    def test_unary_minus(self):
        self.assertAlmostEqual(evaluate("-3+5"), 2.0)

    def test_unary_minus_with_power(self):
        # 一元负号优先级低于幂：- (2 ** 2) = -4
        self.assertAlmostEqual(evaluate("-2**2"), -4.0)

    def test_unary_plus(self):
        self.assertAlmostEqual(evaluate("+7"), 7.0)

    def test_float(self):
        self.assertAlmostEqual(evaluate("1.5*2"), 3.0)

    def test_scientific_notation(self):
        self.assertAlmostEqual(evaluate("1.5e2"), 150.0)

    def test_negative_scientific(self):
        self.assertAlmostEqual(evaluate("1e-2"), 0.01)


class TestErrorHandling(unittest.TestCase):
    """异常路径。"""

    def test_divide_by_zero(self):
        with self.assertRaises(ExpressionError):
            evaluate("1/0")

    def test_mod_by_zero(self):
        with self.assertRaises(ExpressionError):
            evaluate("5%0")

    def test_missing_right_parenthesis(self):
        with self.assertRaises(ExpressionError):
            evaluate("(1+2")

    def test_extra_right_parenthesis(self):
        with self.assertRaises(ExpressionError):
            evaluate("1+2)")

    def test_illegal_character(self):
        with self.assertRaises(ValueError):
            evaluate("1 & 2")

    def test_empty_expression(self):
        with self.assertRaises(ValueError):
            evaluate("   ")

    def test_non_string_input(self):
        with self.assertRaises(TypeError):
            evaluate(123)


class TestTokenize(unittest.TestCase):
    """词法分析。"""

    def test_token_types(self):
        tokens = tokenize("1 + 2")
        self.assertEqual(tokens[0], ("num", "1"))
        self.assertEqual(tokens[1], ("op", "+"))

    def test_power_token(self):
        self.assertIn(("op", "**"), tokenize("2**3"))

    def test_illegal_character(self):
        with self.assertRaises(ExpressionError):
            tokenize("1 # 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
'''


class SimulatedLLM:
    """按 system prompt 返回预设内容的离线模拟引擎。

    Args:
        simulate_bug: 首轮实现是否故意带缺陷（用于演示「校验失败 → 修复」回边）。
    """

    def __init__(self, simulate_bug: bool = False) -> None:
        self.simulate_bug = simulate_bug
        self.impl_calls = 0
        self.call_count = 0
        self.calls: list[str] = []

    def chat(self, system: str, user: str, temperature=None, max_tokens=None, tag=""):
        """返回与真实大模型格式一致的回复（含 ``` 代码块）。"""
        self.call_count += 1
        self.calls.append(tag or "unknown")

        if "需求分析师" in system:
            return "```markdown\n" + SRS + "\n```"
        if "架构师" in system:
            return "```markdown\n" + DESIGN + "\n```"
        if "测试工程师" in system:
            return "```python\n" + TESTS + "\n```"
        if "修复" in system:
            # 修复阶段总是返回正确实现
            return "```python\n" + SOLUTION_OK + "\n```"
        if "Python 工程师" in system:
            self.impl_calls += 1
            code = SOLUTION_BUGGY if (self.simulate_bug and self.impl_calls == 1) else SOLUTION_OK
            return "```python\n" + code + "\n```"
        raise ValueError("模拟引擎未识别的 system prompt：" + system[:60])

    def usage(self) -> dict[str, int]:
        return {"calls": self.call_count, "prompt_tokens": 0, "completion_tokens": 0}
