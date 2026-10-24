# -*- coding: utf-8 -*-
"""工作流共享状态（Blackboard 黑板模型）。

为什么用黑板模型而不是「上一个节点的输出直接传给下一个节点」：
- 并行分支（coding / testing）需要同时读取同一份设计文档；
- 循环修复时，fix 节点要读取历史实现与错误信息；
- 状态可整体快照（snapshot / restore），从而支持断点续跑与事后复现。

黑板上的每个条目都是带版本号的 Artifact，写入会自增版本，
用于在报告中展示「谁在什么时候改了什么」。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .message import MessageBus


@dataclass
class Artifact:
    """黑板上的一个产物件。"""

    key: str
    content: str
    producer: str
    version: int = 1
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "producer": self.producer,
            "version": self.version,
            "updated_at": self.updated_at,
            "size": len(self.content),
            "content": self.content,
        }


@dataclass
class NodeRun:
    """一次节点执行的记录。"""

    name: str
    attempt: int
    status: str                 # pending / running / success / failed / skipped
    started_at: float | None = None
    finished_at: float | None = None
    summary: str = ""
    error: str | None = None

    @property
    def duration(self) -> float:
        if self.started_at is None or self.finished_at is None:
            return 0.0
        return round(self.finished_at - self.started_at, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "attempt": self.attempt,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
            "summary": self.summary,
            "error": self.error,
        }


class WorkflowState:
    """线程安全的共享状态。"""

    def __init__(self, task: str = "", meta: dict[str, Any] | None = None) -> None:
        self._lock = threading.RLock()
        self.task = task
        self.meta: dict[str, Any] = dict(meta or {})
        self.bus = MessageBus()
        self._artifacts: dict[str, Artifact] = {}
        self._runs: dict[str, NodeRun] = {}
        self._attempts: dict[str, int] = {}
        self._executed: set[str] = set()
        self._activated: set[str] = set()
        self.started_at = time.time()
        self.finished_at: float | None = None

    # ---------- 黑板读写 ----------
    def write(self, key: str, content: str, producer: str) -> Artifact:
        with self._lock:
            old = self._artifacts.get(key)
            version = (old.version + 1) if old else 1
            art = Artifact(key=key, content=str(content), producer=producer, version=version)
            self._artifacts[key] = art
        return art

    def read(self, key: str, default: str | None = None) -> str:
        with self._lock:
            art = self._artifacts.get(key)
            return art.content if art else (default or "")

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._artifacts

    def artifact(self, key: str) -> Artifact | None:
        with self._lock:
            return self._artifacts.get(key)

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._artifacts.keys())

    def artifacts(self) -> dict[str, Artifact]:
        with self._lock:
            return dict(self._artifacts)

    # ---------- 节点执行记录 ----------
    def mark(self, name: str, attempt: int, status: str, **kw) -> NodeRun:
        with self._lock:
            run = self._runs.get(name)
            if run is None or run.attempt != attempt:
                run = NodeRun(name=name, attempt=attempt, status=status)
                self._runs[name] = run
            run.status = status
            for k, v in kw.items():
                setattr(run, k, v)
            return run

    def runs(self) -> list[NodeRun]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: (r.started_at or 0, r.name))

    def next_attempt(self, name: str) -> int:
        with self._lock:
            n = self._attempts.get(name, 0) + 1
            self._attempts[name] = n
            return n

    def attempt_of(self, name: str) -> int:
        with self._lock:
            return self._attempts.get(name, 0)

    def mark_executed(self, name: str) -> None:
        with self._lock:
            self._executed.add(name)

    def reset_node(self, name: str) -> None:
        """重置节点，使其可以被再次调度（用于循环边）。"""
        with self._lock:
            self._executed.discard(name)

    def is_executed(self, name: str) -> bool:
        with self._lock:
            return name in self._executed

    def activate(self, name: str) -> None:
        with self._lock:
            self._activated.add(name)

    def is_activated(self, name: str) -> bool:
        with self._lock:
            return name in self._activated

    def activated(self) -> set[str]:
        with self._lock:
            return set(self._activated)

    # ---------- 快照 / 恢复 ----------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "task": self.task,
                "meta": self.meta,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "artifacts": {k: v.to_dict() for k, v in self._artifacts.items()},
                "runs": [r.to_dict() for r in self._runs.values()],
                "attempts": dict(self._attempts),
                "executed": sorted(self._executed),
                "activated": sorted(self._activated),
                "messages": self.bus.to_dict(),
            }

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def restore(cls, path: str | Path) -> "WorkflowState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        st = cls(task=data.get("task", ""), meta=data.get("meta", {}))
        st.started_at = data.get("started_at", time.time())
        st.finished_at = data.get("finished_at")
        for k, v in data.get("artifacts", {}).items():
            st._artifacts[k] = Artifact(
                key=k,
                content=v["content"],
                producer=v["producer"],
                version=v["version"],
                updated_at=v["updated_at"],
            )
        for r in data.get("runs", []):
            st._runs[r["name"]] = NodeRun(
                name=r["name"],
                attempt=r["attempt"],
                status=r["status"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                summary=r.get("summary", ""),
                error=r.get("error"),
            )
        st._attempts = dict(data.get("attempts", {}))
        st._executed = set(data.get("executed", []))
        st._activated = set(data.get("activated", []))
        return st
