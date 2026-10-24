# -*- coding: utf-8 -*-
"""工作流图（有向图 + 条件边 + 并行分支）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GraphValidationError
from .node import Node, Route


@dataclass
class WorkflowGraph:
    """一个可执行的 Workflow 定义。"""

    name: str
    description: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)

    def add(self, node: Node) -> "WorkflowGraph":
        if node.name in self.nodes:
            raise GraphValidationError(f"节点名重复：{node.name}")
        self.nodes[node.name] = node
        return self

    def node(self, name: str) -> Node:
        if name not in self.nodes:
            raise GraphValidationError(f"节点不存在：{name}")
        return self.nodes[name]

    def entry_nodes(self) -> list[str]:
        return [n for n, node in self.nodes.items() if not node.deps]

    def validate(self) -> None:
        """校验依赖与出边指向的节点都存在。"""
        for name, node in self.nodes.items():
            for d in node.deps:
                if d not in self.nodes:
                    raise GraphValidationError(f"节点 [{name}] 依赖了不存在的节点 [{d}]")
            for r in node.routes:
                if r.target not in self.nodes:
                    raise GraphValidationError(
                        f"节点 [{name}] 的出边指向不存在的节点 [{r.target}]"
                    )
            if name in node.deps:
                raise GraphValidationError(f"节点 [{name}] 不能依赖自己")

    # ---------- 可视化 ----------
    def mermaid(self) -> str:
        """导出 Mermaid 流程图文本，可直接粘到 Markdown / 网页。"""
        lines = ["```mermaid", "flowchart TD"]
        for name, node in self.nodes.items():
            label = f"{name}\\n({node.role or node.kind})"
            shape = f'    {name}["{label}"]'
            lines.append(shape)
        for name, node in self.nodes.items():
            for r in node.routes:
                if r.label:
                    lines.append(f"    {name} -->|{r.label}| {r.target}")
                else:
                    lines.append(f"    {name} --> {r.target}")
        lines.append("```")
        return "\n".join(lines)

    def ascii(self) -> str:
        """纯文本拓扑，便于在终端快速查看。"""
        out = [f"Workflow: {self.name}"]
        for name, node in self.nodes.items():
            deps = "、".join(node.deps) or "（入口）"
            nxt = "、".join(
                f"{r.target}{'(' + r.label + ')' if r.label else ''}" for r in node.routes
            ) or "（终点）"
            out.append(f"  · {name:<14} [{node.kind}] 依赖 {deps}  ->  {nxt}")
        return "\n".join(out)
