# -*- coding: utf-8 -*-
"""OpenAI 兼容 Chat Completions 客户端（零第三方依赖，基于 urllib）。

兼容 OpenAI / DeepSeek / Moonshot / 通义千问 / 智谱 / 本地 vLLM·Ollama 等
一切提供 OpenAI 兼容接口的服务端。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..core.errors import LLMError
from .base import LLMBackend
from .config import LLMConfig


class OpenAICompatLLM:
    """OpenAI 兼容接口实现。"""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_count = 0

    # ---------- LLMBackend ----------
    def chat(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tag: str = "",
    ) -> str:
        cfg = self.config
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": cfg.temperature if temperature is None else temperature,
            "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            cfg.endpoint(),
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
                **cfg.extra_headers,
            },
        )

        last_err: Exception | None = None
        for attempt in range(cfg.max_retries + 1):
            if attempt:
                wait = 2.0 * attempt
                print(f"    ⏳ LLM 调用重试 {attempt}/{cfg.max_retries}（等待 {wait}s）", flush=True)
                time.sleep(wait)
            try:
                with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                return self._parse(raw, tag)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:500]
                # 429 / 5xx 属于可恢复错误，其余（401/404/400）直接抛出
                if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < cfg.max_retries:
                    last_err = LLMError(f"HTTP {e.code}: {detail}")
                    continue
                raise LLMError(f"LLM 调用失败 HTTP {e.code}: {detail}") from e
            except urllib.error.URLError as e:
                last_err = LLMError(f"网络错误：{e.reason}")
                if attempt >= cfg.max_retries:
                    raise last_err from e
            except TimeoutError as e:
                last_err = LLMError(f"请求超时（{cfg.timeout}s）")
                if attempt >= cfg.max_retries:
                    raise last_err from e
        raise last_err or LLMError("LLM 调用失败（未知原因）")

    # ---------- 内部 ----------
    def _parse(self, raw: str, tag: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"响应不是合法 JSON：{raw[:300]}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"响应结构异常：{json.dumps(data, ensure_ascii=False)[:300]}") from e
        usage = data.get("usage") or {}
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)
        self.call_count += 1
        return (content or "").strip()

    def usage(self) -> dict[str, int]:
        return {
            "calls": self.call_count,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
        }


def build_llm(config: LLMConfig) -> LLMBackend:
    """工厂方法：校验配置并构造后端。"""
    config.validate()
    return OpenAICompatLLM(config)
