"""中缀算术表达式计算器。

采用 词法分析 → 调度场算法 → 逆波兰求值 三段式实现。
"""

import re

__all__ = ["evaluate", "tokenize", "ExpressionError"]


class ExpressionError(ValueError):
    """表达式错误（中文提示）。"""


_TOKEN = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<pow>\*\*)|(?P<op>[+\-*/%()]))"
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