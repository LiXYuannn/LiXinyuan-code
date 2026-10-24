# -*- coding: utf-8 -*-
"""LLM 后端抽象。

Agent 只依赖这个接口，换模型 / 换厂商只需要换一个实现，
不需要改任何 Agent 代码（面向接口编程，便于扩展）。
"""

from __future__ import annotations

import re
from typing import Protocol


class LLMBackend(Protocol):
    """所有 LLM 后端需要实现的接口。"""

    def chat(self, system: str, user: str, temperature: float | None = None,
             max_tokens: int | None = None, tag: str = "") -> str:
        """发起一次对话，返回助手的纯文本回复。"""
        ...


def strip_fences(text: str, lang: str | None = None) -> str:
    """从大模型回复里抽出代码块。

    大模型常把代码包在 ```python ... ``` 里，直接落盘会无法运行，
    所以统一做一次抽取；抽不到就原样返回（可能本来就是纯代码）。
    """
    if not text:
        return ""
    pattern = r"```" + (lang or r"[a-zA-Z0-9_+.-]*") + r"?\s*\n(.*?)```"
    m = re.search(pattern, text, re.S)
    if m:
        return m.group(1).strip()
    # 退化情况：只有开始 fence 没有结束 fence
    m2 = re.search(r"```[a-zA-Z0-9_+.-]*\s*\n(.*)$", text, re.S)
    if m2:
        return m2.group(1).strip()
    return text.strip()


def extract_block(text: str, lang: str = "python") -> str:
    """优先抽取指定语言的代码块。"""
    got = strip_fences(text, lang)
    if got:
        return got
    return strip_fences(text)
