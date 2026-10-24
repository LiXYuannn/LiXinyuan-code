#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MiniSE-Workflow-MVP 命令行入口。

    python main.py run                     # 用内置示例需求跑完整流程
    python main.py run --input "需求描述"    # 自定义需求
    python main.py run --input-file req.txt
    python main.py viz                     # 打印流程图（Mermaid + ASCII）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core import WorkflowEngine            # noqa: E402
from src.core.tracing import (                 # noqa: E402
    render_report,
    write_artifacts,
    write_trace,
)
from src.core.viz import render_svg            # noqa: E402
from src.llm.config import LLMConfig           # noqa: E402
from src.llm.openai_client import build_llm    # noqa: E402
from src.llm.simulated import SimulatedLLM     # noqa: E402
from src.workflows import build_workflow       # noqa: E402

DEFAULT_REQUIREMENT = (
    "请实现一个中缀算术表达式计算器的 Python 库，要求："
    "1) 支持加(+)、减(-)、乘(*)、除(/)、取模(%)、幂(**) 与括号；"
    "2) 支持一元正负号与小数、科学计数法；"
    "3) 对括号不匹配、除零、非法字符给出明确的中文错误信息；"
    "4) 提供 evaluate(expression: str) -> float 作为唯一对外主入口。"
)


def cmd_run(args: argparse.Namespace) -> int:
    if args.input_file:
        requirement = Path(args.input_file).read_text(encoding="utf-8").strip()
    else:
        requirement = (args.input or DEFAULT_REQUIREMENT).strip()
    if not requirement:
        print("错误：需求文本为空。", file=sys.stderr)
        return 2

    if args.sim:
        # 离线模拟引擎：不消耗 token，用于演示 / 录屏 / 回归测试
        llm = SimulatedLLM(simulate_bug=args.simulate_bug)
        print("已接入：内置离线模拟引擎（--sim），不消耗 token\n")
    else:
        cfg = LLMConfig.from_env(args.env)
        try:
            cfg.validate()
        except Exception as e:  # noqa: BLE001
            print(f"\n[配置错误] {e}", file=sys.stderr)
            print("提示：没有 API Key 时可以用 `python main.py run --sim` 离线跑通全流程。\n",
                  file=sys.stderr)
            return 2
        llm = build_llm(cfg)
        print(f"已接入模型：{cfg.model} @ {cfg.base_url}\n")

    graph, state = build_workflow(
        llm,
        requirement=requirement,
        max_fix_rounds=args.max_fix_rounds,
        execute_tests=not args.no_exec,
        workdir=args.workdir,
    )
    print(graph.ascii(), "\n")

    engine = WorkflowEngine(max_workers=args.workers, verbose=not args.quiet)
    t0 = time.time()
    report = engine.run(graph, state)
    print(f"\n总耗时 {time.time() - t0:.2f}s，状态：{report.status}")

    out_dir = Path(args.out)
    files = write_artifacts(state, out_dir)
    trace_path = write_trace(state, report, Path(args.logs) / "trace.json")
    report_path = render_report(graph, state, report, out_dir / "report.html")

    print(f"\n产物目录：{out_dir.resolve()}")
    for f in sorted(files):
        print(f"  - {f.name}  ({f.stat().st_size} B)")
    print(f"执行轨迹：{trace_path}")
    print(f"可视化报告：{report_path}")

    usage = getattr(llm, "usage", None)
    if callable(usage):
        print(f"LLM 用量：{usage()}")
    print(f"校验结果：{'通过' if state.meta.get('verify_passed') else '未通过'}"
          f"（修复 {state.meta.get('fix_rounds', 0)} 轮）")
    return 0 if report.status == "success" else 1


def cmd_viz(args: argparse.Namespace) -> int:
    from src.workflows.mini_se import build_workflow as _bw

    class _Dummy:
        def chat(self, *a, **k):
            return ""

    graph, _ = _bw(_Dummy(), requirement="(示意)")
    print(graph.ascii())
    print()
    print(graph.mermaid())
    if args.svg:
        p = Path(args.svg)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_svg(graph), encoding="utf-8")
        print(f"\nSVG 已写入：{p}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="main.py", description="MiniSE-Workflow-MVP：多 Agent 协作的迷你软件工程工作流"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="运行完整工作流")
    p_run.add_argument("--input", "-i", help="原始需求文本")
    p_run.add_argument("--input-file", "-f", help="从文件读取原始需求")
    p_run.add_argument("--max-fix-rounds", type=int, default=2, help="最大修复轮次（默认 2）")
    p_run.add_argument("--no-exec", action="store_true", help="只做语法检查，不执行测试")
    p_run.add_argument("--workers", type=int, default=4, help="并行线程数（默认 4）")
    p_run.add_argument("--out", default="outputs", help="产物输出目录")
    p_run.add_argument("--logs", default="logs", help="日志/轨迹输出目录")
    p_run.add_argument("--env", default=".env", help=".env 路径")
    p_run.add_argument("--workdir", default=None, help="测试执行的临时目录")
    p_run.add_argument("--sim", action="store_true",
                       help="使用内置离线模拟引擎，无需 API Key")
    p_run.add_argument("--simulate-bug", action="store_true",
                       help="配合 --sim：首轮实现故意留缺陷，演示「校验失败→修复→重校验」回边")
    p_run.add_argument("--quiet", "-q", action="store_true", help="减少控制台输出")
    p_run.set_defaults(func=cmd_run)

    p_viz = sub.add_parser("viz", help="输出工作流结构")
    p_viz.add_argument("--svg", help="额外把流程图写成 SVG 文件")
    p_viz.set_defaults(func=cmd_viz)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
