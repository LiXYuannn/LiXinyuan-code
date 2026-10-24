# -*- coding: utf-8 -*-
"""Mini SE 工作流：需求 → 设计 → 代码。

拓扑与控制流：

    requirements ──> design ──> coding_impl ──┐
                                coding_test ──┴──> verify
                                                    │
                                        ┌───────────┴───────────┐
                                   （通过/放弃）           （失败且未超轮次）
                                        ↓                       ↓
                                    summarize  <────  fix ──> verify（回边）

控制流覆盖：
- 顺序执行：requirements → design → coding
- 并行执行：coding_impl 与 coding_test 同时就绪，并发跑
- 条件分支：verify 之后按校验结果选择 summarize / fix
- 循环回退：fix → verify 形成回边，最多 max_fix_rounds 轮
"""

from __future__ import annotations

from ..agents import CodingAgent, DesignAgent, RequirementsAgent
from ..core.graph import WorkflowGraph
from ..core.node import Node, Route
from ..core.state import WorkflowState
from ..llm.base import LLMBackend
from ..tools import CodeVerifier, Summarizer

REQUIREMENT_KEY = "00_requirement.md"


def build_workflow(
    llm: LLMBackend,
    requirement: str,
    max_fix_rounds: int = 2,
    execute_tests: bool = True,
    workdir: str | None = None,
) -> tuple[WorkflowGraph, WorkflowState]:
    """装配出一张可执行的图 + 一份初始状态。"""
    req_agent = RequirementsAgent(llm)
    design_agent = DesignAgent(llm)
    impl_agent = CodingAgent(llm, mode="impl")
    test_agent = CodingAgent(llm, mode="test")
    fix_agent = CodingAgent(llm, mode="fix")
    verifier = CodeVerifier(execute=execute_tests, workdir=workdir)
    summarizer = Summarizer()

    def _pass_or_give_up(s: WorkflowState) -> bool:
        """校验通过，或修复轮次已用尽（避免死循环）。"""
        return bool(s.meta.get("verify_passed")) or int(s.meta.get("fix_rounds", 0)) >= max_fix_rounds

    def _need_fix(s: WorkflowState) -> bool:
        return (not s.meta.get("verify_passed")) and int(s.meta.get("fix_rounds", 0)) < max_fix_rounds

    def _fix_handler(s: WorkflowState):
        result = fix_agent.run(s)
        # 记录修复轮次，供路由条件判断是否继续循环
        s.meta["fix_rounds"] = int(s.meta.get("fix_rounds", 0)) + 1
        return result

    graph = WorkflowGraph(
        name="Mini SE Workflow · 需求→设计→代码",
        description="3 个 Agent（需求/设计/编码）+ 1 个校验器 + 1 个汇总器的端到端流水线",
    )
    graph.add(Node(
        name="requirements", handler=req_agent.run, deps=[],
        routes=[Route("design")], kind="agent", role=req_agent.name,
        description="原始需求 → 需求规格说明书（SRS）", max_retries=2,
    ))
    graph.add(Node(
        name="design", handler=design_agent.run, deps=["requirements"],
        routes=[Route("coding_impl"), Route("coding_test")],
        kind="agent", role=design_agent.name,
        description="SRS → 模块划分 + 接口定义", max_retries=2,
    ))
    graph.add(Node(
        name="coding_impl", handler=impl_agent.run, deps=["design"],
        routes=[Route("verify")], kind="agent", role=impl_agent.name,
        description="按设计实现 solution.py", max_retries=2,
    ))
    graph.add(Node(
        name="coding_test", handler=test_agent.run, deps=["design"],
        routes=[Route("verify")], kind="agent", role=test_agent.name,
        description="按设计编写 test_solution.py", max_retries=2,
    ))
    graph.add(Node(
        name="verify", handler=verifier, deps=["coding_impl", "coding_test"],
        routes=[
            Route("summarize", condition=_pass_or_give_up, label="通过/放弃"),
            Route("fix", condition=_need_fix, label="失败重试"),
        ],
        kind="tool", role="代码校验器",
        description="语法检查 + 执行单元测试（确定性守门员）", max_retries=1,
    ))
    graph.add(Node(
        name="fix", handler=_fix_handler, deps=["verify"],
        routes=[Route("verify", label="重新校验")],
        kind="agent", role=fix_agent.name,
        description="根据报错修复实现/测试代码（循环回边）", max_retries=1,
    ))
    graph.add(Node(
        name="summarize", handler=summarizer, deps=["verify"],
        routes=[], kind="tool", role="汇总器",
        description="生成交付物清单", max_retries=1,
    ))
    graph.validate()

    state = WorkflowState(task=requirement, meta={"requirement": requirement})
    state.write(REQUIREMENT_KEY, requirement, producer="user")
    return graph, state
