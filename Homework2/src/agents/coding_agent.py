# -*- coding: utf-8 -*-
"""编码 Agent：支持三种模式（实现 / 测试 / 修复），由同一份设计驱动。

用同一个类 + 不同 mode 而不是写三个类，是因为三者的
「读黑板 → 组 Prompt → 调 LLM → 写黑板」骨架完全一致，
差别只在 Prompt；这样新增第四种代码任务只需要加一个 Prompt 常量。
"""

from __future__ import annotations

from ..core.node import NodeResult
from ..core.state import WorkflowState
from ..llm.base import extract_block
from .base import BaseAgent

# ---------------- 实现模式 ----------------
IMPL_SYSTEM = """你是一名资深 Python 工程师（Python Engineer）。

你的任务：严格按照《软件设计说明书》实现可运行的 Python 代码。

硬性要求：
1. 只输出一个完整 Python 源文件的代码，不要任何解释文字。
2. 文件名视为 solution.py，是单文件模块。
3. 必须使用设计说明书中定义的函数名、参数名与返回类型，不得擅自改名。
4. 仅使用 Python 标准库；不要引入第三方依赖。
5. 每个公开函数都要有中文 docstring 和类型注解。
6. 必须包含必要的入参校验与异常处理。
7. 不要写测试代码，不要写 if __name__ == "__main__" 的演示代码。
8. 代码必须能通过 `python -m py_compile` 语法检查。
"""

IMPL_USER = """《需求规格说明书》：

{srs}

《软件设计说明书》：

{design}

请输出完整的 solution.py 源码。"""

# ---------------- 测试模式 ----------------
TEST_SYSTEM = """你是一名资深测试工程师（Test Engineer）。

你的任务：为《软件设计说明书》中的接口编写单元测试。

硬性要求：
1. 只输出一个完整 Python 测试文件的代码，不要任何解释文字。
2. 使用标准库 unittest，不要使用 pytest（环境不保证安装）。
3. 通过 `from solution import ...` 导入被测代码（测试文件与 solution.py 同目录）。
4. 至少覆盖：正常路径、边界条件、异常路径三类用例。
5. 文件末尾必须包含：
   if __name__ == "__main__":
       unittest.main(verbosity=2)
6. 断言必须具体（断言值，而不是只 assertIsNotNone）。
"""

TEST_USER = """《软件设计说明书》：

{design}

《需求规格说明书》中的验收标准（节选）：

{srs}

请输出完整的 test_solution.py 源码。"""

# ---------------- 修复模式 ----------------
FIX_SYSTEM = """你是一名资深 Python 工程师，正在修复自动化测试跑不过的代码。

你的任务：根据报错信息修复实现代码。

硬性要求：
1. 只输出修复后的完整 solution.py 源码，不要任何解释文字。
2. 保持对外接口（函数名、参数、返回类型）不变 —— 测试文件不会同步修改，
   接口一改测试必然失败。
3. 如果是测试代码本身写错了（比如断言与实现语义不符、导入名错误），
   则输出 # FIX_TARGET: test 注释开头，并输出修复后的完整 test_solution.py。
4. 仅使用标准库；代码必须能通过语法检查。
"""

FIX_USER = """《软件设计说明书》（节选）：

{design}

当前 solution.py：

{impl}

当前 test_solution.py：

{test}

测试执行结果（失败信息）：

{report}

请输出修复后的完整源码。"""


class CodingAgent(BaseAgent):
    """编码 Agent（mode: impl / test / fix）。"""

    def __init__(self, llm, mode: str = "impl") -> None:
        if mode not in ("impl", "test", "fix"):
            raise ValueError(f"未知模式：{mode}")
        self.mode = mode
        if mode == "impl":
            super().__init__(
                name="编码Agent(实现)", role="Python 工程师", llm=llm,
                system_prompt=IMPL_SYSTEM, description="按设计文档生成实现代码",
            )
        elif mode == "test":
            super().__init__(
                name="编码Agent(测试)", role="测试工程师", llm=llm,
                system_prompt=TEST_SYSTEM, description="按设计文档生成单元测试",
            )
        else:
            super().__init__(
                name="编码Agent(修复)", role="Python 工程师", llm=llm,
                system_prompt=FIX_SYSTEM, description="根据测试报错修复代码",
            )

    def run(self, state: WorkflowState) -> NodeResult:
        if self.mode == "impl":
            return self._run_impl(state)
        if self.mode == "test":
            return self._run_test(state)
        return self._run_fix(state)

    # ---------- 三种模式 ----------
    def _run_impl(self, state: WorkflowState) -> NodeResult:
        design = self.read(state, "02_design.md")
        srs = self.read(state, "01_requirements.md")
        if not design.strip():
            raise ValueError("设计文档为空，无法编码")

        raw = self.think(IMPL_USER.format(srs=srs, design=design))
        code = extract_block(raw, "python")
        if "def " not in code:
            raise ValueError("生成的实现代码不像 Python 源码，已拒绝写入黑板")

        self.send(
            state,
            receiver="代码校验器",
            msg_type="artifact",
            payload=f"实现代码已就绪（{len(code.splitlines())} 行），请等待校验。",
            refs=["solution.py"],
        )
        return NodeResult(
            summary=f"实现 {len(code.splitlines())} 行（耗时 {self.last_latency}s）",
            outputs={"solution.py": code},
        )

    def _run_test(self, state: WorkflowState) -> NodeResult:
        design = self.read(state, "02_design.md")
        srs = self.read(state, "01_requirements.md")
        if not design.strip():
            raise ValueError("设计文档为空，无法编写测试")

        raw = self.think(TEST_USER.format(srs=srs, design=design))
        code = extract_block(raw, "python")
        if "unittest" not in code:
            raise ValueError("生成的测试代码未使用 unittest，已拒绝写入黑板")
        if "def test" not in code:
            raise ValueError("生成的测试代码里没有测试用例，已拒绝写入黑板")

        self.send(
            state,
            receiver="代码校验器",
            msg_type="artifact",
            payload=f"单元测试已就绪（{len(code.splitlines())} 行），请等待校验。",
            refs=["test_solution.py"],
        )
        return NodeResult(
            summary=f"测试 {len(code.splitlines())} 行（耗时 {self.last_latency}s）",
            outputs={"test_solution.py": code},
        )

    def _run_fix(self, state: WorkflowState) -> NodeResult:
        design = self.read(state, "02_design.md")
        impl = self.read(state, "solution.py")
        test = self.read(state, "test_solution.py")
        report = self.read(state, "03_verify_report.md", "(无报告)")
        if not impl.strip():
            raise ValueError("实现代码为空，无法修复")

        raw = self.think(
            FIX_USER.format(design=design, impl=impl, test=test, report=report),
            temperature=0.2,
        )
        code = extract_block(raw, "python")

        if code.startswith("# FIX_TARGET: test"):
            code = code.split("\n", 1)[1] if "\n" in code else ""
            if "unittest" not in code:
                raise ValueError("修复后的测试代码不合法，已拒绝写入黑板")
            key = "test_solution.py"
        else:
            if "def " not in code:
                raise ValueError("修复后的实现代码不合法，已拒绝写入黑板")
            key = "solution.py"

        self.send(
            state,
            receiver="代码校验器",
            msg_type="feedback",
            payload=f"已修复 {key}，请重新执行校验。",
            refs=[key],
        )
        return NodeResult(
            summary=f"修复并重写 {key}（耗时 {self.last_latency}s）",
            outputs={key: code},
        )
