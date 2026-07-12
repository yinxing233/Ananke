from ananke.config import Config


class LLMClient:
    def __init__(self, use_mock: bool = None):
        self.use_mock = use_mock if use_mock is not None else Config.USE_MOCK_LLM

    def call_llm(self, prompt: str, system_prompt: str = None) -> str:
        if self.use_mock:
            return self._mock_response(prompt)
        # ---- 这里换成你真实的 API 调用逻辑 ----
        # import openai / anthropic ...
        # return real_response
        return ""

    def _mock_response(self, prompt: str) -> str:
        # 针对记忆提取
        if "提取" in prompt or "extract" in prompt.lower():
            return '["用户喜欢打羽毛球", "用户养了一只猫"]'
        # 针对局部重组判断
        if "矛盾" in prompt:
            return "矛盾"
        if "合并" in prompt or "merge" in prompt.lower():
            return "合并"
        return "无关"
