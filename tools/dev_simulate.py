#!/usr/bin/env python3
"""开发用：确定性合成驱动，验证动力学分析脚本（tools/analyze_trajectory.py）。

注意：这不是实验语料，只是用来证明「事件日志 → Trajectory 重建」这条管道能跑通。
- 用真实 MemoryPipeline + 真实 EventLogger（保证日志格式与线上一致）。
- 用不下载模型的确定性 FakeEmbedding + 脚本化 LLM（避免真实 API / 真实嵌入依赖）。
- 写入隔离路径 logs/dev_events.jsonl + data/dev/，不污染真实数据。

覆盖的事件类型：memory_write / internal_activation / external_validation /
working_to_consolidated / local_reorganization / consolidated_to_core / working_eviction。

关于阈值（重要，避免误导）：
- LOCAL_REORG_THRESHOLD 保持**真实默认值 2**（之前为演示临时改成 1 会造成
  "阈值2却trigger=1升层"的歧义）。本脚本通过让 M3 同时与两条猫记忆相似，
  在一次升层里累积 trigger=2，从而真实地触发中→慢迁移。
- WORKING_CAPACITY 临时降到 4 仅为在小规模下也能演示淘汰（真实默认 50），
  不影响升层/迁移语义，仅影响"何时淘汰"。

用法：
    uv run python tools/dev_simulate.py
"""
from __future__ import annotations

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

# ---- 开发期配置覆盖（仅影响本脚本，不改动源码默认值）----
Config.WORKING_CAPACITY = 4  # 仅为演示淘汰；真实默认 50，不影响迁移语义
# LOCAL_REORG_THRESHOLD 保持真实默认 2（不覆盖），见文件头说明


class FakeEmbedding:
    """关键词 → one-hot 向量。同关键词余弦=1.0（互斥后只触发外部验证 EV，不触发 IA），
    不同关键词=0.0（不触发）。未知文本→零向量（余弦 0）。不下载任何模型。"""

    DIM = 16
    KW = {
        "羽毛球": 0, "猫": 1, "咖啡": 2, "游泳": 3,
        "读书": 4, "旅行": 5, "爬山": 6,
    }

    def _vec(self, text: str):
        for kw, idx in self.KW.items():
            if kw in text:
                v = [0.0] * self.DIM
                v[idx] = 1.0
                return np.array(v)
        return np.array([0.0] * self.DIM)

    def encode(self, text):
        # 返回 numpy 数组以匹配真实 EmbeddingEngine 的契约（pipeline v3 去重逻辑调 .tolist()）。
        # 单条输入保持 shape (1, DIM)，兼容 pipeline 的 `[0]` 取向量写法。
        if isinstance(text, list):
            return np.array([self._vec(t) for t in text])
        return np.array([self._vec(text)])

    @staticmethod
    def cosine_similarity(a, b) -> float:
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return sum(x * y for x, y in zip(a, b)) / (na * nb)


class ScriptedLLM(BaseLLMClient):
    """脚本化 LLM：抽取结果队列 + 重组关系队列。"""

    def __init__(self, extractions, relations):
        self.extractions = list(extractions)
        self.relations = list(relations)

    def call_llm(self, prompt: str, system_prompt=None, temperature=None) -> str:
        # v3 起 extraction.py 的抽取 prompt 改为英文（跨语言嵌入失真修复），
        # 故按英文关键词匹配；重组分支仍匹配中文（reorganization.py 的 prompt 仍是中文）。
        if "extract" in prompt.lower():
            return json.dumps(self.extractions.pop(0), ensure_ascii=False) if self.extractions else "[]"
        if "关系" in prompt or "合并" in prompt:
            return self.relations.pop(0) if self.relations else "无关"
        return "无关"


# (输入文本, 应抽取的记忆)。设计覆盖全部事件类型；猫簇让 M3 获 trigger=2 真实升慢层。
SCRIPT = [
    ("用户喜欢打羽毛球", ["用户喜欢打羽毛球"]),        # M1 写入
    ("这周又去打羽毛球了", []),                         # M1 外部验证（互斥后同关键词 cosine=1.0 只触发 EV）
    ("周末也去打羽毛球", []),
    ("每天打羽毛球", []),                               # M1 persist=3.0 → 升巩固层
    ("用户养了一只猫", ["用户养了一只猫"]),             # M2 写入
    ("用户很爱猫", []),
    ("猫是用户最好的朋友", []),
    ("猫今天又粘人了", []),                             # M2 persist=3.0 → 升巩固层
    ("用户养的猫很粘人", ["用户养的猫很粘人"]),         # M2b(猫) 写入
    ("猫一直跟着我", []),
    ("猫喜欢趴腿上", []),
    ("猫太粘人了", []),                                # M2b persist=3.0 → 升巩固层
                                                        #   （与 M2 相似 → reorg trigger=1，未达2不升慢层）
    ("用户喜欢喝咖啡", ["用户喜欢喝咖啡"]),             # M4 写入(无验证)
    ("用户喜欢游泳", ["用户喜欢游泳"]),                 # M5 写入
    ("用户喜欢读书", ["用户喜欢读书"]),                 # M6 写入
    ("用户喜欢旅行", ["用户喜欢旅行"]),                 # M7 写入
    ("用户还喜欢爬山", ["用户还喜欢爬山"]),             # M8 写入 → 触发 working 淘汰
    ("用户有一只宠物猫", ["用户有一只宠物猫"]),         # M3(猫) 写入
    ("宠物猫很可爱", []),
    ("猫喜欢睡觉", []),
    ("猫早上会叫", []),                                # M3 persist=3.0 → 升巩固层
                                                        #   （同时与 M2、M2b 相似 → reorg trigger=2 ≥2 → 升慢层）
]
# 重组关系队列：M2b 升层时 1 次(与M2)，M3 升层时 2 次(与M2、M2b)
RELATIONS = ["矛盾", "矛盾", "矛盾"]


def main() -> None:
    dev_log = Path("logs/dev_events.jsonl")
    dev_data = Path("data/dev")
    # 用截断而非删除来清空（沙箱禁止删除文件，但允许截断）
    for p in (dev_log, *dev_data.glob("*.jsonl")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")

    pipeline = MemoryPipeline(
        MemoryStore(str(dev_data)),
        FakeEmbedding(),
        ScriptedLLM([e for _, e in SCRIPT], RELATIONS),
        EventLogger(str(dev_log)),
    )
    for text, _ in SCRIPT:
        pipeline.process(text)

    n_lines = sum(1 for _ in dev_log.open(encoding="utf-8"))
    print(f"[ok] 合成 {len(SCRIPT)} 轮对话 → {dev_log} ({n_lines} 条事件)")
    print(f"     下一步运行: uv run python tools/analyze_trajectory.py --log {dev_log} --data {dev_data}")


if __name__ == "__main__":
    main()
