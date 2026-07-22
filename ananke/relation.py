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

    def __init__(self, llm_client, temperature: float = 0.0) -> None:
        self.llm_client = llm_client
        self.temperature = temperature

    def classify(self, new_content: str, existing_content: str) -> str:
        prompt = (
            f"Existing memory: {existing_content}\n"
            f"New memory: {new_content}\n\n"
            "What is the relation of the new memory to the existing memory?"
        )
        response = self.llm_client.call_llm(
            prompt, system_prompt=_LLM_SYSTEM_PROMPT, temperature=self.temperature
        ).strip().lower()
        token = response.split()[0] if response.split() else response
        token = token.strip(".,:;\"'")
        return _LABEL_NORMALIZE.get(token, REL_UNRELATED)


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
