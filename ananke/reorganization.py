"""Local reorganization event sink (protocol v4 §4).

v3 中 check_local_reorganization 自己跑余弦 + 调 LLM 三选一。v4 把重组判定吸收进
召回-分类两段式：关系分类器在 pipeline 写入阶段直接产出 contradict/mergeable 事件，
本模块只负责**接收事件、对受体记忆 e 累加触发、写审计日志**（不再自己召回/分类）。

- mergeable  → e.local_reorganization_trigger += 1
- contradict → e.conflict_trigger += 1
两者均计入 e.total_activation（频率对照组的一致性强度代理），并触发 local_reorganization 审计事件。
"""

from datetime import datetime
from typing import Any, Dict

from ananke.config import Config
from ananke.models import MemoryEntry
from ananke.relation import REL_CONTRADICT, REL_MERGEABLE


def apply_relation_event(
    memory_store,
    event_logger,
    recipient: MemoryEntry,
    action: str,
    similarity: float,
    incoming_content: str,
) -> MemoryEntry:
    """对受体记忆 recipient 应用一次重组事件，返回更新后的记忆。"""
    if action == REL_CONTRADICT:
        recipient.conflict_trigger += 1
    elif action == REL_MERGEABLE:
        recipient.local_reorganization_trigger += 1
    else:
        # 非重组事件（理论上不应到达此处），原样返回。
        return recipient

    recipient.total_activation += 1
    recipient.last_activated_at = datetime.now()
    memory_store.update(recipient)
    event_logger.log(
        "local_reorganization",
        recipient_memory_id=recipient.id,
        incoming_content=incoming_content[:120],
        action=action,
        cosine_similarity=round(similarity, 3),
        local_reorganization_trigger=recipient.local_reorganization_trigger,
        conflict_trigger=recipient.conflict_trigger,
    )
    return recipient


def pending_core_candidates(memory_store) -> Dict[str, MemoryEntry]:
    """返回下一轮 process 会升 CORE 的巩固层记忆（供观察/调试）。

    条件 = local_reorganization_trigger ≥ LOCAL_REORG_THRESHOLD 且未被矛盾阻断
    （conflict_trigger == 0）。被矛盾触发的记忆即便 merge trigger 达标也升不进 CORE。
    """
    out: Dict[str, MemoryEntry] = {}
    for m in memory_store.get_consolidated_memories():
        if (
            m.local_reorganization_trigger >= Config.LOCAL_REORG_THRESHOLD
            and m.conflict_trigger == 0
        ):
            out[m.id] = m
    return out
