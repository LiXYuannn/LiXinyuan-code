# -*- coding: utf-8 -*-
"""汇总节点（确定性，不消耗 token）：把整个流程的产出整理成交付清单。"""

from __future__ import annotations

import time

from ..core.node import NodeResult
from ..core.state import WorkflowState

FILE_DESC = {
    "00_requirement.md": "原始需求（用户输入）",
    "01_requirements.md": "需求规格说明书（需求Agent 产出）",
    "02_design.md": "软件设计说明书（设计Agent 产出）",
    "solution.py": "实现代码（编码Agent 产出）",
    "test_solution.py": "单元测试（编码Agent 产出）",
    "03_verify_report.md": "代码校验报告（校验器产出）",
}


class Summarizer:
    """生成交付物清单。"""

    def __call__(self, state: WorkflowState) -> NodeResult:
        passed = bool(state.meta.get("verify_passed"))
        rounds = int(state.meta.get("fix_rounds", 0))
        runs = state.runs()
        total = sum(r.duration for r in runs)

        lines = [
            "# 交付物清单",
            "",
            f"- 原始需求：{state.task[:120]}",
            f"- 流程结果：{'✅ 端到端跑通' if passed else '⚠️ 校验未通过（已达最大修复轮次）'}",
            f"- 修复轮次：{rounds}",
            f"- 节点执行：{len(runs)} 次，累计 {total:.2f}s",
            f"- Agent 消息：{len(state.bus.history())} 条",
            "",
            "## 产物",
            "",
            "| 文件 | 说明 | 版本 | 产出者 |",
            "|------|------|------|--------|",
        ]
        for key in sorted(state.keys()):
            art = state.artifacts()[key]
            desc = FILE_DESC.get(key, "流程产物")
            lines.append(f"| `{key}` | {desc} | v{art.version} | {art.producer} |")

        lines += [
            "",
            "## 节点耗时",
            "",
            "| 节点 | 轮次 | 耗时 | 状态 |",
            "|------|------|------|------|",
        ]
        for r in runs:
            # 汇总器自己此时还没被引擎标记完成（引擎在 handler 返回后才落 status），
            # 这里把它按「即将成功」展示，避免出现误导性的 running。
            status = "success" if r.status == "running" and r.name == "summarize" else r.status
            lines.append(f"| {r.name} | #{r.attempt} | {r.duration}s | {status} |")

        lines += ["", f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"]

        return NodeResult(
            summary=f"汇总完成（{len(state.keys())} 个产物）",
            outputs={"00_summary.md": "\n".join(lines)},
            extra={"summary_done": True},
        )
