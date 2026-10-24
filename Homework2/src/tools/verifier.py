# -*- coding: utf-8 -*-
"""代码校验器（工具节点，非 LLM）。

在 Agent 协作流水线里放一个确定性的「守门员」很有必要：
大模型的输出不能自证正确，必须由客观检查（语法 + 执行）来判定，
判定结果写回黑板，供后续的条件路由决定「放行」还是「打回修复」。
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..core.node import NodeResult
from ..core.state import WorkflowState

MAX_LOG_CHARS = 2500


def _syntax_check(code: str, filename: str) -> str | None:
    """返回错误信息，None 表示通过。"""
    try:
        ast.parse(code, filename=filename)
        return None
    except SyntaxError as e:
        return f"{filename}:{e.lineno}: {e.msg}"


class CodeVerifier:
    """对黑板上的 solution.py / test_solution.py 做客观校验。"""

    def __init__(
        self,
        execute: bool = True,
        timeout: float = 60.0,
        workdir: str | None = None,
    ) -> None:
        self.execute = execute
        self.timeout = timeout
        self.workdir = Path(workdir) if workdir else Path(tempfile.gettempdir())

    def __call__(self, state: WorkflowState) -> NodeResult:
        impl = state.read("solution.py")
        test = state.read("test_solution.py")

        lines = ["# 代码校验报告", ""]
        impl_err = _syntax_check(impl, "solution.py") if impl.strip() else "solution.py 为空"
        test_err = _syntax_check(test, "test_solution.py") if test.strip() else "test_solution.py 为空"

        lines.append("## 1. 语法检查")
        lines.append(f"- solution.py：{'通过' if impl_err is None else '失败 — ' + impl_err}")
        lines.append(
            f"- test_solution.py：{'通过' if test_err is None else '失败 — ' + test_err}"
        )
        lines.append("")

        passed = impl_err is None and test_err is None
        exec_output = ""

        if passed and self.execute:
            lines.append("## 2. 测试执行")
            code, out = self._run_tests(impl, test)
            exec_output = out
            lines.append(f"- 命令：`python test_solution.py`（超时 {self.timeout}s）")
            lines.append(f"- 返回码：{code}")
            lines.append("")
            lines.append("```")
            lines.append(out[:MAX_LOG_CHARS])
            lines.append("```")
            passed = code == 0
        elif passed:
            lines.append("## 2. 测试执行")
            lines.append("- 已跳过（--no-exec）")
        else:
            lines.append("## 2. 测试执行")
            lines.append("- 因语法检查失败，未执行")

        lines.append("")
        lines.append(f"## 3. 结论：{'✅ 通过' if passed else '❌ 未通过'}")

        report = "\n".join(lines)
        state.bus.publish(
            sender="代码校验器",
            receiver="编排器",
            msg_type="status",
            payload=("校验通过，进入汇总" if passed else "校验未通过，可触发修复"),
            refs=["03_verify_report.md"],
        )
        return NodeResult(
            summary="校验通过" if passed else "校验未通过",
            outputs={"03_verify_report.md": report},
            extra={
                "verify_passed": passed,
                "verify_error": (impl_err or test_err or exec_output[-800:]),
            },
        )

    def _run_tests(self, impl: str, test: str) -> tuple[int, str]:
        """把两个文件写进临时目录并跑起来，返回 (返回码, 输出)。"""
        self.workdir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(self.workdir)) as tmp:
            d = Path(tmp)
            (d / "solution.py").write_text(impl, encoding="utf-8")
            (d / "test_solution.py").write_text(test, encoding="utf-8")
            t0 = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, "test_solution.py"],
                    cwd=str(d),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                out += f"\n（耗时 {time.time() - t0:.2f}s）"
                return proc.returncode, out.strip()
            except subprocess.TimeoutExpired:
                return 1, f"测试执行超时（>{self.timeout}s）"
            except Exception as e:  # noqa: BLE001
                return 1, f"测试执行异常：{e}"
