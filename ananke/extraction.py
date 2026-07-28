import json
import re
from typing import List, Optional

from ananke.cache import normalize

# 让真实 LLM 稳定输出纯 JSON 数组，而非解释或代码块。
# 关键：输出语言必须与用户输入保持一致，否则跨语言语料下
# 嵌入模型的余弦相似度会失真（英文输入 vs 中文记忆 → 几乎不相似）。
_SYSTEM_PROMPT = (
    "You are a memory extractor. Extract short, atomic facts worth remembering long-term "
    "from the user's input. Output language MUST match the input language "
    "(if input is English, output English; if Chinese, output Chinese). "
    "Output only a JSON array of strings, e.g. [\"User likes badminton\"] or [\"用户喜欢羽毛球\"]. "
    "Do not output any explanation, extra text, or code fences. If nothing is worth remembering, output []."
)

# 用户 prompt 的**固定前缀**（输入变量 user_input 拼在后面）。提取 prompt 模板 =
# _SYSTEM_PROMPT + EXTRACTION_USER_PREFIX，作为缓存 key 的 prompt_hash 来源（B3）。
EXTRACTION_USER_PREFIX = (
    "Extract short, atomic facts worth remembering long-term from the input below. "
    "Output language must match the input language. Output only a JSON array of strings; "
    "if none, output [].\nUser input: "
)
# 完整模板（system + 用户前缀），供 llm_client 构造缓存时算 SHA1。改此模板即全量失效。
EXTRACTION_PROMPT_TEMPLATE = _SYSTEM_PROMPT + EXTRACTION_USER_PREFIX


def extract_memories(user_input: str, llm_client) -> List[str]:
    prompt = EXTRACTION_USER_PREFIX + user_input
    # 两级缓存（提取层）：同输入永远返回首次提取结果 → 重跑/换策略零 API、且给 D 去噪。
    cache = getattr(llm_client, "cache", None)
    norm = normalize(user_input)
    cached = cache.get("extraction", norm) if cache else None
    if cached is not None:
        # 命中：缓存的是规范 JSON 列表字符串（C1），直接解析返回。
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass  # 缓存损坏（不应发生）；视为 miss 重算
    last_err: Optional[Exception] = None
    # 解析失败 / 空响应 = 基础设施故障（超时/429/连接断），不缓存、重试、最终 raise（C2）。
    for _ in range(3):
        try:
            response = llm_client.call_llm(
                prompt, system_prompt=_SYSTEM_PROMPT, temperature=0.0
            ).strip()
            try:
                items = json.loads(response)
            except json.JSONDecodeError:
                match = re.search(r"\[[\s\S]*\]", response)
                if not match:
                    raise ValueError(f"无法解析提取响应: {response!r}")
                try:
                    items = json.loads(match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"提取响应去噪后仍无法解析: {response!r}")
            if not isinstance(items, list):
                raise ValueError("提取结果非列表")
            items = [item.strip() for item in items if isinstance(item, str) and item.strip()]
            # 合法解析出的归一化结果才落盘（C1+C2）：规范 JSON 列表字符串。
            if cache:
                cache.put("extraction", norm, json.dumps(items, ensure_ascii=False))
            return items
        except ValueError as e:
            last_err = e
            continue
    raise last_err or RuntimeError("提取失败（基础设施故障且重试未恢复）")
