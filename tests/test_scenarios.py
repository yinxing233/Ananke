"""v0.2 (protocol v4) test suite — recall-classification pipeline.

Replaces the v3 cosine-activation tests. All signal paths are exercised with a
deterministic MockRelationClassifier + MockEmbedding + FakeExtractionLLM, so the
suite runs with zero API calls and no downloaded models.

Design decisions under test (protocol v4 §2.3/§2.4/§2.5, Fable5 drift fixes):
- Recipient semantics: EV/IA/triggers accrue on the *existing* memory e, not the new m.
- duplicate → never written (dedup); mergeable → NOT written (debt) + recipient trigger (PI ruling: writing = self-reinforcing signal pump).
- contradict → written (new assertion) + bidirectional conflict link + recipient conflict_trigger+1.
- EV only on cross-session duplicate (not system_guided).
- core promotion when local_reorganization_trigger≥2; conflict_trigger>0 is a BLOCKER (no core).
"""

import json
from pathlib import Path

import numpy as np

from ananke.config import Config
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import LayerEnum, MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.promotion import FrequencyPromotionStrategy, promotion_strategy_from_config
from ananke.relation import (
    MockRelationClassifier,
    REL_CONTRADICT,
    REL_DUPLICATE,
    REL_MERGEABLE,
    REL_RELATED,
    REL_UNRELATED,
)


class MockEmbedding:
    """Registry-backed embedding: known contents map to fixed vectors, unknown → zero (cos 0)."""

    def __init__(self, vectors):
        self.vectors = {k: np.array(v, dtype=float) for k, v in vectors.items()}

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([self.vectors.get(t, np.zeros(3)) for t in texts])

    def cosine_similarity(self, a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))


class FakeExtractionLLM:
    """Returns scripted extractions; relation classification is handled by MockRelationClassifier."""

    def __init__(self, extractions):
        self.extractions = list(extractions)

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        if "extract" in prompt.lower():
            return json.dumps(self.extractions.pop(0), ensure_ascii=False) if self.extractions else "[]"
        return "[]"


def make_pipeline(tmp_path, extractions=(), relation=REL_UNRELATED, vectors=None, strategy=None):
    return MemoryPipeline(
        MemoryStore(tmp_path / "data"),
        MockEmbedding(vectors or {}),
        FakeExtractionLLM(list(extractions)),
        EventLogger(tmp_path / "events.jsonl"),
        promotion_strategy=strategy,
        relation_classifier=MockRelationClassifier(relation),
    )


# ---------------------------------------------------------------------------
# Recall-classification signal mapping (protocol v4 §2.3)
# ---------------------------------------------------------------------------


