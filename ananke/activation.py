from datetime import datetime
from typing import List

from ananke.config import Config
from ananke.embedding import EmbeddingEngine
from ananke.models import MemoryEntry


def detect_activations(input_text: str, memory_store, embedding_engine: EmbeddingEngine, event_logger, system_guided: bool = False) -> List[MemoryEntry]:
    candidates = memory_store.get_working_memories() + memory_store.get_consolidated_memories()
    if not candidates:
        return []
    input_vector = embedding_engine.encode(input_text)[0]
    vectors = embedding_engine.encode([memory.content for memory in candidates])
    activated = []
    for memory, vector in zip(candidates, vectors):
        similarity = embedding_engine.cosine_similarity(input_vector, vector)
        if not system_guided and similarity >= Config.EXTERNAL_VALIDATION_THRESHOLD:
            memory.external_validation += 1
            memory.total_activation += 1
            memory.last_activated_at = datetime.now()
            activated.append(memory)
            memory_store.update(memory)
            event_logger.log("external_validation", memory_id=memory.id, input_summary=input_text[:120],
                             cosine_similarity=similarity, external_validation=memory.external_validation)
        elif similarity >= Config.INTERNAL_ACTIVATION_THRESHOLD:
            memory.internal_activation += 1
            memory.total_activation += 1
            memory.last_activated_at = datetime.now()
            activated.append(memory)
            memory_store.update(memory)
            event_logger.log("internal_activation", memory_id=memory.id, input_summary=input_text[:120],
                             internal_activation=memory.internal_activation, cosine_similarity=similarity)
    return activated
