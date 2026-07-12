import json
import re
from typing import List


def extract_memories(user_input: str, llm_client) -> List[str]:
    prompt = "从以下用户输入中提取值得长期保留的、简短且原子化的事实。只输出 JSON 字符串数组；没有事实则输出 []。\n用户输入：" + user_input
    response = llm_client.call_llm(prompt).strip()
    try: items = json.loads(response)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", response)
        if not match: return []
        try: items = json.loads(match.group())
        except json.JSONDecodeError: return []
    if not isinstance(items, list):
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]
