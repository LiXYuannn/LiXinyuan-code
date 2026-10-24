# -*- coding: utf-8 -*-
"""把工作流图渲染成静态 SVG（纯标准库，不依赖 Mermaid / 联网）。

为什么自己画：Mermaid 需要 CDN，离线打开报告就空白；
自绘 SVG 保证 HTML 报告在断网环境也能完整显示。
"""

from __future__ import annotations

from html import escape

from .graph import WorkflowGraph

NODE_W = 168
NODE_H = 58
H_GAP = 44
V_GAP = 78
PAD = 28

# 节点配色（按 kind 区分）
FILL = {"agent": "#1E6091", "tool": "#2A9D8F", "join": "#6D2E46"}
TEXT = "#FFFFFF"


def _layers(graph: WorkflowGraph) -> dict[str, int]:
    """按最长依赖路径分层（deps 图无环，迭代松弛即可收敛）。"""
    layer = {n: 0 for n in graph.nodes}
    for _ in range(len(graph.nodes) + 1):
        changed = False
        for name, node in graph.nodes.items():
            if node.deps:
                cand = max(layer[d] + 1 for d in node.deps)
                if cand > layer[name]:
                    layer[name] = cand
                    changed = True
        if not changed:
            break
    return layer


def _layout(graph: WorkflowGraph):
    layer = _layers(graph)
    buckets: dict[int, list[str]] = {}
    for name in sorted(graph.nodes):
        buckets.setdefault(layer[name], []).append(name)

    pos: dict[str, tuple[float, float]] = {}
    max_cols = max(len(v) for v in buckets.values())
    width = PAD * 2 + max_cols * NODE_W + (max_cols - 1) * H_GAP
    for depth, names in buckets.items():
        total = len(names) * NODE_W + (len(names) - 1) * H_GAP
        start_x = (width - total) / 2
        for i, name in enumerate(sorted(names)):
            x = start_x + i * (NODE_W + H_GAP)
            y = PAD + depth * (NODE_H + V_GAP)
            pos[name] = (x, y)

    height = PAD * 2 + (max(buckets) + 1) * NODE_H + max(buckets) * V_GAP
    return pos, width, height


def render_svg(graph: WorkflowGraph) -> str:
    """渲染整张图的 SVG 字符串。"""
    pos, width, height = _layout(graph)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Menlo, Consolas, sans-serif">',
        "<defs>"
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#8899A6"/></marker>'
        '<marker id="arrow-back" markerWidth="10" markerHeight="10" refX="9" refY="3" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#E76F51"/></marker>'
        "</defs>",
    ]

    # 先画边，避免遮挡节点
    for name, node in graph.nodes.items():
        sx, sy = pos[name]
        for route in node.routes:
            tx, ty = pos[route.target]
            back = ty <= sy  # 回边（循环）
            if back:
                x1, y1 = sx + NODE_W / 2, sy
                x2, y2 = tx + NODE_W / 2, ty + NODE_H
                dx = NODE_W / 2 + 26
                d = (
                    f"M {x1:.0f} {y1:.0f} C {x1 - dx:.0f} {y1 - 40:.0f}, "
                    f"{x2 - dx:.0f} {y2 + 40:.0f}, {x2:.0f} {y2:.0f}"
                )
                color, marker = "#E76F51", "arrow-back"
            else:
                x1, y1 = sx + NODE_W / 2, sy + NODE_H
                x2, y2 = tx + NODE_W / 2, ty
                mid = (y1 + y2) / 2
                d = (
                    f"M {x1:.0f} {y1:.0f} C {x1:.0f} {mid:.0f}, "
                    f"{x2:.0f} {mid:.0f}, {x2:.0f} {y2:.0f}"
                )
                color, marker = "#8899A6", "arrow"
            parts.append(
                f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8" '
                f'marker-end="url(#{marker})"/>'
            )
            if route.label:
                lx = (x1 + x2) / 2 + (10 if back else 8)
                ly = (y1 + y2) / 2
                parts.append(
                    f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="11" fill="{color}">'
                    f"{escape(route.label)}</text>"
                )

    # 再画节点
    for name, node in graph.nodes.items():
        x, y = pos[name]
        fill = FILL.get(node.kind, "#1E6091")
        parts.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{NODE_W}" height="{NODE_H}" rx="10" '
            f'fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{x + NODE_W / 2:.0f}" y="{y + 24:.0f}" text-anchor="middle" '
            f'font-size="14" font-weight="bold" fill="{TEXT}">{escape(name)}</text>'
        )
        sub = node.role or node.kind
        parts.append(
            f'<text x="{x + NODE_W / 2:.0f}" y="{y + 42:.0f}" text-anchor="middle" '
            f'font-size="11" fill="rgba(255,255,255,.75)">{escape(sub)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
