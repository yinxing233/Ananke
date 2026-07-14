"""Selectable working-memory promotion rules for comparative experiments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ananke.config import Config
from ananke.models import MemoryEntry


class WorkingPromotionStrategy(ABC):
    """Scores one working-memory entry and decides whether it graduates."""

    name: str

    @property
    @abstractmethod
    def threshold(self) -> float:
        """Promotion threshold for this strategy."""

    @abstractmethod
    def score(self, memory: MemoryEntry) -> float:
        """Return the evidence used by this strategy."""

    def should_promote(self, memory: MemoryEntry) -> bool:
        return self.score(memory) >= self.threshold


@dataclass(frozen=True)
class PersistencePromotionStrategy(WorkingPromotionStrategy):
    """MVP rule: external validation outweighs internal activation."""

    name: str = "persistence"

    @property
    def threshold(self) -> float:
        return Config.MIGRATION_THRESHOLD

    def score(self, memory: MemoryEntry) -> float:
        return memory.persistence_score


@dataclass(frozen=True)
class FrequencyPromotionStrategy(WorkingPromotionStrategy):
    """Control rule: promote according only to how often a memory is activated."""

    name: str = "frequency"

    @property
    def threshold(self) -> float:
        return Config.FREQUENCY_MIGRATION_THRESHOLD

    def score(self, memory: MemoryEntry) -> float:
        return float(memory.frequency_score)


def promotion_strategy_from_config() -> WorkingPromotionStrategy:
    strategies = {
        "persistence": PersistencePromotionStrategy,
        "frequency": FrequencyPromotionStrategy,
    }
    try:
        return strategies[Config.WORKING_PROMOTION_STRATEGY]()
    except KeyError as error:
        choices = ", ".join(sorted(strategies))
        raise ValueError(
            f"Unknown working promotion strategy {Config.WORKING_PROMOTION_STRATEGY!r}; "
            f"choose one of: {choices}."
        ) from error
