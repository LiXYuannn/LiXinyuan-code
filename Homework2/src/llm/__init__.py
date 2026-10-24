# -*- coding: utf-8 -*-
"""LLM 接入层。"""

from .base import LLMBackend, extract_block, strip_fences
from .config import LLMConfig
from .openai_client import OpenAICompatLLM, build_llm
from .simulated import SimulatedLLM

__all__ = [
    "LLMBackend",
    "LLMConfig",
    "OpenAICompatLLM",
    "SimulatedLLM",
    "build_llm",
    "extract_block",
    "strip_fences",
]
