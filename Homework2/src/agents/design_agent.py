# -*- coding: utf-8 -*-
"""设计 Agent：把需求规格变成模块划分 + 接口定义的设计说明书。"""

from __future__ import annotations

from ..core.node import NodeResult
from ..core.state import WorkflowState
from .base import BaseAgent

SYSTEM_PROMPT = """你是一名资深软件架构师（Software Architect）。

你的任务：基于《需求规格说明书》，产出一份编码 Agent 可以直接照着写代码的
《软件设计说明书》。

硬性要求：
1. 全中文输出，使用 Markdown。
2. 只输出文档本身，不要开场白与客套话。
3. 技术栈固定为 **Python 3 单文件模块 solution.py**，只允许使用标准库，
   除非需求明确要求外部依赖。
4. 接口定义必须精确到函数签名（含类型注解）与返回值语义，
   编码 Agent 会严格照抄，所以不能含糊。
5. 模块数量控制在 3-5 个，接口控制在 8 个以内，保持 MVP 的克制。

文档结构（严格按此顺序）：
# 软件设计说明书
## 1. 架构总览
## 2. 模块划分
## 3. 接口定义
## 4. 核心数据结构
## 5. 关键流程
## 6. 异常与边界处理
## 7. 测试要点
"""

USER_TEMPLATE = """《需求规格说明书》如下：

{srs}

请输出《软件设计说明书》。"""


class DesignAgent(BaseAgent):
    """设计 Agent。"""

    def __init__(self, llm) -> None:
        super().__init__(
            name="设计Agent",
            role="软件架构师",
            llm=llm,
            system_prompt=SYSTEM_PROMPT,
            description="把 SRS 转成模块划分与接口定义",
        )

    def run(self, state: WorkflowState) -> NodeResult:
        srs = self.read(state, "01_requirements.md")
        if not srs.strip():
            raise ValueError("需求规格为空，无法进行设计")

        doc = self.think(USER_TEMPLATE.format(srs=srs))

        # 设计完成后同时通知编码 Agent 的两个并行分支
        for receiver in ("编码Agent(实现)", "编码Agent(测试)"):
            self.send(
                state,
                receiver=receiver,
                msg_type="artifact",
                payload=f"设计说明书已完成，请基于 02_design.md 开始工作。",
                refs=["02_design.md"],
            )
        return NodeResult(
            summary=f"设计文档完成（{len(doc)} 字符，耗时 {self.last_latency}s）",
            outputs={"02_design.md": doc},
        )
