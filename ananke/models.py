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
    total_activation: int = 0          # EV / IA / 任一重组触发时 +1；Frequency 模式（Internal Selection 对照组）使用，不区分来源
    local_reorganization_trigger: int = 0  # mergeable 累积（v4 §2.3）
    conflict_trigger: int = 0              # contradict 累积（v4 §2.3，与 mergeable 分开计）。
                                           # 一旦 >0 即成为 CORE 晋升阻断器（Fable5 漂移1：被矛盾=被检验失败，非确认）。
    conflict_links: List[str] = Field(default_factory=list)  # 双向矛盾链接：与本条记忆相互矛盾的记忆 id 列表（v4 §2.3/漂移2）
    session_id: Optional[str] = None       # 记忆首次写入时所属 session；跨 session 再断言 = EV 的独立性代理（v4 §3）
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
