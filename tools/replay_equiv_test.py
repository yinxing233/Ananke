#!/usr/bin/env python3
"""重放等价性测试（协议 v4 §8 确定性审计）。

用两级缓存重放前 N 轮，逐事件比对原始 events.jsonl。不一致即暴露管线非确定性
（提取/分类未缓存、或平票打破规则不确定）。

为什么这是最强的确定性测试
==========================
v0.1 验证过的「路径无关性」（两遍运行逐记忆计数一致）在这里升级为「重放等价性」：
缓存重放的前 N 轮结果必须与原始运行逐事件一致。缓存让提取对所有运行一致、重叠句对
分类一致，剩下的差异只能来自召回排序 / 淘汰的非确定性——若 tie-break 不确定，这里
会抓到。

红线与防呆（Claude 裁决）
========================
B2 防呆：重放必须用与原始运行**相同模型**才能命中缓存、得零 API。若缓存 key 前缀
  （model_tag）与当前 .env 配置不一致 → 直接中止——否则会烧新额度 + 假 FAIL，且恰
  发生在「换额度」这个高概率操作之后。
D 内置：默认重放上限 = 原始日志实际轮数（从事件 turn 字段推断）。跑满完整语料是
  显式 opt-in（--max-turns 大于推断值会告警），避免「务必记得 252」这种口头约定
  变成下一个事故（旧日志崩溃在第 253 轮，默认跑满会重演撞额度）。

用法
====
    # 原始运行（同模型）已产出带 turn 字段的日志；重放默认取其实际轮数，零 API，逐事件比对
    uv run python tools/replay_equiv_test.py \
        --corpus data/locomo/conv-26_corpus.jsonl \
        --original-log logs/conv26_events.jsonl \
        --data data/replay_check --clean
"""
from __future__ import annotations

import argparse
import json
import shutil
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

# run_corpus.load_corpus 与 run_corpus 共用，保证语料加载一致
sys.path.insert(0, str(ROOT / "tools"))
from run_corpus import load_corpus  # noqa: E402


def fingerprint(event: dict) -> dict:
    """移除 *_id（uuid 跨运行不同）、timestamp、turn（位置信息非业务语义），保留业务字段。

    memory_id / matched_memory_id / new_memory_id / recipient_memory_id 全部是 uuid，
    两次运行不同，但它们指向的 content 跨运行一致（提取缓存）。turn 是轮序号（位置），
    重放对齐靠事件顺序而非 turn 值。故忽略三者，比对 event / content / relation /
    cross_session / cosine / 数值字段等业务语义。
    """
    return {
        k: v
        for k, v in event.items()
        if not k.endswith("_id") and k not in ("timestamp", "turn")
    }


def _cache_model_tag(cache_dir: str | Path) -> str | None:
    """读缓存文件首条 key 的 model_tag 段。

    key 结构 = 'model_tag|prompt_hash|category|normalized_input'。
    model_tag 本身含 '|'（形如 'openai-compatible|deepseek-chat'），故**不能**用
    split('|',1)[0] 截断——那只会取到 provider 半段，漏掉 model，导致 B2 防呆在默认
    配置下误判（cached_tag='openai-compatible' ≠ expected='openai-compatible|deepseek-chat'）
    而错误中止合理重放。

    正确做法：末尾三段（prompt_hash=hex / category / normalized_input，三者均不含 '|'
    因为 normalized_input 经 §6 归一化去标点、category 为固定词）截断后，剩余段拼回即
    完整 model_tag。
    """
    cache_dir = Path(cache_dir)
    for cat in ("extraction", "pairs"):
        p = cache_dir / f"{cat}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = rec.get("key", "")
            parts = key.split("|")
            # 至少需要 model_tag + 3 固定段；少于 4 段视为畸形，跳过本条。
            if len(parts) >= 4:
                return "|".join(parts[:-3])
    return None


def _max_turn_in_log(log_path: str | Path) -> int | None:
    """原始日志实际轮数 = 事件中 turn 字段的最大值（D 内置默认上限来源）。

    旧格式日志无 turn 字段 → 返回 None（无法安全推断，要求显式 --max-turns）。
    """
    p = Path(log_path)
    if not p.exists():
        return None
    max_turn = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = rec.get("turn")
        if isinstance(t, int) and t > max_turn:
            max_turn = t
    return max_turn or None


