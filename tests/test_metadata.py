"""A4/A5+B2 来源元数据贯通与惰性守护测试。"""

import json

import numpy as np

from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline
from ananke.relation import MockRelationClassifier, REL_UNRELATED
from tools.run_corpus import load_corpus


class _Embedding:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([[1.0, 0.0] for _ in texts])

    def cosine_similarity(self, left, right):
        return 1.0


class _ExtractionLLM:
    cache = None

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        return '["new fact"]'


def _make_pipeline(tmp_path):
    return MemoryPipeline(
        MemoryStore(tmp_path / "data"),
        _Embedding(),
        _ExtractionLLM(),
        EventLogger(tmp_path / "events.jsonl"),
        relation_classifier=MockRelationClassifier(REL_UNRELATED),
    )


def _records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_a4_jsonl_loader_preserves_session_dia_and_speaker(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "session_id": "conv-41_s3",
                "input": "A fact",
                "dia_id": "D17",
                "speaker": "Caroline",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    turn = load_corpus(corpus)[0]

    assert turn.text == "A fact"
    assert turn.session_id == "conv-41_s3"
    assert turn.dia_id == "D17"
    assert turn.speaker == "Caroline"


def test_a4_source_metadata_persists_and_input_metadata_reaches_all_events(tmp_path):
    pipeline = _make_pipeline(tmp_path)

    result = pipeline.process(
        "input",
        session_id="conv-41_s3",
        dia_id="D17",
        speaker="Caroline",
    )

    memory = result["written"][0]
    assert memory.source_session_id == "conv-41_s3"
    assert memory.source_dia_id == "D17"
    assert memory.source_speaker == "Caroline"

    reloaded = MemoryStore(tmp_path / "data").find(memory.id)
    assert reloaded.source_session_id == "conv-41_s3"
    assert reloaded.source_dia_id == "D17"
    assert reloaded.source_speaker == "Caroline"

    records = _records(tmp_path / "events.jsonl")
    assert records
    for record in records:
        assert record["input_session_id"] == "conv-41_s3"
        assert record["input_dia_id"] == "D17"
        assert record["input_speaker"] == "Caroline"
        assert record["system_guided"] is False


def test_metadata_dia_and_speaker_are_dynamically_inert(tmp_path):
    left = _make_pipeline(tmp_path / "left")
    right = _make_pipeline(tmp_path / "right")

    left_result = left.process(
        "input",
        session_id="same-session",
        dia_id="left-dia",
        speaker="left-speaker",
    )
    right_result = right.process(
        "input",
        session_id="same-session",
        dia_id="right-dia",
        speaker="right-speaker",
    )

    left_memory = left_result["written"][0]
    right_memory = right_result["written"][0]
    assert left_memory.content == right_memory.content
    assert left_memory.layer == right_memory.layer
    assert left_memory.persistence_score == right_memory.persistence_score
    assert left_memory.frequency_score == right_memory.frequency_score
    assert left_memory.internal_activation == right_memory.internal_activation
    assert left_memory.external_validation == right_memory.external_validation

    left_events = [record["event"] for record in _records(tmp_path / "left" / "events.jsonl")]
    right_events = [record["event"] for record in _records(tmp_path / "right" / "events.jsonl")]
    assert left_events == right_events
