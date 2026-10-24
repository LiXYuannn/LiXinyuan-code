# -*- coding: utf-8 -*-
"""工作流调度引擎。

职责：
1. 拓扑调度：节点的所有依赖执行完毕且已被激活后才可运行；
2. 并行执行：同一时刻就绪的多个节点放进线程池并发跑；
3. 条件路由：节点结束后按其 Route 的 condition 决定走哪条边；
4. 循环回退：目标节点若已执行过则重置，从而实现「修复 -> 重新校验」的环；
5. 错误处理：节点失败自动重试（带退避），耗尽后终止并落盘快照，便于续跑。
"""

from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import MaxRetriesExceeded, NodeExecutionError
from .graph import WorkflowGraph
from .node import Node, NodeResult
from .state import WorkflowState


@dataclass
class RunReport:
    """一次完整运行的执行报告。"""

    workflow: str
    status: str = "pending"        # success | failed | pending
    started_at: float = 0.0
    finished_at: float = 0.0
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def duration(self) -> float:
        return round(self.finished_at - self.started_at, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
            "steps": self.steps,
            "error": self.error,
        }


class WorkflowEngine:
    """最小可用的 Workflow 调度引擎。"""

    def __init__(
        self,
        max_workers: int = 4,
        max_steps: int = 64,
        verbose: bool = True,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.max_workers = max_workers
        self.max_steps = max_steps
        self.verbose = verbose
        self.on_event = on_event

    # ---------- 对外主入口 ----------
    def run(self, graph: WorkflowGraph, state: WorkflowState) -> RunReport:
        graph.validate()
        report = RunReport(workflow=graph.name, started_at=time.time())

        # 入口节点（无依赖）自动激活
        for n in graph.entry_nodes():
            state.activate(n)

        self._emit("workflow_start", {"workflow": graph.name, "nodes": len(graph.nodes)})
        self._log(f"▶ 启动工作流：{graph.name}（{len(graph.nodes)} 个节点）")

        executed_steps = 0
        try:
            while executed_steps < self.max_steps:
                ready = [n for n in graph.nodes.values() if n.is_ready(state)]
                if not ready:
                    break

                if len(ready) > 1:
                    finished = self._run_parallel(ready, state, report)
                else:
                    finished = [self._run_one(ready[0], state, report)]

                executed_steps += len(finished)

                # 处理每个完成节点的出边
                for node in finished:
                    for route in node.next_targets(state):
                        target = route.target
                        if state.is_executed(target):
                            state.reset_node(target)  # 形成回环，允许重复执行
                        state.activate(target)
                        self._emit(
                            "route",
                            {"from": node.name, "to": target, "label": route.label},
                        )
        except NodeExecutionError as e:
            report.status = "failed"
            report.error = str(e)
            self._log(f"✖ {e}")
        finally:
            state.finished_at = time.time()
            report.finished_at = time.time()

        if report.status != "failed":
            failed = [r for r in state.runs() if r.status == "failed"]
            if failed:
                report.status = "failed"
                report.error = f"节点 {failed[0].name} 失败"
            else:
                report.status = "success"

        self._emit("workflow_end", {"status": report.status})
        self._log(f"■ 工作流结束：{report.status}，耗时 {report.duration}s")
        return report

    # ---------- 调度细节 ----------
    def _run_parallel(
        self, nodes: list[Node], state: WorkflowState, report: RunReport
    ) -> list[Node]:
        names = "、".join(n.name for n in nodes)
        self._log(f"  ⇉ 并行执行 {len(nodes)} 个节点：{names}")
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._run_one, n, state, report): n for n in nodes}
            results = []
            for fut, node in futures.items():
                try:
                    results.append(fut.result())
                except NodeExecutionError:
                    raise
            return results

    def _run_one(self, node: Node, state: WorkflowState, report: RunReport) -> Node:
        attempt = state.next_attempt(node.name)
        started = time.time()
        state.mark(node.name, attempt, "running", started_at=started)
        self._emit("node_start", {"node": node.name, "attempt": attempt})
        self._log(f"  → [{node.name}] 第 {attempt} 次执行…")

        last_err: Exception | None = None
        for retry in range(node.max_retries + 1):
            if retry > 0:
                wait = node.retry_backoff * retry
                self._log(f"    ↻ [{node.name}] 重试 {retry}/{node.max_retries}，等待 {wait}s")
                time.sleep(wait)
            try:
                result: NodeResult = node.handler(state)
                # 将节点产物写入黑板（带版本号）
                for key, value in (result.outputs or {}).items():
                    state.write(key, value, producer=node.name)
                finished = time.time()
                state.mark(
                    node.name,
                    attempt,
                    "success",
                    finished_at=finished,
                    summary=result.summary,
                    error=None,
                )
                state.mark_executed(node.name)
                for k, v in (result.extra or {}).items():
                    state.meta[k] = v
                report.steps.append(
                    {
                        "node": node.name,
                        "attempt": attempt,
                        "status": "success",
                        "duration": round(finished - started, 3),
                        "summary": result.summary,
                    }
                )
                self._emit("node_end", {"node": node.name, "status": "success"})
                self._log(
                    f"  ✓ [{node.name}] 完成（{round(finished - started, 2)}s）"
                    f" {result.summary[:60]}"
                )
                return node
            except Exception as exc:  # noqa: BLE001 - 统一收敛为节点错误
                last_err = exc
                self._log(f"    ! [{node.name}] 出错：{exc}")

        err_msg = f"{last_err}\n{traceback.format_exc(limit=3)}" if last_err else "未知错误"
        state.mark(node.name, attempt, "failed", finished_at=time.time(), error=str(last_err))
        report.steps.append(
            {
                "node": node.name,
                "attempt": attempt,
                "status": "failed",
                "duration": round(time.time() - started, 3),
                "summary": str(last_err),
            }
        )
        self._emit("node_end", {"node": node.name, "status": "failed"})
        raise NodeExecutionError(node.name, str(last_err), cause=last_err) from last_err

    # ---------- 辅助 ----------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception:  # noqa: BLE001 - 回调失败不影响主流程
                pass