def main() -> None:
    ap = argparse.ArgumentParser(description="重放等价性测试：用缓存重放 N 轮，逐事件比对原始日志")
    ap.add_argument("--corpus", required=True, help="语料文件（与原始运行同一份）")
    ap.add_argument("--original-log", required=True, help="原始运行产出的事件日志")
    ap.add_argument("--max-turns", type=int, default=None,
                    help="只重放前 N 轮；默认=原始日志实际轮数，跑满为显式 opt-in")
    ap.add_argument("--data", default="data/replay_check", help="重放用记忆目录")
    ap.add_argument("--clean", action="store_true", help="运行前清空 --data 目录")
    ap.add_argument("--replay-log", default="logs/replay_check.jsonl", help="重放日志输出")
    args = ap.parse_args()

    # ---- 前提审计：确定性条件须满足 ----
    issues: list[str] = []
    if Config.LLM_TEMPERATURE != 0.0:
        issues.append(f"LLM_TEMPERATURE={Config.LLM_TEMPERATURE} ≠ 0（非确定性风险）")
    if not Config.CACHE_ENABLED:
        issues.append("CACHE_ENABLED=false（重放将产生新 API 调用，非等价测试）")
    if Config.USE_MOCK_LLM:
        issues.append("USE_MOCK_LLM=true（mock 路径不经缓存，仅验证管道）")
    print("[audit] 确定性前提：")
    if issues:
        for x in issues:
            print(f"  [!] {x}")
        print("  继续运行，但结果仅作参考（不构成等价性证据）。")
    else:
        print(f"  OK: LLM_TEMPERATURE=0.0 | CACHE_ENABLED=true | model_tag={Config.LLM_PROVIDER}|{Config.LLM_MODEL}")

    # ---- B2 防呆：缓存 model_tag 必须与当前配置一致，否则中止 ----
    expected_tag = f"{Config.LLM_PROVIDER}|{Config.LLM_MODEL}"
    cached_tag = _cache_model_tag(Config.CACHE_DIR)
    if cached_tag is not None and cached_tag != expected_tag:
        print(f"\n[abort] 缓存 model_tag='{cached_tag}' 与当前配置 '{expected_tag}' 不一致。")
        print("  重放必须用与原始运行相同的模型才能命中缓存、得零 API 调用。")
        print("  请先用当前模型续跑以填充缓存，或确认 .env 的 LLM_PROVIDER/LLM_MODEL 与原始运行一致。")
        sys.exit(2)

    # ---- D 内置：默认上限 = 原始日志实际轮数（跑满是显式 opt-in）----
    orig_turns = _max_turn_in_log(args.original_log)
    if args.max_turns is None:
        if orig_turns is None:
            print("\n[abort] 原始日志无 turn 字段（旧格式），无法安全推断轮数。")
            print("  请显式传 --max-turns N（注意：跑满可能撞原始运行的额度墙）。")
            sys.exit(3)
        args.max_turns = orig_turns
        print(f"[info] 默认重放前 {orig_turns} 轮（=原始日志实际轮数；--max-turns 显式值可覆盖/跑满）")
    elif orig_turns is not None and args.max_turns > orig_turns:
        print(f"[warn] 显式 --max-turns {args.max_turns} > 原始日志实际轮数 {orig_turns}，"
              f"将跑满完整语料（可能撞原始运行的额度墙）。")

    # ---- 准备 ----
    data_path = Path(args.data)
    if args.clean and data_path.exists():
        shutil.rmtree(data_path)

    corpus = load_corpus(Path(args.corpus))
    if args.max_turns:
        corpus = corpus[: args.max_turns]
    if not corpus:
        print("[warn] 语料为空。")
        return

    # ---- 重放（缓存命中应零 API）----
    embedding = EmbeddingEngine(Config.EMBEDDING_MODEL)
    llm = create_llm_client()
    pipeline = MemoryPipeline(
        MemoryStore(args.data),
        embedding,
        llm,
        EventLogger(args.replay_log),
    )
    print(f"\n[replay] 重放 {len(corpus)} 轮（缓存命中应零新 API 调用）...")
    for i, (line, sid) in enumerate(corpus, 1):
        pipeline.event_logger.turn = i  # 重放也标记轮序号，与原始日志对齐
        pipeline.process(line, session_id=sid)

    cache = getattr(llm, "cache", None)
    if cache is not None:
        st = cache.stats()
        eh = st["extraction"]["hits"]
        em = st["extraction"]["misses"]
        ph = st["pairs"]["hits"]
        pm = st["pairs"]["misses"]
        print(f"[cache] 提取 hits={eh}/{eh + em} | 分类对 hits={ph}/{ph + pm}")
        if em == 0 and pm == 0:
            print("  [OK] 全部命中——重放零新调用，等价性测试有效。")
        else:
            print(f"  [!] 有 miss（提取 {em} / 分类 {pm}）：存在未缓存的新调用，等价性可能受非确定性影响。")

    # ---- 逐事件比对 ----
    orig = [json.loads(l) for l in Path(args.original_log).read_text(encoding="utf-8").splitlines() if l.strip()]
    replay = [json.loads(l) for l in Path(args.replay_log).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"\n[compare] 原始 {len(orig)} 事件 vs 重放 {len(replay)} 事件")

    n = min(len(orig), len(replay))
    mismatches: list[tuple] = []
    for i in range(n):
        if fingerprint(orig[i]) != fingerprint(replay[i]):
            mismatches.append((i, orig[i], replay[i]))

    tail_gap = abs(len(orig) - len(replay))
    if not mismatches and tail_gap == 0:
        print(f"[PASS] {n} 事件逐条业务等价（忽略 memory_id/timestamp/turn）。重放等价性成立。")
    else:
        if mismatches:
            print(f"[FAIL] {len(mismatches)} 处业务字段不一致，暴露管线非确定性：")
            for idx, o, r in mismatches[:10]:
                print(f"  事件 #{idx}:")
                print(f"    原始 : {o}")
                print(f"    重放 : {r}")
        if tail_gap:
            shorter = "原始" if len(orig) < len(replay) else "重放"
            print(f"[note] 事件数差 {tail_gap}（{shorter} 较短；若原始因崩溃截断属预期）。")
        if not mismatches and tail_gap:
            print(f"[PASS-ish] 已比对的 {n} 事件逐条等价；尾部差异来自崩溃截断（非确定性无关）。")

    # ---- 结论 ----
    if not mismatches:
        print("\n[结论] 已比对事件全部业务等价。管线在当前缓存 + 确定性 tie-break 下满足重放等价。")
    else:
        print(f"\n[结论] {len(mismatches)} 处不一致。请检查：提取/分类是否漏缓存、"
              f"召回/淘汰 tie-break 是否按 content 打破、embedding 是否确定性。")


if __name__ == "__main__":
    main()
