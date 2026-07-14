#!/usr/bin/env python3
"""真实语料喂入驱动：用真实 LLM + 真实嵌入模型跑一段语料，产出事件日志。

与 tools/dev_simulate.py 的区别：
- dev_simulate 用 FakeEmbedding + ScriptedLLM（合成数据，仅验证管道）；
- 本脚本用**真实 EmbeddingEngine + create_llm_client()（读 .env 的 Gemini/DeepSeek 等）**，
  产生的是真实语义下的动力学日志，可直接喂给 tools/analyze_trajectory.py 分析。

原则 B 边界：本脚本**只喂入你提供的语料**（实验者控制的外部输入），绝不自行生成
输入来"检验自己"——系统生成内容永远不计入 external_validation（由 pipeline 内部
system_guided=False 保证）。

用法：
    # 先把 Gemini key 写进 .env，设 USE_MOCK_LLM=false
    uv run python tools/run_corpus.py corpus.txt
    uv run python tools/run_corpus.py corpus.jsonl --log logs/real_events.jsonl
    # Phase 3 对照：同语料跑两遍，仅切迁移策略
    uv run python tools/run_corpus.py corpus.txt --strategy persistence
    uv run python tools/run_corpus.py corpus.txt --strategy frequency --log logs/freq_events.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ananke.config import Config
from ananke.embedding import EmbeddingEngine
from ananke.llm_client import create_llm_client
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline


def load_corpus(path: Path) -> list[str]:
    """支持 .jsonl（每行含 input/text/user 字段）或纯文本（每行一条输入）。"""
    text = path.read_text(encoding="utf-8")
    inputs: list[str] = []
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            val = obj.get("input") or obj.get("text") or obj.get("user") or obj.get("content")
            if isinstance(val, str) and val.strip():
                inputs.append(val.strip())
    else:
        for line in text.splitlines():
            line = line.strip()
            if line:
                inputs.append(line)
    return inputs


def main() -> None:
    ap = argparse.ArgumentParser(description="用真实 LLM + 真实嵌入跑语料，产出事件日志")
    ap.add_argument("corpus", help="语料文件：.txt(每行一条) 或 .jsonl(含 input 字段)")
    ap.add_argument("--log", default="logs/events.jsonl", help="事件日志输出路径")
    ap.add_argument("--data", default="data", help="记忆存储目录")
    ap.add_argument(
        "--strategy",
        default=None,
        choices=["persistence", "frequency"],
        help="覆盖迁移策略（Phase 3 对照实验用；默认用 Config.WORKING_PROMOTION_STRATEGY）",
    )
    args = ap.parse_args()

    if args.strategy:
        Config.WORKING_PROMOTION_STRATEGY = args.strategy

    corpus = load_corpus(Path(args.corpus))
    if not corpus:
        print(f"[warn] 语料 {args.corpus} 为空或无有效输入。")
        return

    # 真实组件
    embedding = EmbeddingEngine(Config.EMBEDDING_MODEL)
    llm = create_llm_client()
    pipeline = MemoryPipeline(
        MemoryStore(args.data),
        embedding,
        llm,
        EventLogger(args.log),
    )

    print(f"[info] 真实 LLM 模式: {type(llm).__name__} | 嵌入模型: {Config.EMBEDDING_MODEL}")
    print(f"[info] 迁移策略: {Config.WORKING_PROMOTION_STRATEGY} | 语料条数: {len(corpus)}")
    print(f"[info] 日志 → {args.log}\n")

    for i, line in enumerate(corpus, 1):
        result = pipeline.process(line)
        n_write = len(result["written"])
        n_consol = len(result["consolidated"])
        n_core = len(result["core"])
        print(f"[{i:>3}/{len(corpus)}] +{n_write}记忆 | 升巩固层 {n_consol} | 升慢层 {n_core} | {line[:30]}")

    print(f"\n[done] 完成。分析: uv run python tools/analyze_trajectory.py --log {args.log} --data {args.data}")


if __name__ == "__main__":
    main()
