"""Static preflight estimates extraction misses without constructing a client."""

import json
import sys

import pytest

from ananke.cache import LLMCache
from ananke.config import Config
from ananke.extraction import EXTRACTION_PROMPT_TEMPLATE, _source_context_key
import tools.run_corpus as run_corpus_module
from tools.run_corpus import CorpusTurn, build_preflight_report, validate_run_mode


def test_preflight_counts_unique_extraction_misses_and_existing_hits(tmp_path):
    turns = [
        CorpusTurn("I have a cat.", "s1", speaker="Alex", session_datetime="1 Jan 2026"),
        CorpusTurn("I have a cat.", "s1", speaker="Alex", session_datetime="1 Jan 2026"),
        CorpusTurn("I have a dog.", "s1", speaker="Alex", session_datetime="1 Jan 2026"),
    ]
    cache = LLMCache(
        tmp_path / "cache",
        model_tag="provider|model",
        prompt_templates={"extraction": EXTRACTION_PROMPT_TEMPLATE},
    )
    cache.put(
        "extraction",
        _source_context_key(
            turns[0].text,
            turns[0].speaker,
            turns[0].session_datetime,
        ),
        '["Alex has a cat"]',
    )

    report = build_preflight_report(
        turns,
        cache_dir=tmp_path / "cache",
        model_tag="provider|model",
    )

    assert report["mode"] == "preflight_no_api"
    assert report["turns"] == 3
    assert report["extraction"]["unique_keys"] == 2
    assert report["extraction"]["existing_cache_hit_turns"] == 2
    assert report["extraction"]["cache_miss_keys"] == 1
    assert report["extraction"]["minimum_logical_calls"] == 1
    assert report["extraction"]["actual_http_requests"] is None
    assert report["extraction"]["input_chars_for_misses"] > 0
    assert report["relation"]["minimum_logical_calls"] is None
    assert report["relation"]["actual_http_requests"] is None


def test_preflight_does_not_create_a_missing_cache_directory(tmp_path):
    cache_dir = tmp_path / "missing-cache"

    report = build_preflight_report(
        [CorpusTurn("I have a cat.", "s1")],
        cache_dir=cache_dir,
        model_tag="provider|model",
    )

    assert report["extraction"]["cache_miss_keys"] == 1
    assert report["extraction"]["minimum_logical_calls"] == 1
    assert report["extraction"]["actual_http_requests"] is None
    assert not cache_dir.exists()


def test_cli_preflight_returns_before_client_construction(tmp_path, monkeypatch):
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        json.dumps({"session_id": "s1", "input": "I have a cat."}) + "\n",
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(Config, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(
        run_corpus_module,
        "create_llm_client",
        lambda **kwargs: pytest.fail("preflight constructed an LLM client"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_corpus.py", str(corpus_path), "--preflight"],
    )

    run_corpus_module.main()

    assert not cache_dir.exists()


def test_formal_mode_rejects_cache_bypass_and_requires_explicit_strategy():
    with pytest.raises(ValueError, match="forbids --no-cache"):
        validate_run_mode(
            formal=True,
            no_cache=True,
            refresh_cache=False,
            cache_enabled=True,
            use_mock=False,
            strategy="persistence",
        )
    with pytest.raises(ValueError, match="explicit --strategy"):
        validate_run_mode(
            formal=True,
            no_cache=False,
            refresh_cache=False,
            cache_enabled=True,
            use_mock=False,
            strategy=None,
        )


def test_formal_mode_requires_key_and_zero_temperature():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        validate_run_mode(
            formal=True,
            no_cache=False,
            refresh_cache=False,
            cache_enabled=True,
            use_mock=False,
            strategy="persistence",
            api_key_configured=False,
        )
    with pytest.raises(ValueError, match="LLM_TEMPERATURE=0.0"):
        validate_run_mode(
            formal=True,
            no_cache=False,
            refresh_cache=False,
            cache_enabled=True,
            use_mock=False,
            strategy="persistence",
            api_key_configured=True,
            temperature=0.2,
        )
