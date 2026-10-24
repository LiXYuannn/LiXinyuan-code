# -*- coding: utf-8 -*-
"""LLM 配置加载（优先 os.environ，其次项目根目录 .env）。

不引入 python-dotenv，用一个 20 行的解析器换取零第三方依赖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..core.errors import ConfigError


def _load_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE，支持 # 注释与引号。"""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 去掉行尾注释（仅当 # 前面有空格时，避免误伤 key 里的 #）
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        data[key] = value
    return data


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: float = 120.0
    max_retries: int = 3
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, dotenv: str | Path | None = ".env") -> "LLMConfig":
        file_values = _load_dotenv(Path(dotenv)) if dotenv else {}

        def pick(key: str, default: str = "") -> str:
            return os.environ.get(key) or file_values.get(key) or default

        cfg = cls(
            api_key=pick("LLM_API_KEY") or pick("OPENAI_API_KEY"),
            base_url=pick("LLM_BASE_URL", "https://api.openai.com/v1"),
            model=pick("LLM_MODEL", "gpt-4o-mini"),
            temperature=float(pick("LLM_TEMPERATURE", "0.3")),
            max_tokens=int(pick("LLM_MAX_TOKENS", "4096")),
            timeout=float(pick("LLM_TIMEOUT", "120")),
            max_retries=int(pick("LLM_MAX_RETRIES", "3")),
        )
        return cfg

    def validate(self) -> None:
        """配置合法性检查，缺什么就明确报错，避免到运行时才失败。"""
        if not self.api_key:
            raise ConfigError(
                "未检测到 LLM_API_KEY。请在项目根目录创建 .env（可复制 .env.example），"
                "或直接在环境变量中设置 LLM_API_KEY。"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigError(f"LLM_BASE_URL 必须是 http/https 地址，当前为：{self.base_url}")
        if not self.model:
            raise ConfigError("LLM_MODEL 不能为空。")

    def endpoint(self) -> str:
        """推导 /chat/completions 地址。"""
        base = self.base_url.rstrip("/")
        if not base.endswith(("/v1", "/v2", "/v3", "/v4")):
            base += "/v1"
        return base + "/chat/completions"
