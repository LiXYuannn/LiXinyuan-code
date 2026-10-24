# -*- coding: utf-8 -*-
"""节点与路由的抽象。

一个 Node 只描述「做什么、依赖谁、完成后往哪走」，
具体怎么做由 handler（通常是 Agent）决定 —— 这样图结构和业务逻辑解耦，
新增 Agent 或改流程只需要改 WorkflowGraph 的装配代码。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .state import WorkflowState


@dataclass
class NodeResult:
    """节点执行的返回值。"""

    summary: str = ""
    outputs: dict[str, str] = field(default_factory=dict)   # 会写入黑板
    extra: dict[str, object] = field(default_factory=dict)  # 引擎/路由可读的中间数据


@dataclass
class Route:
    """一条出边。

    condition 为 None 表示无条件；
    label 用于可视化（例如「校验通过」/「校验失败」）。
    """

    target: str
    condition: Callable[[WorkflowState], bool] | None = None
    label: str = ""


@dataclass
class Node:
    """工作流中的一个节点。"""

    name: str
    handler: Callable[[WorkflowState], NodeResult]
    deps: list[str] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    kind: str = "agent"          # agent | tool（仅用于展示）
    role: str = ""               # 展示用：所属 Agent
    description: str = ""
    max_retries: int = 2         # 失败重试次数（不含首次）
    retry_backoff: float = 1.5   # 重试退避基数（秒）

    def is_ready(self, state: WorkflowState) -> bool:
        """是否可以被调度。"""
        if state.is_executed(self.name):
            return False
        if not state.is_activated(self.name):
            return False
        return all(state.is_executed(d) for d in self.deps)

    def next_targets(self, state: WorkflowState) -> list[Route]:
        """筛选出当前满足条件的出边。"""
        return [r for r in self.routes if r.condition is None or r.condition(state)]
