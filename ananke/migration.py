from typing import List

from ananke.config import Config
from ananke.models import LayerEnum, MemoryEntry
from ananke.promotion import WorkingPromotionStrategy, promotion_strategy_from_config


def enforce_working_capacity(memory_store, event_logger, strategy=None) -> None:
    """工作层容量淘汰。淘汰度量跟随当前激活的迁移策略（#13 修复）：

    - persistence 模式 → 用 persistence_score 淘汰最低分者；
    - frequency 模式 → 用 frequency_score 淘汰最低分者。

    两种分数均为"越高越该保留"，故始终淘汰最低分者。修复前硬编码 persistence_score，
    会使纯 Internal Selection 的淘汰条件被外部选择压力污染。

    注：MVP v0.1 的 Phase 1/3 实验记忆数（21）< 工作层容量（50），淘汰从未触发，
    既有结果不受此修复影响；此修复仅为逻辑自洽。
    """
    if strategy is None:
        strategy = promotion_strategy_from_config()
    working = memory_store.get_working_memories()
    while len(working) > Config.WORKING_CAPACITY:
        evicted = min(working, key=lambda memory: strategy.score(memory))
        memory_store.remove(evicted)
        event_logger.log(
            "working_eviction",
            memory_id=evicted.id,
            strategy=strategy.name,
            eviction_score=strategy.score(evicted),
        )
        working.remove(evicted)


def promote_working_memories(
    memory_store,
    event_logger,
    strategy: WorkingPromotionStrategy | None = None,
) -> List[MemoryEntry]:
    strategy = strategy or promotion_strategy_from_config()
    promoted = []
    for memory in memory_store.get_working_memories():
        if strategy.should_promote(memory):
            score = strategy.score(memory)
            memory_store.move(memory, LayerEnum.CONSOLIDATED)
            event_logger.log(
                "working_to_consolidated",
                memory_id=memory.id,
                migration_strategy=strategy.name,
                migration_score=score,
                persistence_score=memory.persistence_score,
                frequency_score=memory.frequency_score,
            )
            promoted.append(memory)
    return promoted


def promote_consolidated_memories(memory_store, event_logger) -> List[MemoryEntry]:
    promoted = []
    for memory in memory_store.get_consolidated_memories():
        if memory.local_reorganization_trigger >= Config.LOCAL_REORG_THRESHOLD:
            count = memory.local_reorganization_trigger
            memory_store.move(memory, LayerEnum.CORE)
            event_logger.log("consolidated_to_core", memory_id=memory.id, local_reorganization_trigger=count)
            promoted.append(memory)
    return promoted
