# -*- coding: utf-8 -*-
"""引擎与工作流的离线自测（不需要 API Key）。

覆盖：
1. 顺序 + 并行 + 条件分支 + 循环回退的完整链路
2. 校验失败时是否真的走进了 fix → verify 回边
3. 共享状态的版本化与快照恢复
4. 图结构校验（依赖缺失要报错）
5. 节点失败时引擎是否按预期终止
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core import WorkflowEngine, WorkflowGraph, WorkflowState  # noqa: E402
from src.core.errors import GraphValidationError  # noqa: E402
from src.core.node import Node, NodeResult  # noqa: E402
from src.llm.base import strip_fences  # noqa: E402
from src.workflows import build_workflow  # noqa: E402
from tests.fake_llm import FailingLLM, SimulatedLLM  # noqa: E402


def run_flow(buggy_first_impl: bool = False, execute: bool = True):
    llm = SimulatedLLM(simulate_bug=buggy_first_impl)
    graph, state = build_workflow(
        llm, requirement="实现一个中缀算术表达式计算器", max_fix_rounds=2, execute_tests=execute
    )
    engine = WorkflowEngine(verbose=False)
    report = engine.run(graph, state)
    return graph, state, report, llm


class TestWorkflowEngine(unittest.TestCase):
    def test_full_pipeline_success(self):
        graph, state, report, _ = run_flow()
        self.assertEqual(report.status, "success", msg=report.error)
        self.assertTrue(state.meta.get("verify_passed"))
        # 顺序链：需求 → 设计 → 实现/测试 → 校验 → 汇总
        for key in ("01_requirements.md", "02_design.md", "solution.py",
                    "test_solution.py", "03_verify_report.md", "00_summary.md"):
            self.assertTrue(state.has(key), f"缺少产物 {key}")
        # 汇总节点必须被执行到（说明条件路由走到了终点）
        self.assertTrue(state.is_executed("summarize"))

    def test_parallel_branch_both_ran(self):
        _, state, _, _ = run_flow()
        self.assertTrue(state.is_executed("coding_impl"))
        self.assertTrue(state.is_executed("coding_test"))

    def test_fix_loop_triggered_on_failure(self):
        """首轮实现故意有 bug，应当走 verify → fix → verify 回边。"""
        _, state, report, _ = run_flow(buggy_first_impl=True)
        self.assertEqual(report.status, "success", msg=report.error)
        self.assertEqual(state.meta.get("fix_rounds"), 1)
        self.assertTrue(state.meta.get("verify_passed"))
        # verify 被重复调度，第二次才算通过
        self.assertGreaterEqual(state.attempt_of("verify"), 2)

    def test_artifact_version_increments(self):
        _, state, _, _ = run_flow(buggy_first_impl=True)
        art = state.artifact("solution.py")
        self.assertGreater(art.version, 1, "修复后 solution.py 版本应自增")

    def test_message_bus_recorded(self):
        _, state, _, _ = run_flow()
        msgs = state.bus.history()
        self.assertGreater(len(msgs), 3)
        receivers = {m.receiver for m in msgs}
        self.assertIn("设计Agent", receivers)
        self.assertIn("编码Agent(实现)", receivers)
        self.assertIn("编码Agent(测试)", receivers)

    def test_state_snapshot_roundtrip(self):
        _, state, _, _ = run_flow()
        snap = state.snapshot()
        restored = WorkflowState(task=snap["task"], meta=snap["meta"])
        for k, v in snap["artifacts"].items():
            restored.write(k, v["content"], producer=v["producer"])
        self.assertEqual(restored.read("01_requirements.md"),
                         state.read("01_requirements.md"))

    def test_syntax_only_mode(self):
        """--no-exec：只做语法检查也应判定通过。"""
        _, state, report, _ = run_flow(execute=False)
        self.assertEqual(report.status, "success")
        self.assertTrue(state.meta.get("verify_passed"))

    def test_node_failure_aborts(self):
        """节点重试耗尽后引擎应优雅降级：报告标记 failed，而不是崩溃。"""
        from src.agents import RequirementsAgent

        agent = RequirementsAgent(FailingLLM())
        graph = WorkflowGraph(name="t")
        graph.add(Node(name="requirements", handler=agent.run, routes=[], max_retries=1))
        state = WorkflowState(task="x")
        state.write("00_requirement.md", "需求", producer="user")
        engine = WorkflowEngine(verbose=False)
        report = engine.run(graph, state)
        self.assertEqual(report.status, "failed")
        self.assertIsNotNone(report.error)
        # 失败节点的状态要被记录下来，便于排障与续跑
        self.assertEqual(state.runs()[0].status, "failed")

    def test_graph_validation(self):
        graph = WorkflowGraph(name="bad")
        graph.add(Node(name="a", handler=lambda s: NodeResult(), deps=["不存在"]))
        with self.assertRaises(GraphValidationError):
            graph.validate()

    def test_strip_fences(self):
        self.assertEqual(strip_fences("```python\nx = 1\n```"), "x = 1")
        self.assertEqual(strip_fences("plain"), "plain")

    def test_mermaid_export(self):
        g, _ = build_workflow(SimulatedLLM(), requirement="x")
        text = g.mermaid()
        self.assertIn("flowchart TD", text)
        self.assertIn("verify -->|失败重试| fix", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
