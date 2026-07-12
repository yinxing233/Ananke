from uuid import uuid4
from typing import Dict, List

from ananke.activation import detect_activations
from ananke.extraction import extract_memories
from ananke.migration import enforce_working_capacity, promote_consolidated_memories, promote_working_memories
from ananke.models import MemoryEntry
from ananke.reorganization import check_local_reorganization


class MemoryPipeline:
    """Orchestrates the one-way three-layer memory lifecycle from the MVP spec."""

    def __init__(self, memory_store, embedding_engine, llm_client, event_logger, promotion_strategy=None):
        self.memory_store = memory_store
        self.embedding_engine = embedding_engine
        self.llm_client = llm_client
        self.event_logger = event_logger
        self.promotion_strategy = promotion_strategy

    def process(self, user_input: str, *, system_guided: bool = False) -> Dict[str, List]:
        activated = detect_activations(user_input, self.memory_store, self.embedding_engine, self.event_logger, system_guided)
        written = []
        for content in extract_memories(user_input, self.llm_client):
            memory = MemoryEntry(id=str(uuid4()), content=content)
            self.memory_store.add(memory)
            self.event_logger.log("memory_write", memory_id=memory.id, content_summary=content[:120], layer=memory.layer.value)
            written.append(memory)
        enforce_working_capacity(self.memory_store, self.event_logger)
        consolidated = promote_working_memories(self.memory_store, self.event_logger, self.promotion_strategy)
        reorganizations = []
        for memory in consolidated:
            for record in check_local_reorganization(memory, self.memory_store, self.embedding_engine, self.llm_client):
                self.event_logger.log("local_reorganization", **record)
                reorganizations.append(record)
        core = promote_consolidated_memories(self.memory_store, self.event_logger)
        return {"activated": activated, "written": written, "consolidated": consolidated, "reorganizations": reorganizations, "core": core}

    def retrieve(self, limit: int = 10) -> List[MemoryEntry]:
        ordered = self.memory_store.get_core_memories() + self.memory_store.get_consolidated_memories() + self.memory_store.get_working_memories()
        return ordered[:limit]
