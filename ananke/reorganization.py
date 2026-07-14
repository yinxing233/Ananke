from typing import Any, Dict, List

from ananke.config import Config
from ananke.embedding import EmbeddingEngine
from ananke.models import MemoryEntry

# 约束真实 LLM 只做最窄的三选一判断，降低误判（文档第六节）。
_SYSTEM_PROMPT = (
    "你是一个严谨的记忆关系判断器。只允许回答以下三个词之一：合并、矛盾、无关。"
    "不要解释，不要任何多余的字符（不要标点、不要引号）。"
)


def check_local_reorganization(
    new_memory: MemoryEntry,
    memory_store,  # 需要有 get_consolidated_memories() 方法
    embedding_engine: EmbeddingEngine,
    llm_client: Any,
) -> List[Dict[str, Any]]:
    logs = []
    existing = [
        m for m in memory_store.get_consolidated_memories() if m.id != new_memory.id
    ]
    if not existing:
        return logs

    new_vec = embedding_engine.encode(new_memory.content)[0]
    existing_vecs = embedding_engine.encode([m.content for m in existing])

    for i, mem in enumerate(existing):
        sim = embedding_engine.cosine_similarity(new_vec, existing_vecs[i])
        if sim >= Config.REORG_SIMILARITY_THRESHOLD:
            prompt = (
                f"记忆A：{new_memory.content}\n"
                f"记忆B：{mem.content}\n\n"
                "这两条记忆的关系是什么？请只回答一个词：合并、矛盾 或 无关。"
            )
            response = llm_client.call_llm(prompt, system_prompt=_SYSTEM_PROMPT, temperature=0.0).strip()
            if "矛盾" in response:
                action = "conflict"
            elif "合并" in response:
                action = "merge"
            else:
                action = "irrelevant"

            if action in ("merge", "conflict"):
                new_memory.local_reorganization_trigger += 1
                memory_store.update(new_memory)
                logs.append(
                    {
                        "trigger_memory_id": new_memory.id,
                        "paired_memory_id": mem.id,
                        "action": action,
                        "cosine_similarity": sim,
                    }
                )
    return logs
