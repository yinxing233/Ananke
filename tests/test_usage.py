"""Request-level LLM metering: count real HTTP attempts and provider usage."""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from openai import RateLimitError

import ananke.llm_client as llm_client_module
from ananke.llm_client import OpenAICompatibleClient


class _Completions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _client(tmp_path, completions):
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        rpm=0,
        provider="test-provider",
        role="driver",
        usage_log=tmp_path / "usage.jsonl",
    )
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return client


def test_sdk_implicit_retries_are_disabled_for_complete_http_accounting(
    tmp_path,
    monkeypatch,
):
    captured = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        rpm=0,
        provider="test-provider",
        usage_log=tmp_path / "usage.jsonl",
    )

    assert captured["max_retries"] == 0
    assert not (tmp_path / "usage.jsonl").exists()


def test_successful_http_attempt_records_tokens_and_output_cap(tmp_path):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="duplicate"))],
        usage=SimpleNamespace(
            prompt_tokens=17,
            completion_tokens=2,
            total_tokens=19,
            prompt_tokens_details=SimpleNamespace(cached_tokens=11),
        ),
    )
    completions = _Completions(response=response)
    client = _client(tmp_path, completions)

    assert client.call_llm(
        "pair",
        system_prompt="judge",
        max_tokens=6,
        operation="relation",
    ) == "duplicate"

    assert completions.calls[0]["max_tokens"] == 6
    records = [
        json.loads(line)
        for line in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["operation"] == "relation"
    assert records[0]["status"] == "success"
    assert records[0]["prompt_tokens"] == 17
    assert records[0]["completion_tokens"] == 2
    assert records[0]["cached_prompt_tokens"] == 11
    assert client.usage_stats()["http_requests"] == 1
    assert client.usage_stats()["total_tokens"] == 19
    assert client.usage_stats()["logical_calls_by_operation"] == {"relation": 1}
    assert client.usage_stats()["http_requests_by_operation"] == {"relation": 1}


def test_failed_http_attempt_is_recorded_once_and_propagated(tmp_path):
    completions = _Completions(error=RuntimeError("network down"))
    client = _client(tmp_path, completions)

    with pytest.raises(RuntimeError, match="network down"):
        client.call_llm("prompt", operation="extraction")

    records = [
        json.loads(line)
        for line in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["status"] == "error"
    assert records[0]["error_type"] == "RuntimeError"
    assert client.usage_stats()["http_requests"] == 1
    assert client.usage_stats()["errors"] == 1


def test_rate_limit_retry_records_each_http_attempt(tmp_path, monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="duplicate"))],
        usage=SimpleNamespace(
            prompt_tokens=7,
            completion_tokens=1,
            total_tokens=8,
            prompt_tokens_details=None,
        ),
    )
    rate_limit = RateLimitError(
        "quota",
        response=httpx.Response(
            429,
            request=httpx.Request("POST", "https://example.invalid/v1"),
        ),
        body=None,
    )

    class _RetryOnce:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise rate_limit
            return response

    monkeypatch.setattr(llm_client_module.time, "sleep", lambda seconds: None)
    completions = _RetryOnce()
    client = _client(tmp_path, completions)

    assert client.call_llm("pair", operation="relation") == "duplicate"
    records = [
        json.loads(line)
        for line in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["status"] for record in records] == [
        "rate_limited",
        "success",
    ]
    assert records[0]["call_id"] == records[1]["call_id"]
    assert client.usage_stats()["logical_calls"] == 1
    assert client.usage_stats()["http_requests"] == 2
    assert client.usage_stats()["rate_limited"] == 1
    assert client.usage_stats()["logical_calls_by_operation"] == {"relation": 1}
    assert client.usage_stats()["http_requests_by_operation"] == {"relation": 2}
