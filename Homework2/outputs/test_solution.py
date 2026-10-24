"""solution.py 的单元测试（覆盖正常 / 边界 / 异常三类路径）。"""

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