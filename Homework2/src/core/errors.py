# -*- coding: utf-8 -*-
"""异常体系。

统一的异常层次让引擎可以做「分级处理」：
- ConfigError：配置问题，属于用户可修复错误，不应重试。
- LLMError：外部服务错误，可重试。
- NodeExecutionError：节点内部错误，可重试。
"""


class WorkflowError(Exception):
    """所有工作流异常的基类。"""


class ConfigError(WorkflowError):
    """配置缺失或非法（缺少 API Key、Base URL 等）。"""


class LLMError(WorkflowError):
    """大模型调用失败（网络、鉴权、限流、返回体异常）。"""


class NodeExecutionError(WorkflowError):
    """节点执行失败。"""

    def __init__(self, node: str, message: str, cause: Exception | None = None):
        self.node = node
        self.cause = cause
        detail = f"节点 [{node}] 执行失败：{message}"
        if cause is not None:
            detail += f"（原因：{cause}）"
        super().__init__(detail)


class MaxRetriesExceeded(WorkflowError):
    """节点重试次数耗尽。"""

    def __init__(self, node: str, attempts: int):
        self.node = node
        self.attempts = attempts
        super().__init__(f"节点 [{node}] 已重试 {attempts} 次仍失败，终止流程。")


class GraphValidationError(WorkflowError):
    """工作流图结构非法（依赖不存在、存在环等）。"""


class NodeTimeout(WorkflowError):
    """节点执行超时。"""

    def __init__(self, node: str, timeout: float):
        self.node = node
        self.timeout = timeout
        super().__init__(f"节点 [{node}] 执行超过 {timeout}s。")
