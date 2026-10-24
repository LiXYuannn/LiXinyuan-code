# -*- coding: utf-8 -*-
"""测试用 LLM 桩。

实际内容放在 `src/llm.simulated`（生产代码里的离线模拟引擎），
这里只做转发，另加一个永远失败的桩用于验证错误处理。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm.simulated import SimulatedLLM  # noqa: E402

__all__ = ["SimulatedLLM", "FailingLLM"]


class FailingLLM:
    """永远失败的 LLM，用于验证重试与错误传播。"""

    def chat(self, system: str, user: str, temperature=None, max_tokens=None, tag=""):
        raise RuntimeError("模拟 LLM 服务不可用")

    def usage(self):
        return {"calls": 0}
