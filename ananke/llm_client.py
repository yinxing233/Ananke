"""LLM 接入层：可切换 provider 的抽象。

设计目标：
- 密钥只来自环境变量 / .env，绝不硬编码，且 .env 已被 .gitignore 忽略。
- 通过 .env 里的 LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 切换不同
  服务商（OpenAI / DeepSeek / OpenRouter / Groq / Ollama / Gemini 等），无需改代码。
- 保留 MockLLMClient，离线、无需密钥即可跑通迁移/激活逻辑。

切换方式（run.py 自动按 Config 选择）：
- USE_MOCK_LLM=true   -> MockLLMClient
- USE_MOCK_LLM=false  -> 按 LLM_PROVIDER 选择真实后端

说明：Gemini 走其官方提供的 OpenAI 兼容接口（v1beta/openai），因此无需新增依赖，
  仅靠 .env 的 LLM_BASE_URL + LLM_API_KEY + LLM_MODEL 即可，与 DeepSeek 等完全一致。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from ananke.config import Config

# 所有走 OpenAI 兼容 Chat Completions 接口的服务商都归到这一类，仅靠 base_url 区分。
_OPENAI_COMPATIBLE = {"openai", "deepseek", "openrouter", "groq", "ollama", "openai-compatible", "gemini"}

# Gemini 官方提供的 OpenAI 兼容接口地址；用户若不显式设置 LLM_BASE_URL 则使用它。
_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class BaseLLMClient(ABC):
    """所有 LLM 后端必须实现的接口。pipeline / extraction / reorganization 只依赖它。"""

    @abstractmethod
    def call_llm(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """返回模型文本回复。system_prompt 与 temperature 为可选覆盖。"""
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """离线调试用：根据 prompt 关键词返回确定性结果，方便跑通迁移/激活/重组逻辑。"""

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        # 针对记忆提取
        if "提取" in prompt or "extract" in prompt.lower():
            return '["用户喜欢打羽毛球", "用户养了一只猫"]'
        # 针对局部重组判断：prompt 里同时含有"合并""矛盾"二字，mock 无法判断语义，
        # 诚实返回"无关"，避免在 mock 模式下误触发中→慢迁移。真实判断交给真实 LLM。
        if "记忆A" in prompt:
            return "无关"
        if "矛盾" in prompt:
            return "矛盾"
        if "合并" in prompt or "merge" in prompt.lower():
            return "合并"
        return "无关"


class OpenAICompatibleClient(BaseLLMClient):
    """基于 openai SDK 的 OpenAI 兼容后端。DeepSeek / OpenRouter / Groq / Ollama / OpenAI 通用。

    切换服务商只需改 .env：
        LLM_PROVIDER=deepseek
        LLM_BASE_URL=https://api.deepseek.com/v1
        LLM_API_KEY=sk-...
        LLM_MODEL=deepseek-chat
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else Config.LLM_API_KEY
        self.base_url = base_url if base_url is not None else Config.LLM_BASE_URL
        self.model = model if model is not None else Config.LLM_MODEL
        self.temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        # 延迟导入，避免未安装 openai 时影响 mock 模式 / 测试。
        from openai import OpenAI

        if not self.api_key:
            raise RuntimeError(
                "未配置 LLM_API_KEY。请在项目根目录的 .env 中设置 LLM_API_KEY，"
                "或把 USE_MOCK_LLM 设为 true 使用 Mock LLM。"
            )
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        # 真实 API 限流（如 Gemini 免费层 15 req/min）是常态，做指数退避重试，
        # 保证任意长度语料都能跑完。仅 I/O 韧性，不影响任何理论行为。
        from openai import RateLimitError

        delay = 8.0
        last_err: Optional[Exception] = None
        for attempt in range(6):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                )
                return (response.choices[0].message.content or "").strip()
            except RateLimitError as e:
                last_err = e
                wait = min(delay * (2 ** attempt), 60.0)
                print(f"[warn] LLM 限流(429)，{wait:.0f}s 后重试 ({attempt + 1}/6)…")
                time.sleep(wait)
        assert last_err is not None
        raise last_err


def create_llm_client() -> BaseLLMClient:
    """按 Config 选择后端。run.py 直接调用它，无需关心具体实现。"""
    if Config.USE_MOCK_LLM:
        return MockLLMClient()
    if Config.LLM_PROVIDER in _OPENAI_COMPATIBLE:
        # Gemini 走官方 OpenAI 兼容接口；未显式设置 base_url 时补默认值。
        base_url = Config.LLM_BASE_URL
        if Config.LLM_PROVIDER == "gemini" and not base_url:
            base_url = _GEMINI_OPENAI_BASE_URL
        return OpenAICompatibleClient(base_url=base_url)
    raise ValueError(
        f"不支持的 LLM_PROVIDER={Config.LLM_PROVIDER!r}。"
        f"可选：{', '.join(sorted(_OPENAI_COMPATIBLE))}；"
        "如需 Anthropic 等其它后端，请在 llm_client.py 增加对应子类并注册到工厂。"
    )
