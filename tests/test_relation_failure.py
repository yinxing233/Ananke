"""A2+B7 关系分类解析硬失败守护测试。"""

import json

import numpy as np
import pytest

from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.relation import RelationParseError


class _Embedding:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([[1.0, 0.0] for _ in texts])

    def cosine_similarity(self, left, right):
        return 1.0


class _CacheSpy:
    def __init__(self):
        self.values = {}
        self.gets = []
        self.puts = []

    def get(self, category, key):
        self.gets.append((category, key))
        return self.values.get((category, key))

    def put(self, category, key, value):
        self.puts.append((category, key, value))
        self.values.setdefault((category, key), value)


class _ScriptedLLM:
    def __init__(self, relation_replies, extracted_content="same fact extended"):
        self.relation_replies = list(relation_replies)
        self.extracted_content = extracted_content
        self.cache = _CacheSpy()

    def call_llm(
        self,
        prompt,
        system_prompt=None,
        temperature=None,
        *,
        max_tokens=None,
        operation="unspecified",
    ):
        if "Extract short, atomic facts" in prompt:
            return json.dumps([self.extracted_content])
        assert max_tokens == 6
        assert operation == "relation"
        reply = self.relation_replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _pipeline(tmp_path, replies, extracted_content="same fact extended"):
    llm = _ScriptedLLM(replies, extracted_content=extracted_content)
    store = MemoryStore(tmp_path / "data")
    store.add(MemoryEntry(id="existing", content="same fact", session_id="s1"))
    pipeline = MemoryPipeline(
        store,
        _Embedding(),
        llm,
        EventLogger(tmp_path / "events.jsonl"),
    )
    return pipeline, llm


def _records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_b7_unknown_tokens_retry_then_abort_without_state_pollution(tmp_path):
    pipeline, llm = _pipeline(tmp_path, ["maybe", "unknown", "???"])

    with pytest.raises(ValueError, match="unknown relation label"):
        pipeline.process("input", session_id="s2")

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 0
    assert memory.total_activation == 0
    assert [item.id for item in pipeline.memory_store.get_working_memories()] == [
        "existing"
    ]
    assert not any(category == "pairs" for category, _, _ in llm.cache.puts)

    records = _records(tmp_path / "events.jsonl")
    assert [record["event"] for record in records] == [
        "classification_unparsed",
        "classification_unparsed",
        "classification_unparsed",
        "turn_failed",
    ]
    assert [record["attempt"] for record in records[:3]] == [1, 2, 3]
    assert [record["raw_response"] for record in records[:3]] == [
        "maybe",
        "unknown",
        "???",
    ]


def test_b7_only_successful_retry_is_cached(tmp_path):
    pipeline, llm = _pipeline(tmp_path, ["maybe", "", "duplicate"])

    pipeline.process("input", session_id="s2")

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 1
    pair_puts = [
        value
        for category, _, value in llm.cache.puts
        if category == "pairs"
    ]
    assert pair_puts == ["duplicate"]

    records = _records(tmp_path / "events.jsonl")
    assert [record["event"] for record in records[:2]] == [
        "classification_unparsed",
        "classification_unparsed",
    ]
    assert "turn_failed" not in {record["event"] for record in records}


def test_b7_invalid_cached_label_fails_closed(tmp_path):
    pipeline, llm = _pipeline(tmp_path, ["duplicate"])
    llm.cache.values[("pairs", "same fact extended||same fact")] = "bogus"

    with pytest.raises(RelationParseError, match="invalid cached relation label"):
        pipeline.process("input", session_id="s2")

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 0
    assert [item.id for item in pipeline.memory_store.get_working_memories()] == [
        "existing"
    ]
    records = _records(tmp_path / "events.jsonl")
    assert [record["event"] for record in records] == [
        "classification_unparsed",
        "turn_failed",
    ]
    assert records[0]["source"] == "cache"


def test_b7_transport_value_error_is_not_mislabeled_as_parse_failure(tmp_path):
    pipeline, llm = _pipeline(tmp_path, [ValueError("transport configuration")])

    with pytest.raises(ValueError, match="transport configuration"):
        pipeline.process("input", session_id="s2")

    records = _records(tmp_path / "events.jsonl")
    assert [record["event"] for record in records] == ["turn_failed"]


def test_exact_duplicate_short_circuits_relation_llm_and_is_audited(tmp_path):
    pipeline, llm = _pipeline(tmp_path, [], extracted_content="Same Fact!")

    pipeline.process("input", session_id="s2")

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 1
    assert not any(category == "pairs" for category, _ in llm.cache.gets)
    assert not any(category == "pairs" for category, _, _ in llm.cache.puts)
    records = _records(tmp_path / "events.jsonl")
    rule_events = [r for r in records if r["event"] == "rule_based_duplicate"]
    assert len(rule_events) == 1
    dedup = next(r for r in records if r["event"] == "memory_dedup_skip")
    assert dedup["classification_source"] == "normalized_exact_rule"
