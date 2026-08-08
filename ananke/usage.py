"""Append-only request-level metering for real LLM HTTP attempts.

The cache counts logical hits and misses.  This module records the lower layer:
every actual provider request, including failed and rate-limited attempts, plus
provider-reported token usage when available.  It deliberately does not infer
prices; a calibration run can combine these stable measurements with whichever
price schedule is current at that time.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _field(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def usage_fields(usage: Any) -> dict[str, Optional[int]]:
    """Normalize OpenAI-compatible usage objects without inventing tokens."""
    prompt_tokens = _field(usage, "prompt_tokens")
    completion_tokens = _field(usage, "completion_tokens")
    total_tokens = _field(usage, "total_tokens")
    # Responses-style aliases are accepted for compatible gateways.
    if prompt_tokens is None:
        prompt_tokens = _field(usage, "input_tokens")
    if completion_tokens is None:
        completion_tokens = _field(usage, "output_tokens")
    details = _field(usage, "prompt_tokens_details")
    cached_tokens = _field(details, "cached_tokens")
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_prompt_tokens": cached_tokens,
    }


class RequestUsageMeter:
    """Thread-safe JSONL ledger and in-process aggregate.

    ``path=None`` keeps the aggregate without writing a file.  The log directory
    is created only when the first real HTTP attempt is recorded, so constructing
    a client or running preflight remains side-effect free.
    """

    def __init__(
        self,
        path: str | Path | None,
        *,
        role: str,
        provider: str,
        model: str,
    ) -> None:
        self.path = Path(path) if path else None
        self.role = role
        self.provider = provider
        self.model = model
        self._lock = threading.Lock()
        self._status = Counter()
        self._http_operations = Counter()
        self._call_ids: set[str] = set()
        self._call_operations: dict[str, str] = {}
        self._token_totals = Counter()
        self._successful_without_usage = 0

    def record(
        self,
        *,
        call_id: str,
        operation: str,
        attempt: int,
        status: str,
        prompt: str,
        system_prompt: str | None,
        completion: str | None = None,
        usage: Any = None,
        error: BaseException | None = None,
        duration_ms: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        tokens = usage_fields(usage)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "call_id": call_id,
            "operation": operation,
            "attempt": attempt,
            "status": status,
            "prompt_chars": len(prompt),
            "system_prompt_chars": len(system_prompt or ""),
            "completion_chars": len(completion or ""),
            "max_tokens": max_tokens,
            "duration_ms": round(duration_ms, 3) if duration_ms is not None else None,
            **tokens,
            "error_type": type(error).__name__ if error is not None else None,
            "error": str(error)[:500] if error is not None else None,
        }
        with self._lock:
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._status[status] += 1
            self._http_operations[operation] += 1
            self._call_ids.add(call_id)
            self._call_operations.setdefault(call_id, operation)
            for name in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cached_prompt_tokens",
            ):
                value = tokens[name]
                if isinstance(value, int):
                    self._token_totals[name] += value
            if status == "success" and tokens["total_tokens"] is None:
                self._successful_without_usage += 1

    def stats(self) -> dict:
        return {
            "logical_calls": len(self._call_ids),
            "http_requests": sum(self._status.values()),
            "successes": self._status["success"],
            "rate_limited": self._status["rate_limited"],
            "errors": sum(
                count
                for status, count in self._status.items()
                if status not in {"success", "rate_limited"}
            ),
            "logical_calls_by_operation": dict(Counter(self._call_operations.values())),
            "http_requests_by_operation": dict(self._http_operations),
            "prompt_tokens": self._token_totals["prompt_tokens"],
            "completion_tokens": self._token_totals["completion_tokens"],
            "total_tokens": self._token_totals["total_tokens"],
            "cached_prompt_tokens": self._token_totals["cached_prompt_tokens"],
            "successful_requests_without_usage": self._successful_without_usage,
            "log_path": str(self.path) if self.path is not None else None,
        }
