from typing import List

from ananke.config import Config
from ananke.models import LayerEnum, MemoryEntry
from ananke.promotion import WorkingPromotionStrategy, promotion_strategy_from_config


def enforce_working_capacity(memory_store, event_logger) -> None:
    working = memory_store.get_working_memories()
    while len(working) > Config.WORKING_CAPACITY:
        evicted = min(working, key=lambda memory: memory.persistence_score)
        memory_store.remove(evicted)
        event_logger.log("working_eviction", memory_id=evicted.id, persistence_score=evicted.persistence_score)
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
