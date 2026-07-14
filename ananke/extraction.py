import json
import re
from typing import List

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


def extract_memories(user_input: str, llm_client) -> List[str]:
    prompt = ("Extract short, atomic facts worth remembering long-term from the input below. "
              "Output language must match the input language. Output only a JSON array of strings; "
              "if none, output [].\nUser input: " + user_input)
    response = llm_client.call_llm(prompt, system_prompt=_SYSTEM_PROMPT, temperature=0.0).strip()
    try: items = json.loads(response)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", response)
        if not match: return []
        try: items = json.loads(match.group())
        except json.JSONDecodeError: return []
    if not isinstance(items, list):
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]
