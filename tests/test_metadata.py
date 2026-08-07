"""A4/A5+B2 来源元数据贯通与惰性守护测试。"""

import json

import numpy as np

from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline
from ananke.relation import MockRelationClassifier, REL_UNRELATED
from tools.locomo_loader import convert_sample
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

    def __init__(self):
        self.prompts = []

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        self.prompts.append(prompt)
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


def test_a4_jsonl_loader_preserves_session_dia_speaker_and_datetime(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "session_id": "conv-41_s3",
                "input": "A fact",
                "dia_id": "D17",
                "speaker": "Caroline",
                "session_datetime": "1:56 pm on 8 May, 2023",
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
    assert turn.session_datetime == "1:56 pm on 8 May, 2023"


def test_locomo_adapter_copies_session_datetime_to_every_turn():
    sample = {
        "sample_id": "conv-test",
        "conversation": {
            "speaker_a": "Caroline",
            "speaker_b": "Melanie",
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [
                {
                    "speaker": "Caroline",
                    "dia_id": "D1:1",
                    "text": "I went to a support group yesterday.",
                },
                {
                    "speaker": "Melanie",
                    "dia_id": "D1:2",
                    "text": "That sounds powerful.",
                },
            ],
        },
        "qa": [],
    }

    corpus, probes, _ = convert_sample(sample)

    assert probes == []
    assert [turn["speaker"] for turn in corpus] == ["Caroline", "Melanie"]
    assert {turn["session_datetime"] for turn in corpus} == {
        "1:56 pm on 8 May, 2023"
    }


def test_locomo_adapter_rejects_missing_session_datetime():
    sample = {
        "sample_id": "conv-test",
        "conversation": {
            "speaker_a": "Caroline",
            "speaker_b": "Melanie",
            "session_1": [
                {"speaker": "Caroline", "dia_id": "D1:1", "text": "I went yesterday."}
            ],
        },
        "qa": [],
    }

    try:
        convert_sample(sample)
    except ValueError as error:
        assert "缺少 session_1_date_time" in str(error)
    else:
        raise AssertionError("LoCoMo session 缺日期时应 fail closed")


def test_a4_source_metadata_persists_and_input_metadata_reaches_all_events(tmp_path):
    pipeline = _make_pipeline(tmp_path)

    result = pipeline.process(
        "input",
        session_id="conv-41_s3",
        dia_id="D17",
        speaker="Caroline",
        session_datetime="1:56 pm on 8 May, 2023",
    )

    memory = result["written"][0]
    assert memory.source_session_id == "conv-41_s3"
    assert memory.source_dia_id == "D17"
    assert memory.source_speaker == "Caroline"
    assert memory.source_session_datetime == "1:56 pm on 8 May, 2023"

    reloaded = MemoryStore(tmp_path / "data").find(memory.id)
    assert reloaded.source_session_id == "conv-41_s3"
    assert reloaded.source_dia_id == "D17"
    assert reloaded.source_speaker == "Caroline"
    assert reloaded.source_session_datetime == "1:56 pm on 8 May, 2023"

    records = _records(tmp_path / "events.jsonl")
    assert records
    for record in records:
        assert record["input_session_id"] == "conv-41_s3"
        assert record["input_dia_id"] == "D17"
        assert record["input_speaker"] == "Caroline"
        assert record["input_session_datetime"] == "1:56 pm on 8 May, 2023"
        assert record["system_guided"] is False


def test_speaker_and_datetime_reach_extractor_but_dia_id_stays_audit_only(tmp_path):
    pipeline = _make_pipeline(tmp_path)

    pipeline.process(
        "I went to a support group yesterday.",
        session_id="conv-41_s3",
        dia_id="D17",
        speaker="Caroline",
        session_datetime="1:56 pm on 8 May, 2023",
    )

    prompt = pipeline.llm_client.prompts[0]
    assert "Source speaker: Caroline" in prompt
    assert "Session date/time: 1:56 pm on 8 May, 2023" in prompt
    assert "User input: I went to a support group yesterday." in prompt
    assert "D17" not in prompt
