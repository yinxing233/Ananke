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

import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from ananke.config import Config


class _RateLimiter:
    """Token-bucket RPM 节流器。纯 I/O 韧性，不影响任何理论行为。

    与 call_llm 内的 429 指数退避互补：退避是「撞墙后恢复」，节流是「预防性不撞墙」。
    rpm<=0 表示不节流（如 deepseek 评判端限额高）。
    """

    def __init__(self, rpm: int) -> None:
        self.rpm = float(rpm)
        self.rate = self.rpm / 60.0 if self.rpm > 0 else 0.0
        self.capacity = max(int(self.rpm), 1)
        self.tokens = float(self.capacity)
        self.last = time.time()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.rate <= 0:
            return
        while True:
            with self._lock:
                now = time.time()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate
            time.sleep(wait + 0.01)


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
        rpm: Optional[int] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else Config.LLM_API_KEY
        self.base_url = base_url if base_url is not None else Config.LLM_BASE_URL
        self.model = model if model is not None else Config.LLM_MODEL
        self.temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        # RPM 节流（I/O 韧性）：未显式传 rpm 时用 Config.LLM_RPM（驱动端默认 30）。
        # 评判端传 rpm=Config.EVAL_LLM_RPM（默认 0=不限，因默认 deepseek）。
        self._limiter = _RateLimiter(rpm if rpm is not None else Config.LLM_RPM)
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

        self._limiter.acquire()  # 预防性 RPM 节流（纯 I/O 韧性，不影响理论行为）
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


def create_eval_llm_client() -> BaseLLMClient:
    """v4 §5 评估独立性：评判端主裁判，**不同家族** LLM。

    与驱动端（embedding + Gemini 提取）刻意分离，结构化判定
    「记忆 X 是否包含回答问题 Q 所需事实：包含/部分/不包含」。
    评估端**禁止出现嵌入模型**（防驱动-评判度量循环）。

    工厂逻辑：
      · USE_MOCK_LLM=true 或缺少评估端密钥 → MockEvaluationJudge（子串匹配，仅供冒烟）。
      · 否则用 Config.EVAL_LLM_* 构造 OpenAICompatibleClient（默认 deepseek，与驱动端不同家族）。
    """
    if Config.USE_MOCK_LLM or not Config.EVAL_LLM_API_KEY:
        return MockEvaluationJudge()
    provider = Config.EVAL_LLM_PROVIDER
    if provider in _OPENAI_COMPATIBLE:
        return OpenAICompatibleClient(
            api_key=Config.EVAL_LLM_API_KEY,
            base_url=Config.EVAL_LLM_BASE_URL or None,
            model=Config.EVAL_LLM_MODEL,
            temperature=0.0,
            rpm=Config.EVAL_LLM_RPM,
        )
    raise ValueError(
        f"不支持的 EVAL_LLM_PROVIDER={provider!r}。"
        f"可选：{', '.join(sorted(_OPENAI_COMPATIBLE))}"
    )


class MockEvaluationJudge(BaseLLMClient):
    """评估端冒烟用：用子串匹配近似「包含/部分/不包含」，仅供开发期跑通管道。

    诚实声明：这不是真实语义评判，仅验证 evaluate.py 的 IO 与计分管线。
    真实评估必须由不同家族 LLM 主裁判完成（v4 §5）。
    """

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        # prompt 形如：记忆=<content>。问题=<question>。请判定…
        import re
        mem_m = re.search(r"记忆=([^\n。]*)", prompt)
        q_m = re.search(r"问题=([^\n。]*)", prompt)
        if not mem_m or not q_m:
            return "不包含"
        content, question = mem_m.group(1).strip(), q_m.group(1).strip()
        # 取问题里 2 字以上的实词（粗略：非标点连续段），任一出现在记忆中 → 包含/部分
        tokens = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", question)]
        hit = sum(1 for t in tokens if t in content)
        if not tokens:
            return "不包含"
        if hit == len(tokens):
            return "包含"
        if hit >= 1:
            return "部分"
        return "不包含"
