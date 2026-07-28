from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from ananke.config import Config
from ananke.extraction import extract_memories
from ananke.migration import (
    enforce_working_capacity,
    promote_consolidated_memories,
    promote_working_memories,
)
from ananke.models import LayerEnum, MemoryEntry
from ananke.reorganization import apply_relation_event
from ananke.relation import (
    REL_CONTRADICT,
    REL_DUPLICATE,
    REL_MERGEABLE,
    REL_RELATED,
    RelationClassifier,
    LLMRelationClassifier,
)


class MemoryPipeline:
    """Orchestrates the one-way three-layer memory lifecycle (protocol v4).

    v4 召回-分类两段式（取代 v3 余弦阈值判定）：
      新提取记忆 m → 余弦召回(cos≥R_RECALL) 候选 e → 关系分类器(m,e) → 信号映射(§2.3)。

    激活(EV/IA)与重组触发(mergeable/contradict)均由「新记忆 m 与既有记忆 e 的关系」
    驱动，而非 v3 的「输入文本 vs 记忆 余弦」。EV 仅跨 session 再断言时计（§3）。
    """

    def __init__(
        self,
        memory_store,
        embedding_engine,
        llm_client,
        event_logger,
        promotion_strategy=None,
        relation_classifier: Optional[RelationClassifier] = None,
    ):
        self.memory_store = memory_store
        self.embedding_engine = embedding_engine
        self.llm_client = llm_client
        self.event_logger = event_logger
        self.promotion_strategy = promotion_strategy
        # 关系分类器：默认 LLM 五选一（方案乙）；测试/开发用 MockRelationClassifier。
        self.relation_classifier = relation_classifier or LLMRelationClassifier(llm_client)

    def process(self, user_input: str, session_id: Optional[str] = None, *, system_guided: bool = False) -> Dict[str, List]:
        written: List[MemoryEntry] = []
        # 召回候选池：工作层 + 巩固层（慢层不参与召回，符合单向阀）。
        existing_cache = self.memory_store.get_working_memories() + self.memory_store.get_consolidated_memories()
        existing_vecs = (
            [self.embedding_engine.encode(m.content)[0] for m in existing_cache] if existing_cache else []
        )

        for content in extract_memories(user_input, self.llm_client):
            candidate, best_sim = self._recall(content, existing_cache, existing_vecs)
            if candidate is None:
                # 无候选（余弦召回空集）→ 视为 unrelated，直接写入快层。
                memory = self._write(content, session_id)
                written.append(memory)
                existing_cache.append(memory)
                existing_vecs.append(self.embedding_engine.encode(content)[0])
                continue

            relation = self.relation_classifier.classify(content, candidate.content)
            write_new, link_recipient = self._handle_relation(
                content, candidate, relation, best_sim, session_id, system_guided
            )
            if write_new:
                memory = self._write(content, session_id)
                written.append(memory)
                existing_cache.append(memory)
                existing_vecs.append(self.embedding_engine.encode(content)[0])
                if link_recipient is not None:
                    self._link_conflict(memory, link_recipient)

        enforce_working_capacity(self.memory_store, self.event_logger, self.promotion_strategy)
        consolidated = promote_working_memories(self.memory_store, self.event_logger, self.promotion_strategy)
        core = promote_consolidated_memories(self.memory_store, self.event_logger)
        return {"written": written, "consolidated": consolidated, "core": core}

    # ---- 召回-分类内部阶段 ----

    def _recall(self, content: str, existing_cache: List[MemoryEntry], existing_vecs: list):
        """返回 (最佳候选 e, 其余弦相似度)；若无 cos≥R_RECALL 的候选则返回 (None, -1.0)。"""
        if not existing_cache:
            return None, -1.0
        cand_vec = self.embedding_engine.encode(content)[0]
        best, best_sim = None, -1.0
        for memory, vec in zip(existing_cache, existing_vecs):
            sim = self.embedding_engine.cosine_similarity(cand_vec, vec)
            if sim >= Config.R_RECALL:
                # 确定性 tie-break（协议 v4 §8 确定性审计）：余弦平票时按 (content, id) 字典序
                # 取较小者。content 跨运行一致（提取缓存命中）→ 重放等价；id(uuid) 仅作同 content
                # 兜底（业务无差别）。避免列表顺序依赖导致的非确定性渗入 D。
                if sim > best_sim or (sim == best_sim and (best is None or (memory.content, memory.id) < (best.content, best.id))):
                    best, best_sim = memory, sim
        return best, best_sim

    def _handle_relation(
        self,
        content: str,
        recipient: MemoryEntry,
        relation: str,
        similarity: float,
        session_id: Optional[str],
        system_guided: bool,
    ) -> tuple[bool, Optional[MemoryEntry]]:
        """按 v4 §2.3 信号映射处理 (m, e) 关系。

        采用**受体语义（recipient semantics）**：信号（EV/IA/触发）一律计到既有记忆 e 上
        ——e 才是「被持续检验的结构节点」。返回 (是否写入新记忆 m, 需建矛盾链接的受体记忆)。

        漂移2 修正（Fable5）：contradict 命中时，新断言 m 必须落盘（写入快层）并与受体 e
        建立**双向 conflict 链接**——系统才能更新世界状态、验证阶段的命中率测量才不会在
        含改口的事实上系统性失真。mergeable 仍不写新记忆（信息多为冗余，留债）。
        """
        cross_session = (
            session_id is not None
            and recipient.session_id is not None
            and session_id != recipient.session_id
        )

        if relation == REL_DUPLICATE:
            # 去重：不写入 m。跨 session 再断言(且非系统引导)→ e 获 EV；同 session 仅丢弃。
            self.event_logger.log(
                "memory_dedup_skip",
                content_summary=content[:120],
                max_similarity=round(similarity, 3),
                matched_memory_id=recipient.id,
                relation=relation,
                cross_session=cross_session,
            )
            if cross_session and not system_guided:
                recipient.external_validation += 1
                recipient.total_activation += 1
                recipient.last_activated_at = datetime.now()
                self.memory_store.update(recipient)
                self.event_logger.log(
                    "external_validation",
                    memory_id=recipient.id,
                    input_summary=content[:120],
                    cosine_similarity=round(similarity, 3),
                    external_validation=recipient.external_validation,
                    cross_session=cross_session,
                )
            return False, None

        if relation == REL_CONTRADICT:
            apply_relation_event(self.memory_store, self.event_logger, recipient, REL_CONTRADICT, similarity, content)
            # 写入新断言 m，并与受体 e 双向链接（漂移2 修正）。
            return True, recipient

        if relation == REL_MERGEABLE:
            apply_relation_event(self.memory_store, self.event_logger, recipient, REL_MERGEABLE, similarity, content)
            # 不写新记忆（协议 v4 §2.3：mergeable 信息多为冗余，留债）。
            # PI 裁决：写入即制造近重复对，该近重复在后续每轮召回高概率命中，虚增 IA 与
            # trigger——双重表示不是静态冗余，是自增强的信号泵，污染 persistence_score 与 |D|。
            # 「不写」把债留在原地（合并执行属 v0.3+），「写」是开新污染源。故 return False。
            return False, None

        if relation == REL_RELATED:
            recipient.internal_activation += 1
            recipient.total_activation += 1
            recipient.last_activated_at = datetime.now()
            self.memory_store.update(recipient)
            self.event_logger.log(
                "internal_activation",
                memory_id=recipient.id,
                input_summary=content[:120],
                internal_activation=recipient.internal_activation,
                cosine_similarity=round(similarity, 3),
            )
            return True, None

        # REL_UNRELATED（理论上 _recall 已兜空，这里兜底）：写入 m。
        return True, None

    def _link_conflict(self, new_memory: MemoryEntry, recipient: MemoryEntry) -> None:
        """建立双向矛盾链接（漂移2 修正）：新断言与受体互为矛盾。"""
        new_memory.conflict_links.append(recipient.id)
        recipient.conflict_links.append(new_memory.id)
        self.memory_store.update(recipient)
        self.memory_store.update(new_memory)
        self.event_logger.log(
            "conflict_link",
            new_memory_id=new_memory.id,
            recipient_memory_id=recipient.id,
            new_content=new_memory.content[:120],
            recipient_content=recipient.content[:120],
        )

    def _write(self, content: str, session_id: Optional[str]) -> MemoryEntry:
        memory = MemoryEntry(id=str(uuid4()), content=content, session_id=session_id)
        self.memory_store.add(memory)
        self.event_logger.log(
            "memory_write", memory_id=memory.id, content_summary=content[:120], layer=memory.layer.value
        )
        return memory

    def retrieve(self, limit: int = 10) -> List[MemoryEntry]:
        ordered = (
            self.memory_store.get_core_memories()
            + self.memory_store.get_consolidated_memories()
            + self.memory_store.get_working_memories()
        )
        return ordered[:limit]
