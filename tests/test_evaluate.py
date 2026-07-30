"""A1+B6 reference-grounded 评估契约守护测试。"""

import json
import math

import pytest

from ananke.config import Config
from ananke.llm_client import MockEvaluationJudge, create_eval_llm_client
from ananke.memory_store import MemoryStore
from ananke.models import LayerEnum, MemoryEntry
from tools.evaluate import (
    evaluate,
    judge_single,
    load_probes,
    parse_verdict,
)
from tools.divergence_analysis import analyze, load_eval


class _Judge:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_b6_verdict_labels_are_mutually_exclusive():
    assert parse_verdict("包含") == 1.0
    assert parse_verdict("部分") == Config.EVAL_PARTIAL_CREDIT
    assert parse_verdict("不包含") == 0.0
    assert parse_verdict("结论：不包含。") == 0.0
    with pytest.raises(ValueError, match="ambiguous"):
        parse_verdict("包含 / 不包含")
    with pytest.raises(ValueError, match="unparseable"):
        parse_verdict("无法判断")


def test_b6_judge_receives_question_and_reference_fact():
    judge = _Judge(["包含"])
    score = judge_single(
        judge,
        content="User learned Python.",
        question="What language did the user learn?",
        reference_fact="The user learned Python.",
    )
    assert score == 1.0
    assert "What language did the user learn?" in judge.prompts[0]
    assert "The user learned Python." in judge.prompts[0]


def test_b6_probe_without_reference_fact_is_rejected(tmp_path):
    path = tmp_path / "probes.jsonl"
    path.write_text(
        json.dumps({"question": "What happened?"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="reference_fact"):
        load_probes(path)


def test_b6_judge_failures_are_excluded_and_reported(tmp_path):
    store = MemoryStore(tmp_path / "data")
    store.add(
        MemoryEntry(
            id="m1",
            content="User learned Python.",
            layer=LayerEnum.CONSOLIDATED,
        )
    )
    probes = [
        {"question": "What language?", "reference_fact": "Python."},
        {"question": "What language?", "reference_fact": "Python."},
    ]
    judge = _Judge([RuntimeError("transport"), "部分"])

    report = evaluate(str(tmp_path / "data"), probes, judge)

    assert report["planned_calls"] == 2
    assert report["judge_failures"] == 1
    assert report["judge_failure_rate"] == 0.5
    assert report["evaluation_valid"] is False
    assert report["n_scored_memories"] == 1
    assert report["n_unscored_memories"] == 0
    assert report["results"][0]["per_probe_scores"] == [
        None,
        Config.EVAL_PARTIAL_CREDIT,
    ]
    assert report["results"][0]["max_hit"] == Config.EVAL_PARTIAL_CREDIT


def test_b6_all_failed_memory_is_unscored_not_negative(tmp_path):
    store = MemoryStore(tmp_path / "data")
    store.add(
        MemoryEntry(
            id="m1",
            content="User learned Python.",
            layer=LayerEnum.CONSOLIDATED,
        )
    )
    probes = [{"question": "What language?", "reference_fact": "Python."}]

    report = evaluate(
        str(tmp_path / "data"),
        probes,
        _Judge([RuntimeError("transport")]),
    )

    result = report["results"][0]
    assert result["status"] == "unscored"
    assert result["max_hit"] is None
    assert result["evidence_backed"] is None
    assert report["n_scored_memories"] == 0
    assert report["n_unscored_memories"] == 1
    assert report["hit_rate"] is None


def test_b6_mock_judge_requires_explicit_smoke_opt_in(monkeypatch):
    monkeypatch.setattr(Config, "USE_MOCK_LLM", True)
    monkeypatch.setattr(Config, "EVAL_LLM_API_KEY", "")

    with pytest.raises(RuntimeError, match="allow_mock"):
        create_eval_llm_client()
    assert isinstance(
        create_eval_llm_client(allow_mock=True),
        MockEvaluationJudge,
    )


def test_b6_unscored_memory_remains_in_promoted_set_but_not_hit_denominator(
    tmp_path,
):
    persistence_path = tmp_path / "p.json"
    frequency_path = tmp_path / "f.json"
    persistence_path.write_text(
        json.dumps(
            {
                "evaluation_valid": True,
                "results": [
                    {
                        "content": "shared fact",
                        "layer": "CONSOLIDATED",
                        "ev": 1,
                        "max_hit": 1.0,
                        "evidence_backed": True,
                        "status": "scored",
                    },
                    {
                        "content": "unscored persistence fact",
                        "layer": "CONSOLIDATED",
                        "ev": 0,
                        "max_hit": None,
                        "evidence_backed": None,
                        "status": "unscored",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    frequency_path.write_text(
        json.dumps(
            {
                "evaluation_valid": True,
                "results": [
                    {
                        "content": "shared fact",
                        "layer": "CONSOLIDATED",
                        "ev": 1,
                        "max_hit": 1.0,
                        "evidence_backed": True,
                        "status": "scored",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    persistence = load_eval(str(persistence_path))
    frequency = load_eval(str(frequency_path))
    report = analyze(persistence, frequency)

    assert len(persistence) == 2
    assert report["n_promoted_P"] == 2
    assert report["n_only_P"] == 1
    assert math.isnan(report["hit_rate_onlyP_judge"])
