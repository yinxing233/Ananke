#!/usr/bin/env python3
"""v0.2 开发用：确定性合成驱动，验证 v4 事件管道（召回-分类 + 分歧集分析）。

用真实 MemoryPipeline + 真实 EventLogger（保证日志格式与线上一致），
+ 确定性 MockRelationClassifier + MockEmbedding（不下载模型、不联网）。
写入隔离路径 logs/dev_events.jsonl + data/dev/，不污染真实数据。

覆盖的事件类型：memory_write / external_validation(跨 session) / memory_dedup_skip /
local_reorganization(merge+conflict) / working_to_consolidated / consolidated_to_core /
conflict_link / core_promotion_blocked。

用法：
    uv run python tools/dev_simulate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ananke.config import Config
from ananke.llm_client import BaseLLMClient
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline
from ananke.relation import (
    MockRelationClassifier,
    REL_CONTRADICT,
    REL_DUPLICATE,
    REL_MERGEABLE,
    REL_UNRELATED,
)

# 受控向量：badminton 轴 [1,0,0] 演示 EV→升巩固层→merge 升慢层；
# 独立轴 [0,1,0] 演示 X 的「矛盾阻断」(conflict 不升 core，仅写新断言+链接)；
# coffee/tea 走第三轴互不干扰，演示无关写入。
VECTORS = {
    "user likes badminton": [1.0, 0.0, 0.0],
    "user plays badminton": [0.85, 0.52, 0.0],          # cos(badminton)≈0.85（merge 1）
    "user enjoys badminton": [0.85, -0.52, 0.0],        # cos(badminton)≈0.85，与 merge1 近正交→两次 merge 都命中 B
    "user likes coffee": [0.0, 0.0, 1.0],
    "user likes tea": [0.0, 0.0, -1.0],
    "user prefers mornings": [0.0, 1.0, 0.0],           # X 基准轴
    "user prefers evenings": [0.0, 0.9, 0.1],           # cos(X)≈0.9，唯一最大 → 命中 X
    "user prefers nights": [0.0, 0.9, -0.1],            # cos(X)≈0.9，cos(evenings)≈0.81 → 仍命中 X
}


class MockEmbedding:
    def __init__(self, vectors):
        self.vectors = {k: np.array(v, dtype=float) for k, v in vectors.items()}

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([self.vectors.get(t, np.zeros(3)) for t in texts])

    def cosine_similarity(self, a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))


class ScriptedExtractionLLM(BaseLLMClient):
    """只产出抽取结果；关系判定由 MockRelationClassifier 负责。"""

    def __init__(self, extractions):
        self.extractions = list(extractions)

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        if "extract" in prompt.lower():
            return json.dumps(self.extractions.pop(0), ensure_ascii=False) if self.extractions else "[]"
        return "[]"


# (session_id, 输入文本, 应抽取的记忆, 召回时应返回的关系；None=无候选/无关写入)
# 演示链：
#   B  = badminton：跨 session dup×3 → EV=3 升巩固层 → merge×2 → trigger=2 升慢层(core)
#   X  = mornings：dup×3 → EV=3 升巩固层 → 两次 contradict → conflict=1,2 → 被阻断留在中层
#                    (core_promotion_blocked)，同时新断言(evenings/nights)落盘并与 X 双向链接
#   C/tea = 无关写入
STEPS = [
    ("s1", "write badminton", ["user likes badminton"], None),          # 写入 B（working）
    ("s1", "write coffee", ["user likes coffee"], None),                # 写入 C（working）
    ("s2", "dup badminton", ["user likes badminton"], REL_DUPLICATE),   # B.EV=1
    ("s3", "dup badminton", ["user likes badminton"], REL_DUPLICATE),   # B.EV=2
    ("s4", "dup badminton", ["user likes badminton"], REL_DUPLICATE),   # B.EV=3 → 升巩固层
    ("s5", "merge badminton1", ["user plays badminton"], REL_MERGEABLE),# B.trigger=1
    ("s5", "merge badminton2", ["user enjoys badminton"], REL_MERGEABLE), # B.trigger=2 → 升慢层(core)
    ("s6", "write X mornings", ["user prefers mornings"], None),        # 写入 X（working）
    ("s7", "dup X", ["user prefers mornings"], REL_DUPLICATE),          # X.EV=1
    ("s8", "dup X", ["user prefers mornings"], REL_DUPLICATE),          # X.EV=2
    ("s9", "dup X", ["user prefers mornings"], REL_DUPLICATE),          # X.EV=3 → 升巩固层
    ("s10", "conflict X evenings", ["user prefers evenings"], REL_CONTRADICT), # X.conflict=1 → 阻断 + 新断言写入 + 链接
    ("s11", "conflict X nights", ["user prefers nights"], REL_CONTRADICT),     # X.conflict=2 仍阻断
    ("s12", "unrelated tea", ["user likes tea"], None),                 # 无关写入
]


def main() -> None:
    ap = argparse.ArgumentParser(description="v4 确定性合成驱动（召回-分类管道）")
    ap.add_argument("--strategy", default=None, choices=["persistence", "frequency"],
                    help="覆盖迁移策略（默认用 Config.WORKING_PROMOTION_STRATEGY）")
    ap.add_argument("--data", default="data/dev", help="记忆存储目录")
    ap.add_argument("--log", default="logs/dev_events.jsonl", help="事件日志路径")
    args = ap.parse_args()

    if args.strategy:
        Config.WORKING_PROMOTION_STRATEGY = args.strategy

    dev_log = Path(args.log)
    dev_data = Path(args.data)
    for p in (dev_log, *dev_data.glob("*.jsonl")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")

    pipeline = MemoryPipeline(
        MemoryStore(str(dev_data)),
        MockEmbedding(VECTORS),
        ScriptedExtractionLLM([s[2] for s in STEPS]),
        EventLogger(str(dev_log)),
        relation_classifier=MockRelationClassifier(
            relation=REL_UNRELATED,
            script=[s[3] for s in STEPS if s[3] is not None],
        ),
    )
    for _sid, text, _ext, _rel in STEPS:
        pipeline.process(text, session_id=_sid)

    records = [json.loads(line) for line in dev_log.open(encoding="utf-8")]
    kinds = sorted({r["event"] for r in records})
    print(f"[ok] v4 合成 {len(STEPS)} 轮 (strategy={Config.WORKING_PROMOTION_STRATEGY}) → {dev_log} ({len(records)} 条事件)")
    print(f"     事件类型: {', '.join(kinds)}")
    print(f"     下一步: uv run python tools/analyze_trajectory.py --log {dev_log} --data {dev_data}")
    print(f"     分歧对照: 跑两遍(仅 --strategy 不同) → 各跑 evaluate.py → tools/divergence_analysis.py --eval-p <eval_p.json> --eval-f <eval_f.json>")


if __name__ == "__main__":
    main()
