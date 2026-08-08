"""B1 distinct-session EV 与 Frequency 激活语义守护测试。"""

import json

import numpy as np

from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.relation import MockRelationClassifier, REL_DUPLICATE


class _Embedding:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([[1.0, 0.0] for _ in texts])

    def cosine_similarity(self, left, right):
        return 1.0


class _ExtractionLLM:
    cache = None

    def __init__(self, count):
        self.count = count

    def call_llm(self, prompt, system_prompt=None, temperature=None, **kwargs):
        if self.count <= 0:
            return "[]"
        self.count -= 1
        return '["same fact"]'


def _pipeline(tmp_path, turns):
    store = MemoryStore(tmp_path / "data")
    store.add(
        MemoryEntry(
            id="existing",
            content="same fact",
            source_session_id="s1",
        )
    )
    return MemoryPipeline(
        store,
        _Embedding(),
        _ExtractionLLM(turns),
        EventLogger(tmp_path / "events.jsonl"),
        relation_classifier=MockRelationClassifier(REL_DUPLICATE),
    )


def _records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_b1_each_distinct_session_contributes_ev_once(tmp_path):
    pipeline = _pipeline(tmp_path, 3)

    pipeline.process("input", session_id="s2")
    pipeline.process("input", session_id="s2")
    pipeline.process("input", session_id="s3")

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 2
    assert memory.total_activation == 3
    assert memory.ev_contributing_session_ids == ["s2", "s3"]

    reloaded = MemoryStore(tmp_path / "data").find("existing")
    assert reloaded.ev_contributing_session_ids == ["s2", "s3"]

    records = _records(tmp_path / "events.jsonl")
    dedup = [record for record in records if record["event"] == "memory_dedup_skip"]
    assert [record["ev_contributed"] for record in dedup] == [True, False, True]
    assert [record["ev_session_already_contributed"] for record in dedup] == [
        False,
        True,
        False,
    ]
    assert len(
        [record for record in records if record["event"] == "external_validation"]
    ) == 2


def test_b1_guided_input_does_not_consume_session_eligibility(tmp_path):
    pipeline = _pipeline(tmp_path, 2)

    pipeline.process("input", session_id="s2", system_guided=True)
    pipeline.process("input", session_id="s2", system_guided=False)

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 1
    assert memory.total_activation == 1
    assert memory.ev_contributing_session_ids == ["s2"]


def test_b1_creation_or_missing_session_has_no_duplicate_signal(tmp_path):
    pipeline = _pipeline(tmp_path, 2)

    pipeline.process("input", session_id="s1")
    pipeline.process("input", session_id=None)

    memory = pipeline.memory_store.find("existing")
    assert memory.external_validation == 0
    assert memory.total_activation == 0
    assert memory.ev_contributing_session_ids == []
