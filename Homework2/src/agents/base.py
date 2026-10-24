# -*- coding: utf-8 -*-
"""Agent 基类。

统一约定：
1. Agent 的输入只从「共享状态（黑板）」读，输出只往黑板写 —— 不直接互相调用；
2. Agent 之间的协作通过 MessageBus 发消息，消息里只放摘要 + 引用的黑板键，
   避免把大段代码塞进消息体（这也是真实系统里常见的做法）；
3. 每个 Agent 只声明「我要什么、我产出什么」，何时被调度由引擎决定。
"""

from __future__ import annotations

import time

from ..core.node import NodeResult
from ..core.state import WorkflowState
from ..llm.base import LLMBackend

MAX_INPUT_CHARS = 16000  # 防止把超长上下文喂给模型导致超限 / 烧钱


class BaseAgent:
    """所有 Agent 的父类。"""

    def __init__(
        self,
        name: str,
        role: str,
        llm: LLMBackend,
        system_prompt: str,
        description: str = "",
    ) -> None:
        self.name = name
        self.role = role
        self.llm = llm
        self.system_prompt = system_prompt
        self.description = description
        self.last_latency = 0.0

    # ---------- 能力 ----------
    def think(
        self,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """调用大模型并统计耗时。"""
        t0 = time.time()
        reply = self.llm.chat(
            self.system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tag=self.name,
        )
        self.last_latency = round(time.time() - t0, 2)
        return reply

    def send(
        self,
        state: WorkflowState,
        receiver: str,
        msg_type: str,
        payload: str,
        refs: list[str] | None = None,
    ) -> None:
        """向另一个 Agent 发消息。"""
        state.bus.publish(
            sender=self.name,
            receiver=receiver,
            msg_type=msg_type,
            payload=payload,
            refs=refs or [],
        )

    def read(self, state: WorkflowState, key: str, default: str = "") -> str:
        """从黑板读取输入，超长自动截断。"""
        text = state.read(key, default)
        if len(text) > MAX_INPUT_CHARS:
            text = text[:MAX_INPUT_CHARS] + "\n...（已截断）"
        return text

    # ---------- 需要子类实现 ----------
    def run(self, state: WorkflowState) -> NodeResult:
        raise NotImplementedError
