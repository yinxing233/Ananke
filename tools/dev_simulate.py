#!/usr/bin/env python3
"""开发用：确定性合成驱动，验证动力学分析脚本（tools/analyze_trajectory.py）。

注意：这不是实验语料，只是用来证明「事件日志 → Trajectory 重建」这条管道能跑通。
- 用真实 MemoryPipeline + 真实 EventLogger（保证日志格式与线上一致）。
- 用不下载模型的确定性 FakeEmbedding + 脚本化 LLM（避免真实 API / 真实嵌入依赖）。
- 写入隔离路径 logs/dev_events.jsonl + data/dev/，不污染真实数据。

覆盖的事件类型：memory_write / internal_activation / external_validation /
memory_dedup_skip / working_to_consolidated / local_reorganization / consolidated_to_core / working_eviction。

关于阈值（重要，避免误导）：
- LOCAL_REORG_THRESHOLD 保持**真实默认值 2**（阈值2需 trigger=2 才升慢层，避免
  "阈值1却trigger=1升层"的歧义）。本脚本让 M3 同时与 M2、M2b 两条猫记忆相似
  （两两余弦=0.75），在一次升层里累积 trigger=2，从而真实地触发中→慢迁移。
- REORG_SIMILARITY_THRESHOLD 临时降到 **0.70**（真实默认 0.90）。真实系统中
  reorg(0.90) > 去重(0.80)，任何"够近到触发重组"的记忆会先被去重吃掉，故 reorg
  在真实运行极少触发——这是已知系统性质。本脚本为演示 reorg/core 事件，把 reorg
  阈值降到去重之下（0.70<0.80），使猫簇(相似0.75)既能通过去重、又能触发重组。
  这不改变"去重门控重组"的真实结论，仅让该事件类型在 dev 工具里可见。
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
# REORG_SIMILARITY_THRESHOLD 降到 0.70（真实默认 0.90）：真实系统中 reorg(0.90) > 去重(0.80)，
# "够近到触发重组"的记忆必先于去重被吞，故 reorg 在真实运行极少触发（已知系统性质）。本脚本为
# 演示 reorg/core 事件，把 reorg 阈值降到去重之下（0.70<0.80），使猫簇(相似0.75)既能过词重又能触发重组。
Config.REORG_SIMILARITY_THRESHOLD = 0.70


class FakeEmbedding:
    """关键词 → one-hot 向量。同关键词余弦=1.0（互斥后只触发外部验证 EV，不触发 IA），
    不同关键词=0.0（不触发）。未知文本→零向量（余弦 0）。不下载任何模型。"""

    DIM = 16
    # 互斥关键词 → one-hot 维度（与真实嵌入不同维度互不干扰）
    ONEHOT_KW = {
        "羽毛球": 0, "猫": 1, "咖啡": 2, "游泳": 3,
        "读书": 4, "旅行": 5, "爬山": 6,
    }
    # 猫簇专用三维子空间（dims 1,7,8）：A=猫、B=宠物、C=喵星人 三个向量两两余弦=0.75。
    # 既是"非近义"（< 去重 0.80 → 不会被去重吃掉），又能触发 reorg（>= 开发覆盖值 0.70）。
    # "猫" 走 ONEHOT_KW 的 dim1=1.0（即 A）；"宠物"/"喵星人" 走下方受控向量（B/C）。
    CAT_DIMS = (1, 7, 8)
    CAT_KW = {
        "宠物":   [0.75, 0.661, 0.0],    # B：sim(A,B)=0.75
        "喵星人": [0.75, 0.286, 0.596],  # C：sim(A,C)=0.75, sim(B,C)=0.75
    }

    def _vec(self, text: str):
        v = [0.0] * self.DIM
        for kw, dim in self.ONEHOT_KW.items():
            if kw in text:
                v[dim] = 1.0
        for kw, vals in self.CAT_KW.items():
            if kw in text:
                for d, val in zip(self.CAT_DIMS, vals):
                    v[d] = val
        return np.array(v)

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


# (输入文本, 应抽取的记忆)。设计覆盖全部事件类型；猫簇(猫/宠物/喵星人)两两相似 0.75
# → 非近义、不被去重，且能触发 reorg/core 演示（见文件头阈值说明）。
SCRIPT = [
    ("用户喜欢打羽毛球", ["用户喜欢打羽毛球"]),        # M1 写入
    ("这周又去打羽毛球了", []),                         # M1 外部验证（同关键词 cosine=1.0 只触发 EV）
    ("周末也去打羽毛球", []),
    ("每天打羽毛球", []),                               # M1 persist=3.0 → 升巩固层
    ("用户特别爱打羽毛球", ["用户喜欢打羽毛球"]),        # 近义重复 M1 → 去重跳过 (memory_dedup_skip)
    ("用户养了一只猫", ["用户养了一只猫"]),             # M2 写入 (A)
    ("用户很爱猫", []),
    ("猫是用户最好的朋友", []),
    ("猫今天又粘人了", []),                             # M2 persist=3.0 → 升巩固层
    ("用户养了一只宠物", ["用户养了一只宠物"]),         # M2b 写入 (B, sim 猫=0.75, 非近义→不去重)
    ("宠物很可爱", []),
    ("宠物喜欢趴腿上", []),
    ("宠物太粘人了", []),                              # M2b persist=3.0 → 升巩固层; reorg vs M2(0.75≥0.70)→trigger=1
    ("用户有一只喵星人", ["用户有一只喵星人"]),         # M3 写入 (C, sim 猫=0.75, sim 宠物=0.75)
    ("喵星人很乖", []),
    ("喵星人喜欢睡觉", []),
    ("喵星人早上会叫", []),                            # M3 persist=3.0 → 升巩固层; reorg vs M2+M2b → trigger=2 ≥2 → 升慢层(core)
    ("用户喜欢喝咖啡", ["用户喜欢喝咖啡"]),             # M4 写入(无验证)
    ("用户喜欢游泳", ["用户喜欢游泳"]),                 # M5 写入
    ("用户喜欢读书", ["用户喜欢读书"]),                 # M6 写入
    ("用户喜欢旅行", ["用户喜欢旅行"]),                 # M7 写入
    ("用户还喜欢爬山", ["用户还喜欢爬山"]),             # M8 写入 → 触发 working 淘汰
]
# 重组关系队列：M2b 升层时 1 次(与M2)，M3 升层时 2 次(与M2、M2b)，共 3 次"合并"
RELATIONS = ["合并", "合并", "合并"]


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
