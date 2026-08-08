"""B3 CORE 召回、同分决胜与四关系处置守护测试。"""

import json

import numpy as np

from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import LayerEnum, MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.relation import (
    MockRelationClassifier,
    REL_CONTRADICT,
    REL_DUPLICATE,
    REL_MERGEABLE,
    REL_RELATED,
)


class _FlatEmbedding:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([[1.0, 0.0] for _ in texts])

    def cosine_similarity(self, left, right):
        return 1.0


class _ExtractionLLM:
    cache = None

    def __init__(self, content):
        self.content = content

    def call_llm(self, prompt, system_prompt=None, temperature=None, **kwargs):
        return json.dumps([self.content])


def _pipeline(tmp_path, incoming, relation):
    store = MemoryStore(tmp_path / "data")
    store.add(
        MemoryEntry(
            id="core",
            content="long-term fact",
            layer=LayerEnum.CORE,
            source_session_id="s1",
        )
    )
    return MemoryPipeline(
        store,
        _FlatEmbedding(),
        _ExtractionLLM(incoming),
        EventLogger(tmp_path / "events.jsonl"),
        relation_classifier=MockRelationClassifier(relation),
    )


def _records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_b3_core_wins_cross_layer_similarity_tie(tmp_path):
    store = MemoryStore(tmp_path / "data")
    working = MemoryEntry(
        id="working",
        content="aaa working fact",
        layer=LayerEnum.WORKING,
    )
    core = MemoryEntry(
        id="core",
        content="zzz core fact",
        layer=LayerEnum.CORE,
    )
    store.add(working)
    store.add(core)
    pipeline = MemoryPipeline(
        store,
        _FlatEmbedding(),
        _ExtractionLLM("incoming"),
        EventLogger(tmp_path / "events.jsonl"),
        relation_classifier=MockRelationClassifier(REL_DUPLICATE),
    )

    candidates = (
        store.get_working_memories()
        + store.get_consolidated_memories()
        + store.get_core_memories()
    )
    vectors = [_FlatEmbedding().encode(memory.content)[0] for memory in candidates]
    recalled, similarity = pipeline._recall("incoming", candidates, vectors)

    assert similarity == 1.0
    assert recalled.id == "core"


def test_b3_duplicate_core_deduplicates_and_counts_ev(tmp_path):
    pipeline = _pipeline(tmp_path, "long-term fact", REL_DUPLICATE)

    result = pipeline.process("input", session_id="s2")

    core = pipeline.memory_store.find("core")
    assert core.layer is LayerEnum.CORE
    assert core.external_validation == 1
    assert core.ev_contributing_session_ids == ["s2"]
    assert result["written"] == []
    assert pipeline.memory_store.get_working_memories() == []


def test_b3_related_core_records_ia_and_writes_working(tmp_path):
    pipeline = _pipeline(tmp_path, "new related fact", REL_RELATED)

    result = pipeline.process("input", session_id="s2")

    core = pipeline.memory_store.find("core")
    assert core.layer is LayerEnum.CORE
    assert core.internal_activation == 1
    assert core.total_activation == 1
    assert [memory.content for memory in result["written"]] == ["new related fact"]
    assert result["written"][0].layer is LayerEnum.WORKING


def test_b3_mergeable_core_keeps_full_increment_in_audit(tmp_path):
    incoming = ("structural increment " * 20).strip()
    pipeline = _pipeline(tmp_path, incoming, REL_MERGEABLE)

    result = pipeline.process(
        "input",
        session_id="s2",
        dia_id="D9",
        speaker="Caroline",
    )

    core = pipeline.memory_store.find("core")
    assert core.layer is LayerEnum.CORE
    assert core.local_reorganization_trigger == 1
    assert result["written"] == []
    event = next(
        record
        for record in _records(tmp_path / "events.jsonl")
        if record["event"] == "local_reorganization"
    )
    assert event["incoming_content"] == incoming
    assert event["input_dia_id"] == "D9"
    assert event["input_speaker"] == "Caroline"


def test_b3_contradict_core_marks_and_links_without_demotion(tmp_path):
    pipeline = _pipeline(tmp_path, "replacement fact", REL_CONTRADICT)

    result = pipeline.process("input", session_id="s2")

    core = pipeline.memory_store.find("core")
    new_memory = result["written"][0]
    assert core.layer is LayerEnum.CORE
    assert core.conflict_trigger == 1
    assert new_memory.layer is LayerEnum.WORKING
    assert new_memory.id in core.conflict_links
    assert core.id in new_memory.conflict_links


def test_b3_core_counters_are_descriptive_not_decision_inputs(tmp_path):
    low = _pipeline(tmp_path / "low", "new related fact", REL_RELATED)
    high = _pipeline(tmp_path / "high", "new related fact", REL_RELATED)
    high_core = high.memory_store.find("core")
    high_core.external_validation = 99
    high_core.internal_activation = 99
    high_core.local_reorganization_trigger = 99
    high_core.conflict_trigger = 99
    high.memory_store.update(high_core)

    low_result = low.process("input", session_id="s2")
    high_result = high.process("input", session_id="s2")

    assert [memory.layer for memory in low_result["written"]] == [
        memory.layer for memory in high_result["written"]
    ]
    assert low.memory_store.find("core").layer is LayerEnum.CORE
    assert high.memory_store.find("core").layer is LayerEnum.CORE
    assert [record["event"] for record in _records(tmp_path / "low" / "events.jsonl")] == [
        record["event"] for record in _records(tmp_path / "high" / "events.jsonl")
    ]


def test_b3_normalized_core_duplicate_rate_is_report_only(tmp_path):
    from ananke.migration import core_exact_duplicate_summary

    store = MemoryStore(tmp_path / "data")
    store.add(
        MemoryEntry(id="a", content="User likes cats!", layer=LayerEnum.CORE)
    )
    store.add(
        MemoryEntry(id="b", content="user likes cats", layer=LayerEnum.CORE)
    )
    store.add(
        MemoryEntry(id="c", content="User knows Python", layer=LayerEnum.CORE)
    )

    summary = core_exact_duplicate_summary(store)

    assert summary == {
        "core_count": 3,
        "unique_normalized_count": 2,
        "duplicate_entry_count": 1,
        "duplicate_group_count": 1,
        "normalized_exact_duplicate_rate": 1 / 3,
    }
    assert len(store.get_core_memories()) == 3
