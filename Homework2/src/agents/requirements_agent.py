# -*- coding: utf-8 -*-
"""需求 Agent：把一句话原始需求变成结构化的需求规格说明书（SRS）。"""

from __future__ import annotations

from ..core.node import NodeResult
from ..core.state import WorkflowState
from .base import BaseAgent

SYSTEM_PROMPT = """你是一名资深软件需求分析师（Requirements Analyst）。

你的任务：把用户给的原始需求，整理成一份可直接交付给设计师的《需求规格说明书》。

硬性要求：
1. 全中文输出，使用 Markdown。
2. 只输出文档本身，不要出现"好的""以下是"之类的开场白与结尾客套话。
3. 需求条目必须编号（FR-01、NFR-01、AC-01），便于后续追溯。
4. 对原始需求中模糊、缺失的信息，做出合理假设，并在"假设与约束"中显式列出。
5. 输出的规模要克制：功能需求控制在 5-8 条，不要无限发散。

文档结构（严格按此顺序）：
# 需求规格说明书
## 1. 项目概述
## 2. 术语表
## 3. 功能需求（FR-01 …）
## 4. 非功能需求（NFR-01 …）
## 5. 输入输出约定
## 6. 验收标准（AC-01 …）
## 7. 假设与约束
"""

USER_TEMPLATE = """原始需求如下：

{requirement}

请输出《需求规格说明书》。"""


class RequirementsAgent(BaseAgent):
    """需求 Agent。"""

    def __init__(self, llm) -> None:
        super().__init__(
            name="需求Agent",
            role="需求分析师",
            llm=llm,
            system_prompt=SYSTEM_PROMPT,
            description="把原始需求结构化成 SRS",
        )

    def run(self, state: WorkflowState) -> NodeResult:
        requirement = self.read(state, "00_requirement.md")
        if not requirement.strip():
            raise ValueError("原始需求为空，无法进行需求分析")

        doc = self.think(USER_TEMPLATE.format(requirement=requirement))

        # 把分析结果交给设计 Agent，消息体只放摘要 + 引用键
        self.send(
            state,
            receiver="设计Agent",
            msg_type="artifact",
            payload=(
                f"需求规格已完成，共 {len(doc)} 字符；"
                f"请基于 01_requirements.md 进行设计。"
            ),
            refs=["01_requirements.md"],
        )
        return NodeResult(
            summary=f"SRS 完成（{len(doc)} 字符，耗时 {self.last_latency}s）",
            outputs={"01_requirements.md": doc},
        )
