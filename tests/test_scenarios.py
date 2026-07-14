import json

import numpy as np

from ananke.config import Config
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import LayerEnum, MemoryEntry
from ananke.pipeline import MemoryPipeline
from ananke.promotion import FrequencyPromotionStrategy, promotion_strategy_from_config


class FakeEmbedding:
    """Exact vectors make threshold tests independent of downloaded ML models."""
    vectors = {
        "fact": [1.0, 0.0], "related": [0.7, 0.71414284], "different": [0.0, 1.0],
        "merge-a": [0.0, 1.0], "merge-b": [0.0, 1.0],
    }

    def encode(self, texts):
        if isinstance(texts, str): texts = [texts]
        return np.asarray([self.vectors[text] for text in texts])

    def cosine_similarity(self, left, right):
        return float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right)))


class FakeLLM:
    def __init__(self, extractions, relation="合并"):
        self.extractions, self.relation = list(extractions), relation

    def call_llm(self, prompt, *args, **kwargs):
        if "提取" in prompt: return json.dumps(self.extractions.pop(0), ensure_ascii=False)
        return self.relation


def pipeline(tmp_path, extractions=(), relation="合并"):
    return MemoryPipeline(MemoryStore(tmp_path / "data"), FakeEmbedding(), FakeLLM(extractions, relation), EventLogger(tmp_path / "events.jsonl"))


def test_external_validation_promotes_to_consolidated(tmp_path):
    app = pipeline(tmp_path, [[], [], []])
    memory = MemoryEntry(id="fact", content="fact")
    app.memory_store.add(memory)
    for _ in range(3): app.process("fact")
    assert app.memory_store.find("fact").layer is LayerEnum.CONSOLIDATED
    assert app.memory_store.find("fact").external_validation == 3


def test_system_guided_input_cannot_be_external_validation(tmp_path):
    app = pipeline(tmp_path, [[]])
    app.memory_store.add(MemoryEntry(id="fact", content="fact"))
    app.process("fact", system_guided=True)
    memory = app.memory_store.find("fact")
    assert memory.internal_activation == 1 and memory.external_validation == 0


def test_internal_activation_promotes_after_persistence_threshold(tmp_path):
    app = pipeline(tmp_path, [[]] * 9)
    app.memory_store.add(MemoryEntry(id="fact", content="fact"))
    for _ in range(9): app.process("related")
    memory = app.memory_store.find("fact")
    assert memory.layer is LayerEnum.CONSOLIDATED
    assert memory.internal_activation == 9 and memory.external_validation == 0


def test_frequency_control_promotes_by_activation_count(tmp_path):
    app = pipeline(tmp_path, [[], [], []])
    app.promotion_strategy = FrequencyPromotionStrategy()
    app.memory_store.add(MemoryEntry(id="fact", content="fact"))

    for _ in range(3):
        app.process("fact")

    memory = app.memory_store.find("fact")
    assert memory.layer is LayerEnum.CONSOLIDATED
    assert memory.internal_activation == 0 and memory.external_validation == 3


def test_config_selects_frequency_control(monkeypatch):
    monkeypatch.setattr(Config, "WORKING_PROMOTION_STRATEGY", "frequency")
    assert isinstance(promotion_strategy_from_config(), FrequencyPromotionStrategy)


def test_persistence_and_frequency_control_diverge_on_mixed_evidence(tmp_path):
    persistence = pipeline(tmp_path / "persistence", [[], [], []])
    frequency = pipeline(tmp_path / "frequency", [[], [], []])
    frequency.promotion_strategy = FrequencyPromotionStrategy()
    for app in (persistence, frequency):
        app.memory_store.add(MemoryEntry(id="fact", content="fact"))
        app.process("related")
        app.process("fact", system_guided=True)

    assert persistence.memory_store.find("fact").layer is LayerEnum.WORKING
    assert frequency.memory_store.find("fact").layer is LayerEnum.WORKING

    for app in (persistence, frequency):
        app.process("fact")

    assert persistence.memory_store.find("fact").layer is LayerEnum.WORKING
    assert frequency.memory_store.find("fact").layer is LayerEnum.CONSOLIDATED


def test_reorganization_promotes_to_core_after_two_triggers(tmp_path):
    app = pipeline(tmp_path, [[], []], relation="合并")
    existing = MemoryEntry(id="existing", content="merge-a", layer=LayerEnum.CONSOLIDATED)
    candidate = MemoryEntry(id="candidate", content="merge-b", local_reorganization_trigger=1)
    app.memory_store.add(existing); app.memory_store.add(candidate)
    candidate.external_validation = 3
    app.memory_store.update(candidate)
    app.process("different")
    assert app.memory_store.find("candidate").layer is LayerEnum.CORE


def test_conflict_reorganization_promotes_to_core(tmp_path):
    app = pipeline(tmp_path, [[], []], relation="矛盾")
    app.memory_store.add(MemoryEntry(id="existing", content="merge-a", layer=LayerEnum.CONSOLIDATED))
    candidate = MemoryEntry(id="candidate", content="merge-b", local_reorganization_trigger=1, external_validation=3)
    app.memory_store.add(candidate)
    result = app.process("different")
    assert result["reorganizations"] == [{
        "trigger_memory_id": "candidate",
        "paired_memory_id": "existing",
        "action": "conflict",
        "cosine_similarity": 1.0,
    }]
    assert app.memory_store.find("candidate").layer is LayerEnum.CORE


def test_capacity_evicts_lowest_persistence_score(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "WORKING_CAPACITY", 1)
    app = pipeline(tmp_path, [["different"]])
    low = MemoryEntry(id="low", content="fact")
    high = MemoryEntry(id="high", content="related", external_validation=1)
    app.memory_store.add(low); app.memory_store.add(high)
    app.process("different")
    assert app.memory_store.find("low") is None
    assert app.memory_store.find("high") is not None


def test_reorganization_audit_log_has_required_fields(tmp_path):
    app = pipeline(tmp_path, [[], []], relation="合并")
    app.memory_store.add(MemoryEntry(id="existing", content="merge-a", layer=LayerEnum.CONSOLIDATED))
    app.memory_store.add(MemoryEntry(id="candidate", content="merge-b", local_reorganization_trigger=1, external_validation=3))
    app.process("different")
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    reorganization = next(record for record in records if record["event"] == "local_reorganization")
    assert {"timestamp", "event", "trigger_memory_id", "paired_memory_id", "action", "cosine_similarity"} <= reorganization.keys()
    assert {"working_to_consolidated", "local_reorganization", "consolidated_to_core"} <= {record["event"] for record in records}


def test_store_survives_restart_and_retrieval_prioritizes_core(tmp_path):
    store = MemoryStore(tmp_path / "data")
    store.add(MemoryEntry(id="working", content="fact"))
    store.add(MemoryEntry(id="core", content="different", layer=LayerEnum.CORE))
    reloaded = MemoryStore(tmp_path / "data")
    app = MemoryPipeline(reloaded, FakeEmbedding(), FakeLLM([]), EventLogger(tmp_path / "events.jsonl"))
    assert [memory.id for memory in app.retrieve()] == ["core", "working"]