def test_duplicate_cross_session_gives_ev(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").external_validation == 1
    # dedup: the duplicate is NOT written as a *new* memory — only the original e remains.
    same = [m for m in pipe.memory_store.get_working_memories() if m.content == "user likes badminton"]
    assert len(same) == 1 and same[0].id == "e"


def test_duplicate_same_session_no_ev(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s1")
    assert pipe.memory_store.find("e").external_validation == 0


def test_mergeable_increments_recipient_trigger_no_write(tmp_path):
    """协议 v4 §2.3 + PI 裁决：mergeable 只给受体加 trigger，不写新记忆。
    写入会制造近重复对→后续每轮高概率召回→虚增 IA/trigger=自增强信号泵，污染 persistence_score 与 |D|。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays badminton weekly": [0.8, 0.6, 0.0],  # cos ~0.8
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").local_reorganization_trigger == 1
    # 不写：working 层不应出现该新记忆（仅原 e 存在）
    assert not any(m.content == "user plays badminton weekly" for m in pipe.memory_store.get_working_memories())


def test_contradict_writes_new_assertion_and_links_bidirectionally(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays tennis instead"]], relation=REL_CONTRADICT,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays tennis instead": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    # 受体：矛盾 trigger 累积 + 进入阻断状态
    assert pipe.memory_store.find("e").conflict_trigger == 1
    # 新断言落盘（漂移2 修正：系统能更新世界状态）
    new_mems = [m for m in pipe.memory_store.get_working_memories() if m.content == "user plays tennis instead"]
    assert new_mems, "contradict 必须写入新断言"
    new_mem = new_mems[0]
    # 双向 conflict 链接
    assert new_mem.id in pipe.memory_store.find("e").conflict_links
    assert "e" in new_mem.conflict_links
    # 审计事件
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "conflict_link" for r in records)


def test_related_same_session_gives_ia(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_RELATED,
        vectors={
            "user likes sports": [1.0, 0.0, 0.0],
            "user likes badminton": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(id="e", content="user likes sports", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s1")
    assert pipe.memory_store.find("e").internal_activation == 1


def test_unrelated_written_no_signal(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes coffee"]], relation=REL_UNRELATED,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user likes coffee": [0.0, 1.0, 0.0],  # cos 0 < R_RECALL
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert any(m.content == "user likes coffee" for m in pipe.memory_store.get_working_memories())
    assert pipe.memory_store.find("e").external_validation == 0


def test_dedup_skips_write_and_logs(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s1")
    assert pipe.memory_store.find("e").external_validation == 0
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "memory_dedup_skip" for r in records)


# ---------------------------------------------------------------------------
# Promotion (working → consolidated), strategies preserved from v3 (v4 §4)
# ---------------------------------------------------------------------------


def test_working_promotion_persistence(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]] * 3, relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    for s in ("s2", "s3", "s4"):
        pipe.process("input", session_id=s)
    mem = pipe.memory_store.find("e")
    assert mem.layer is LayerEnum.CONSOLIDATED
    assert mem.external_validation == 3


def test_working_promotion_frequency(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]] * 3, relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
        strategy=FrequencyPromotionStrategy(),
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    for s in ("s2", "s3", "s4"):
        pipe.process("input", session_id=s)
    mem = pipe.memory_store.find("e")
    assert mem.layer is LayerEnum.CONSOLIDATED
    assert mem.total_activation == 3 and mem.internal_activation == 0


def test_persistence_and_frequency_control_diverge_on_mixed_signal(tmp_path):
    """Core experimental claim: persistence keeps a 1EV+2IA memory in working;
    frequency promotes it (total_activation=3)."""
    vectors = {
        "user likes badminton": [1.0, 0.0, 0.0],
        "user plays sports": [0.8, 0.6, 0.0],
        "user follows sports": [0.8, -0.6, 0.0],
    }
    extractions = [["user likes badminton"], ["user plays sports"], ["user follows sports"]]
    script = [REL_DUPLICATE, REL_RELATED, REL_RELATED]

    persist = make_pipeline(tmp_path / "p", extractions=list(extractions), vectors=vectors)
    persist.relation_classifier = MockRelationClassifier(script=list(script))
    persist.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    persist.process("i", session_id="s2")  # EV (cross)
    persist.process("i", session_id="s1")  # IA
    persist.process("i", session_id="s1")  # IA
    assert persist.memory_store.find("e").layer is LayerEnum.WORKING

    freq = make_pipeline(tmp_path / "f", extractions=list(extractions), vectors=vectors,
                         strategy=FrequencyPromotionStrategy())
    freq.relation_classifier = MockRelationClassifier(script=list(script))
    freq.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    freq.process("i", session_id="s2")
    freq.process("i", session_id="s1")
    freq.process("i", session_id="s1")
    assert freq.memory_store.find("e").layer is LayerEnum.CONSOLIDATED


# ---------------------------------------------------------------------------
# Core promotion (consolidated → core) via either trigger (v4 §2.3/§4)
# ---------------------------------------------------------------------------


def test_core_promotion_by_merge_trigger(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays badminton weekly": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1",
                    layer=LayerEnum.CONSOLIDATED, local_reorganization_trigger=1)
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").layer is LayerEnum.CORE


def test_core_promotion_blocked_by_conflict(tmp_path):
    """漂移1 修正：被矛盾触发的记忆即便 merge trigger 达标也不得升 CORE（晋升阻断器）。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays tennis instead"]], relation=REL_CONTRADICT,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays tennis instead": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(
        id="e", content="user likes badminton", session_id="s1",
        layer=LayerEnum.CONSOLIDATED,
        local_reorganization_trigger=2,  # 已达 merge 晋升条件
        conflict_trigger=1,              # 但被矛盾 → 阻断
    )
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").layer is LayerEnum.CONSOLIDATED  # 仍在中层，未升
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "core_promotion_blocked" for r in records)


def test_core_promotion_only_via_merge_trigger(tmp_path):
    """晋升唯一条件 = merge trigger≥2；conflict 不参与晋升。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays badminton weekly": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1",
                    layer=LayerEnum.CONSOLIDATED, local_reorganization_trigger=1)
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").layer is LayerEnum.CORE


# ---------------------------------------------------------------------------
# Session semantics + red lines
# ---------------------------------------------------------------------------


def test_ev_only_cross_session(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]] * 2, relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s1")  # same session → no EV
    pipe.process("input", session_id="s2")  # cross session → EV
    assert pipe.memory_store.find("e").external_validation == 1


def test_system_guided_input_cannot_be_external_validation(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1")
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2", system_guided=True)  # cross but guided → no EV
    assert pipe.memory_store.find("e").external_validation == 0


# ---------------------------------------------------------------------------
# Capacity eviction (strategy score, #13 fix preserved)
# ---------------------------------------------------------------------------


def test_capacity_evicts_lowest_persistence_score(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "WORKING_CAPACITY", 1)
    pipe = make_pipeline(
        tmp_path, extractions=[["charlie"]], relation=REL_UNRELATED,
        vectors={"alpha": [1, 0, 0], "bravo": [0, 1, 0], "charlie": [0, 0, 1]},
    )
    pipe.memory_store.add(MemoryEntry(id="low", content="alpha"))                       # score 0
    pipe.memory_store.add(MemoryEntry(id="high", content="bravo", external_validation=1))  # score 1.0
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("low") is None
    assert pipe.memory_store.find("high") is not None


def test_capacity_evicts_lowest_frequency_score(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "WORKING_CAPACITY", 1)
    pipe = make_pipeline(
        tmp_path, extractions=[["charlie"]], relation=REL_UNRELATED,
        vectors={"alpha": [1, 0, 0], "bravo": [0, 1, 0], "charlie": [0, 0, 1]},
        strategy=FrequencyPromotionStrategy(),
    )
    pipe.memory_store.add(MemoryEntry(id="freq_low", content="alpha", external_validation=1, total_activation=1))
    pipe.memory_store.add(MemoryEntry(id="freq_high", content="bravo", internal_activation=2, total_activation=2))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("freq_low") is None
    assert pipe.memory_store.find("freq_high") is not None


# ---------------------------------------------------------------------------
# Audit log + persistence
# ---------------------------------------------------------------------------


def test_reorganization_audit_log_has_required_fields(tmp_path):
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={
            "user likes badminton": [1.0, 0.0, 0.0],
            "user plays badminton weekly": [0.8, 0.6, 0.0],
        },
    )
    e = MemoryEntry(id="e", content="user likes badminton", session_id="s1",
                    layer=LayerEnum.CONSOLIDATED, local_reorganization_trigger=1)
    pipe.memory_store.add(e)
    pipe.process("input", session_id="s2")
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    reorg = next(r for r in records if r["event"] == "local_reorganization")
    assert {"timestamp", "event", "recipient_memory_id", "incoming_content", "action", "cosine_similarity"} <= reorg.keys()
    # mergeable 不写新记忆（PI 裁决），故本测试只要求重组+升层两类事件；memory_write 不再出现于此路径
    assert {"local_reorganization", "consolidated_to_core"} <= {r["event"] for r in records}


def test_store_survives_restart_and_retrieval_prioritizes_core(tmp_path):
    store = MemoryStore(tmp_path / "data")
    store.add(MemoryEntry(id="working", content="alpha"))
    store.add(MemoryEntry(id="core", content="bravo", layer=LayerEnum.CORE))
    reloaded = MemoryStore(tmp_path / "data")
    pipe = MemoryPipeline(reloaded, MockEmbedding({}), FakeExtractionLLM([]), EventLogger(tmp_path / "events.jsonl"))
    assert [m.id for m in pipe.retrieve()] == ["core", "working"]


def test_config_selects_frequency_control(monkeypatch):
    monkeypatch.setattr(Config, "WORKING_PROMOTION_STRATEGY", "frequency")
    assert isinstance(promotion_strategy_from_config(), FrequencyPromotionStrategy)


# ---------------------------------------------------------------------------
# 协议 v4 一致性守护（§2.3 信号映射表 + §2.5 CORE 阻断器）
#
# 这些测试是协议条款的**机器可执行守护**：名字带条款号，协议改则测试改，二者不同步即飘红。
# 存在理由：P0-A 暴露的流程病——协议说"mergeable 不写"、代码却写、测试还断言写——
# 根因是协议条款无机器守护，靠下一轮人肉三方对照太贵。此处用命名测试把条款钉死。
# 与上方行为测试有重叠是有意的：守护层独立于行为测试，必须各自绿。
# ---------------------------------------------------------------------------


def test_protocol_2_3_duplicate_cross_session_ev_no_write(tmp_path):
    """§2.3 duplicate|跨session → EV+1，不写入。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").external_validation == 1
    assert len([m for m in pipe.memory_store.get_working_memories() if m.content == "user likes badminton"]) == 1


def test_protocol_2_3_duplicate_same_session_no_signal(tmp_path):
    """§2.3 duplicate|同session → 去重，不计任何信号。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_DUPLICATE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    pipe.process("input", session_id="s1")
    e = pipe.memory_store.find("e")
    assert e.external_validation == 0 and e.internal_activation == 0


def test_protocol_2_3_contradict_writes_new_assertion_and_bidirectional_link(tmp_path):
    """§2.3 contradict → 写新断言 + 双向 conflict 链接 + 受体 conflict_trigger+1。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays tennis instead"]], relation=REL_CONTRADICT,
        vectors={"user likes badminton": [1.0, 0.0, 0.0], "user plays tennis instead": [0.8, 0.6, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").conflict_trigger == 1
    new_mems = [m for m in pipe.memory_store.get_working_memories() if m.content == "user plays tennis instead"]
    assert new_mems, "contradict 必须写入新断言"
    assert new_mems[0].id in pipe.memory_store.find("e").conflict_links
    assert "e" in new_mems[0].conflict_links


def test_protocol_2_3_mergeable_no_write_trigger_only(tmp_path):
    """§2.3 mergeable → local_reorganization_trigger+1，**不写**新记忆（PI 裁决：写入=自增强信号泵）。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0], "user plays badminton weekly": [0.8, 0.6, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").local_reorganization_trigger == 1
    assert not any(m.content == "user plays badminton weekly" for m in pipe.memory_store.get_working_memories())


def test_protocol_2_3_related_ia_and_write(tmp_path):
    """§2.3 related → IA+1，写入新记忆。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes badminton"]], relation=REL_RELATED,
        vectors={"user likes sports": [1.0, 0.0, 0.0], "user likes badminton": [0.8, 0.6, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes sports", session_id="s1"))
    pipe.process("input", session_id="s1")
    assert pipe.memory_store.find("e").internal_activation == 1
    assert any(m.content == "user likes badminton" for m in pipe.memory_store.get_working_memories())


def test_protocol_2_3_unrelated_write_no_signal(tmp_path):
    """§2.3 unrelated → 正常写入，受体无信号。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user likes coffee"]], relation=REL_UNRELATED,
        vectors={"user likes badminton": [1.0, 0.0, 0.0], "user likes coffee": [0.0, 1.0, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(id="e", content="user likes badminton", session_id="s1"))
    pipe.process("input", session_id="s2")
    e = pipe.memory_store.find("e")
    assert e.external_validation == 0 and e.internal_activation == 0
    assert any(m.content == "user likes coffee" for m in pipe.memory_store.get_working_memories())


def test_protocol_2_5_conflict_blocks_core_promotion(tmp_path):
    """§2.5 conflict_trigger>0 = CORE 晋升阻断器（即便 merge trigger 达标也不升）。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays tennis instead"]], relation=REL_CONTRADICT,
        vectors={"user likes badminton": [1.0, 0.0, 0.0], "user plays tennis instead": [0.8, 0.6, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(
        id="e", content="user likes badminton", session_id="s1",
        layer=LayerEnum.CONSOLIDATED, local_reorganization_trigger=2, conflict_trigger=1,
    ))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").layer is LayerEnum.CONSOLIDATED  # 冻结中层，未升


def test_protocol_2_5_core_promotion_only_via_merge_trigger(tmp_path):
    """§2.5 晋升唯一条件 = local_reorganization_trigger ≥ LOCAL_REORG_THRESHOLD；conflict 不参与晋升。"""
    pipe = make_pipeline(
        tmp_path, extractions=[["user plays badminton weekly"]], relation=REL_MERGEABLE,
        vectors={"user likes badminton": [1.0, 0.0, 0.0], "user plays badminton weekly": [0.8, 0.6, 0.0]},
    )
    pipe.memory_store.add(MemoryEntry(
        id="e", content="user likes badminton", session_id="s1",
        layer=LayerEnum.CONSOLIDATED, local_reorganization_trigger=1,  # process 后变 2
    ))
    pipe.process("input", session_id="s2")
    assert pipe.memory_store.find("e").layer is LayerEnum.CORE


def test_ratelimiter_zero_rpm_nonblocking():
    """rpm<=0 不节流：acquire 立即返回，不 sleep（如 deepseek 评估端默认）。"""
    from ananke.llm_client import _RateLimiter
    import time
    rl = _RateLimiter(0)
    t0 = time.time()
    for _ in range(5):
        rl.acquire()
    assert time.time() - t0 < 0.5


def test_ratelimiter_positive_rpm_burst_capacity():
    """rpm>0：capacity=rpm，前 rpm 次 acquire 立即可用（突发额度），rate 属性正确。"""
    from ananke.llm_client import _RateLimiter
    import time
    rl = _RateLimiter(30)
    assert rl.rate == 0.5          # 30/60
    assert rl.capacity == 30
    t0 = time.time()
    for _ in range(30):            # 恰好 capacity，全应立即可用
        rl.acquire()
    assert time.time() - t0 < 0.5
