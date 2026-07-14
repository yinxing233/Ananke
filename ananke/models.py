from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field

from ananke.config import Config


class LayerEnum(str, Enum):
    WORKING = "WORKING"
    CONSOLIDATED = "CONSOLIDATED"
    CORE = "CORE"


class MemoryEntry(BaseModel):
    id: str
    content: str
    layer: LayerEnum = LayerEnum.WORKING
    created_at: datetime = Field(default_factory=datetime.now)
    last_activated_at: Optional[datetime] = None
    internal_activation: int = 0
    external_validation: int = 0
    total_activation: int = 0          # EV 或 IA 任一触发时 +1；Frequency 模式（Internal Selection 对照组）使用，不区分来源
    local_reorganization_trigger: int = 0
    source_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def persistence_score(self) -> float:
        return (
            self.external_validation * Config.EXTERNAL_VALIDATION_WEIGHT
            + self.internal_activation * Config.INTERNAL_ACTIVATION_WEIGHT
        )

    @computed_field
    @property
    def frequency_score(self) -> int:
        """Control-group (Internal Selection) evidence: total semantic activations regardless of source."""
        return self.total_activation

    # 预留字段
    decay_coefficient: Optional[float] = None
    persistence_score_log: List[float] = Field(default_factory=list)
