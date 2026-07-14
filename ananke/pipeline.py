from uuid import uuid4
from typing import Dict, List

from ananke.activation import detect_activations
from ananke.config import Config
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
        # 写入前去重（v3 控制变量 DEDUP_SIMILARITY_THRESHOLD）：候选记忆与既有记忆高度相似则跳过写入，
        # 该输入的信号已由 detect_activations 注册到既有记忆上。消除真实 LLM 提取的碎片化混杂。
        existing_cache = self.memory_store.get_working_memories() + self.memory_store.get_consolidated_memories()
        existing_vecs = self.embedding_engine.encode([m.content for m in existing_cache]).tolist() if existing_cache else []
        for content in extract_memories(user_input, self.llm_client):
            candidate_vec = self.embedding_engine.encode(content)[0]
            max_sim, matched = -1.0, None
            for m, vec in zip(existing_cache, existing_vecs):
                sim = self.embedding_engine.cosine_similarity(candidate_vec, vec)
                if sim > max_sim:
                    max_sim, matched = sim, m
            if existing_cache and max_sim >= Config.DEDUP_SIMILARITY_THRESHOLD:
                self.event_logger.log("memory_dedup_skip", content_summary=content[:120],
                                      max_similarity=round(max_sim, 3), matched_memory_id=matched.id)
                continue
            memory = MemoryEntry(id=str(uuid4()), content=content)
            self.memory_store.add(memory)
            self.event_logger.log("memory_write", memory_id=memory.id, content_summary=content[:120], layer=memory.layer.value)
            written.append(memory)
            existing_cache.append(memory)
            existing_vecs.append(candidate_vec)
        enforce_working_capacity(self.memory_store, self.event_logger, self.promotion_strategy)
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
