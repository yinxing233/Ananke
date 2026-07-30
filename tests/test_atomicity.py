"""A3 轮级原子性与失败审计守护测试。"""

import json
from pathlib import Path

import numpy as np
import pytest

import ananke.pipeline as pipeline_module
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.relation import MockRelationClassifier, REL_RELATED


class _Embedding:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        vectors = {
            "existing fact": [1.0, 0.0],
            "new related fact": [0.8, 0.6],
        }
        return np.array([vectors.get(text, [0.0, 0.0]) for text in texts])

    def cosine_similarity(self, left, right):
        left_norm = np.linalg.norm(left)
        right_norm = np.linalg.norm(right)
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return float(np.dot(left, right) / (left_norm * right_norm))


class _ExtractionLLM:
    cache = None

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        return '["new related fact"]'


def _records(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_a3_failed_turn_rolls_back_state_and_state_events(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    log_path = tmp_path / "events.jsonl"
    store = MemoryStore(data_dir)
    store.add(MemoryEntry(id="existing", content="existing fact", session_id="s1"))
    pipeline = MemoryPipeline(
        store,
        _Embedding(),
        _ExtractionLLM(),
        EventLogger(log_path),
        relation_classifier=MockRelationClassifier(REL_RELATED),
    )

    def fail_after_relation_side_effects(*args, **kwargs):
        raise RuntimeError("capacity failure")

    monkeypatch.setattr(
        pipeline_module,
        "enforce_working_capacity",
        fail_after_relation_side_effects,
    )

    with pytest.raises(RuntimeError, match="capacity failure"):
        pipeline.process("input", session_id="s2")

    in_memory = pipeline.memory_store.find("existing")
    assert in_memory is not None
    assert in_memory.internal_activation == 0
    assert [m.id for m in pipeline.memory_store.get_working_memories()] == ["existing"]

    reloaded = MemoryStore(data_dir)
    persisted = reloaded.find("existing")
    assert persisted is not None
    assert persisted.internal_activation == 0
    assert [m.id for m in reloaded.get_working_memories()] == ["existing"]

    records = _records(log_path)
    assert [record["event"] for record in records] == ["turn_failed"]
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["input_session_id"] == "s2"


def test_a3_failure_audit_bypasses_rolled_back_state_buffer(tmp_path):
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(log_path)

    with pytest.raises(RuntimeError):
        with logger.transaction():
            logger.log("memory_write", memory_id="transient")
            logger.log_audit(
                "classification_unparsed",
                raw_response="bad token",
                attempt=1,
            )
            raise RuntimeError("abort")

    records = _records(log_path)
    assert [record["event"] for record in records] == ["classification_unparsed"]


def test_a3_partial_state_log_flush_is_truncated_and_state_is_restored(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(log_path)
    store = MemoryStore(data_dir)
    pipeline = MemoryPipeline(
        store,
        _Embedding(),
        _ExtractionLLM(),
        logger,
        relation_classifier=MockRelationClassifier(REL_RELATED),
    )
    original_append = logger._append

    def partially_write_then_fail(records):
        if any(record["event"] == "memory_write" for record in records):
            with log_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(records[0]) + "\n")
            raise OSError("log flush failed")
        original_append(records)

    monkeypatch.setattr(logger, "_append", partially_write_then_fail)

    with pytest.raises(OSError, match="log flush failed"):
        pipeline.process("input", session_id="s2")

    assert store.get_working_memories() == []
    assert MemoryStore(data_dir).get_working_memories() == []
    assert [record["event"] for record in _records(log_path)] == ["turn_failed"]


def test_a3_prepare_failure_preserves_every_existing_layer_file(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    store = MemoryStore(data_dir)
    from ananke.models import LayerEnum

    store.add(MemoryEntry(id="working", content="w", layer=LayerEnum.WORKING))
    store.add(
        MemoryEntry(
            id="consolidated",
            content="c",
            layer=LayerEnum.CONSOLIDATED,
        )
    )
    store.add(MemoryEntry(id="core", content="k", layer=LayerEnum.CORE))
    originals = {
        layer: store._path(layer).read_bytes()
        for layer in LayerEnum
    }

    original_write_text = Path.write_text

    def fail_first_prepare(path, *args, **kwargs):
        if (
            path.name.startswith(".consolidated.jsonl.")
            and path.name.endswith(".tmp")
        ):
            raise OSError("prepare failed")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_first_prepare)

    with pytest.raises(OSError, match="prepare failed"):
        store._persist_layers(LayerEnum)

    for layer in LayerEnum:
        assert store._path(layer).read_bytes() == originals[layer]
