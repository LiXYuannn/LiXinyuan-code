# -*- coding: utf-8 -*-
"""Agent 间消息传递。

设计要点：
1. 所有 Agent 之间的通信必须经过 MessageBus，禁止直接互相调用，
   这样 Agent 之间只依赖「消息协议」而不依赖彼此的实现（解耦）。
2. 每条消息带 seq / ts / attempt，可用于事后重放（replay）与排障。
3. MessageBus 是线程安全的，因为引擎会并行执行节点。
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    """一条 Agent 间消息。"""

    sender: str
    receiver: str
    msg_type: str          # 例如 artifact / request / feedback / status
    payload: str           # 正文（正文过长时只放摘要 + 引用 key）
    refs: list[str] = field(default_factory=list)  # 引用的黑板键，避免消息体过大
    ts: float = field(default_factory=time.time)
    seq: int = 0
    attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.msg_type,
            "refs": self.refs,
            "payload": self.payload,
            "attempt": self.attempt,
        }


class MessageBus:
    """线程安全的消息总线。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._messages: list[AgentMessage] = []

    def publish(
        self,
        sender: str,
        receiver: str,
        msg_type: str,
        payload: str,
        refs: list[str] | None = None,
        attempt: int = 0,
    ) -> AgentMessage:
        """发送一条消息并返回它。"""
        with self._lock:
            msg = AgentMessage(
                sender=sender,
                receiver=receiver,
                msg_type=msg_type,
                payload=payload,
                refs=list(refs or []),
                seq=next(self._counter),
                attempt=attempt,
            )
            self._messages.append(msg)
        return msg

    def history(self) -> list[AgentMessage]:
        with self._lock:
            return list(self._messages)

    def for_receiver(self, receiver: str) -> list[AgentMessage]:
        with self._lock:
            return [m for m in self._messages if m.receiver == receiver]

    def between(self, a: str, b: str) -> list[AgentMessage]:
        with self._lock:
            return [
                m
                for m in self._messages
                if (m.sender == a and m.receiver == b)
                or (m.sender == b and m.receiver == a)
            ]

    def to_dict(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.history()]
