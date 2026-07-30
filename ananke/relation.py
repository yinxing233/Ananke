"""Relation classifier: 5-way classification of (new_memory, existing_memory) pairs.

Protocol v4 §2.2 — replaces the v3 cosine-threshold dedup/reorg scheme.

The classifier consumes a *newly extracted* memory `m` and a *recalled* existing
memory `e` (cosine ≥ R_RECALL) and returns exactly one of five relation labels:

    duplicate  : m states the SAME fact as e (re-confirmation / restatement)
    contradict : m states the OPPOSITE / an incompatible fact relative to e
    mergeable  : m is a COMPATIBLE additional fact that extends or combines with e
    related    : m is on the SAME topic but a different, non-overlapping fact
    unrelated  : m is on a different topic with no meaningful relation

The signal mapping driven by these labels lives in pipeline.py (v4 §2.3). The
classifier itself is deliberately narrow: it only decides the relation, never
the side effects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ananke.cache import normalize

# Canonical relation labels.
REL_DUPLICATE: str = "duplicate"
REL_CONTRADICT: str = "contradict"
REL_MERGEABLE: str = "mergeable"
REL_RELATED: str = "related"
REL_UNRELATED: str = "unrelated"

RELATION_LABELS = frozenset(
    {REL_DUPLICATE, REL_CONTRADICT, REL_MERGEABLE, REL_RELATED, REL_UNRELATED}
)

# Triggers that feed the consolidation→core gate (v4 §2.3 / §4).
TRIGGER_LABELS = frozenset({REL_MERGEABLE, REL_CONTRADICT})

_LLM_SYSTEM_PROMPT = (
    "You are a precise memory relation judge. Given an EXISTING memory and a NEW candidate memory, "
    "classify their relation into EXACTLY ONE of these five labels:\n"
    "- duplicate: the new memory states the SAME fact as the existing one (a re-confirmation or restatement).\n"
    "- mergeable: the new memory is a COMPATIBLE additional fact that extends or combines with the existing one.\n"
    "- contradict: the new memory states the OPPOSITE or an incompatible fact relative to the existing one.\n"
    "- related: the new memory is on the SAME topic but a different, non-overlapping fact (not duplicate/merge/contradict).\n"
    "- unrelated: the new memory is on a different topic with no meaningful relation.\n"
    "Respond with ONLY the single label word in lowercase, no punctuation, no explanation."
)

# Exact-token normalization (kept explicit to avoid substring hazards such as
# "unrelated" matching "related").
_LABEL_NORMALIZE = {
    "duplicate": REL_DUPLICATE,
    "duplicates": REL_DUPLICATE,
    "contradict": REL_CONTRADICT,
    "contradiction": REL_CONTRADICT,
    "conflict": REL_CONTRADICT,
    "mergeable": REL_MERGEABLE,
    "merge": REL_MERGEABLE,
    "related": REL_RELATED,
    "relate": REL_RELATED,
    "unrelated": REL_UNRELATED,
    "irrelevant": REL_UNRELATED,
}

# 用户 prompt 的**固定结构**（{existing}/{new} 为输入变量占位）。关系分类 prompt 模板 =
# _LLM_SYSTEM_PROMPT + RELATION_USER_PREFIX，作为缓存 key 的 prompt_hash 来源（B3）。
# 改此结构即全量失效。
RELATION_USER_PREFIX = (
    "Existing memory: {existing}\n"
    "New memory: {new}\n\n"
    "What is the relation of the new memory to the existing memory?"
)
# 完整模板（system + 用户结构），供 llm_client 构造缓存时算 SHA1。
RELATION_PROMPT_TEMPLATE = _LLM_SYSTEM_PROMPT + RELATION_USER_PREFIX


class RelationClassifier(ABC):
    """Decides the relation label for a (new, existing) memory pair."""

    @abstractmethod
    def classify(self, new_content: str, existing_content: str) -> str:
        """Return one of RELATION_LABELS for the pair (new, existing)."""
        raise NotImplementedError


class LLMRelationClassifier(RelationClassifier):
    """Scheme B (protocol v4 §2.2): structured 5-choice via the driving LLM.

    Reuses the same llm_client as extraction, keeping the driving end uniform.
    The *evaluation* judge is a different-family LLM (v4 §5) and lives in
    tools/evaluate.py, never here.
    """

    def __init__(
        self,
        llm_client,
        temperature: float = 0.0,
        event_logger=None,
    ) -> None:
        self.llm_client = llm_client
        self.temperature = temperature
        self.event_logger = event_logger

    def classify(self, new_content: str, existing_content: str) -> str:
        prompt = (
            f"Existing memory: {existing_content}\n"
            f"New memory: {new_content}\n\n"
            "What is the relation of the new memory to the existing memory?"
        )
        # 两级缓存（分类对层）：同 (new, existing) 句对永远返回首次判定 → P/F 重跑与 sweep
        # 中重现的句对全部免费命中，且消除分类非确定性对 D 的污染。
        cache = getattr(self.llm_client, "cache", None)
        norm = normalize(new_content) + "||" + normalize(existing_content)
        cached = cache.get("pairs", norm) if cache else None
        if cached is not None:
            return cached  # 命中：已是归一化标签（C1），直接返回
        last_err: Optional[Exception] = None
        # 解析失败 / 空响应 = 基础设施故障（超时/429/连接断），不等于 unrelated，
        # 不落盘、重试、最终 raise（C2：unrelated 是唯一不发光信号的类，每次故障折叠
        # 都无声吞掉一个潜在 EV 或 contradict）。
        for attempt in range(1, 4):
            response = ""
            try:
                response = self.llm_client.call_llm(
                    prompt, system_prompt=_LLM_SYSTEM_PROMPT, temperature=self.temperature
                ).strip()
                if not response:
                    raise ValueError("关系分类收到空响应（基础设施故障，非语义判定）")
                token = response.lower().split()[0].strip(".,:;\"'")
                if not token:
                    raise ValueError("关系分类响应无可解析 token（基础设施故障）")
                label = _LABEL_NORMALIZE.get(token)
                if label is None:
                    raise ValueError(f"unknown relation label: {token!r}")
                # C1：只缓存合法归一化标签。
                if cache:
                    cache.put("pairs", norm, label)
                return label
            except ValueError as e:
                last_err = e
                if self.event_logger is not None:
                    self.event_logger.log_audit(
                        "classification_unparsed",
                        raw_response=response[:200],
                        attempt=attempt,
                        max_attempts=3,
                        error=str(e),
                        new_content_summary=new_content[:120],
                        existing_content_summary=existing_content[:120],
                    )
                continue
        raise last_err or RuntimeError("关系分类失败（基础设施故障且重试未恢复）")


class MockRelationClassifier(RelationClassifier):
    """Deterministic classifier for tests / dev simulation (no API, no model).

    Either returns a constant label, or pops labels from a scripted queue in
    call order. Lets every v4 signal path be exercised predictably.
    """

    def __init__(self, relation: str = REL_UNRELATED, script: Optional[list[str]] = None) -> None:
        self.relation = relation
        self.script = list(script) if script else None

    def classify(self, new_content: str, existing_content: str) -> str:
        if self.script:
            return self.script.pop(0)
        return self.relation
