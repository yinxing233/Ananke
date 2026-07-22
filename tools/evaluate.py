#!/usr/bin/env python3
"""v0.2 证据命中评估（协议 v4 §5 评估独立性）。

用**不同家族** LLM 主裁判（评判端，Config.EVAL_LLM_*）独立判定：
    「记忆 M 是否包含回答问题 Q 所需的事实？」
仅允许回复：包含 / 部分 / 不包含。

为什么需要独立评判端（v4 §5 核心纪律）：
    驱动端 = embedding + Gemini 提取，已经决定了「哪些记忆被留下来」。
    若再用同一套 embedding/LLM 度量「记忆好不好」，就形成了
    **驱动-评判度量循环**（self-fulfilling），结论不可信。
    因此评判端必须是不同家族 LLM，且**禁止出现嵌入模型**。

证据命中率（evidence hit rate）定义：
    对每个记忆 M，取其在所有探针问题上判定的最大值（包含=1.0 / 部分=EVAL_PARTIAL_CREDIT / 不包含=0）。
    某记忆「被证据命中」 ⇔ 其最大命中 > 0（至少部分包含某外部问题答案所需事实）。
    证据命中率 = 被命中记忆数 / 评估记忆总数。

输入：
    --data      一次运行产出的记忆存储目录（CORE/CONSOLIDATED 层记忆）
    --probes    探针文件（.jsonl，每行 {"question": "...", "fact": "..."}）；fact 仅作审计参考
    --strategy  标注用（persistence / frequency），仅写入结果文件
输出：
    1) stdout 摘要：评估记忆数、证据命中率、逐记忆明细。
    2) logs/eval_<tag>.json：机读结果，供 divergence_analysis 汇总。

诚实边界（v4 §5）：本工具只产出「评判端对记忆的外部一致性判定」，不判定理论。
真实评估需配置 EVAL_LLM_API_KEY（不同家族）；USE_MOCK_LLM 下用子串匹配近似，仅供冒烟。

用法：
    uv run python tools/evaluate.py --data data/p --probes corpus_phase2_probes.jsonl --strategy persistence --tag p
    uv run python tools/evaluate.py --data data/f --probes corpus_phase2_probes.jsonl --strategy frequency   --tag f
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ananke.config import Config
from ananke.llm_client import create_eval_llm_client
from ananke.memory_store import MemoryStore

_LABEL_SCORE = {"包含": 1.0, "部分": Config.EVAL_PARTIAL_CREDIT, "不包含": 0.0}


def load_probes(path: Path) -> list[dict]:
    probes: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        q = obj.get("question") or obj.get("q") or obj.get("text")
        if q:
            probes.append({"question": q.strip(), "fact": obj.get("fact", "")})
    return probes


def parse_verdict(text: str) -> float:
    """从 LLM 回复解析 包含/部分/不包含 → 分数。鲁棒到多余字符。"""
    for label, score in _LABEL_SCORE.items():
        if label in text:
            return score
    return 0.0


def judge_single(judge, content: str, question: str) -> float:
    prompt = (
        f"记忆={content}。\n"
        f"问题={question}。\n"
        f"请判定：该记忆是否包含回答该问题所需的事实？\n"
        f"仅回复以下之一，不要解释：包含 / 部分 / 不包含"
    )
    try:
        reply = judge.call_llm(prompt)
    except Exception as e:  # 单条失败不应中断整批
        print(f"    [warn] 评判失败: {e}")
        return 0.0
    return parse_verdict(reply)


def evaluate(data_dir: str, probes: list[dict], judge) -> list[dict]:
    store = MemoryStore(data_dir)
    # 仅评估升层记忆（CORE/CONSOLIDATED）；MemoryStore 无 get_all_memories，
    # 用两层 getter 拼合（原 get_all_memories 调用会 AttributeError 崩溃——P0-B 修复）。
    memories = store.get_core_memories() + store.get_consolidated_memories()
    results: list[dict] = []
    for mem in memories:
        per_probe = [judge_single(judge, mem.content, p["question"]) for p in probes]
        max_hit = max(per_probe) if per_probe else 0.0
        results.append({
            "memory_id": mem.id,
            "content": mem.content,
            "layer": mem.layer.value.upper(),
            "ev": mem.external_validation,
            "per_probe_scores": per_probe,
            "max_hit": max_hit,
            "evidence_backed": max_hit > 0,
        })
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="v0.2 证据命中评估（协议 v4 §5，独立评判端）")
    ap.add_argument("--data", required=True, help="记忆存储目录（CORE/CONSOLIDATED 层）")
    ap.add_argument("--probes", required=True, help="探针文件 .jsonl（question/fact）")
    ap.add_argument("--strategy", default="persistence", help="标注用策略名")
    ap.add_argument("--tag", default="eval", help="输出文件标签")
    ap.add_argument("--out", default="logs", help="JSON 结果输出目录")
    args = ap.parse_args()

    probes = load_probes(Path(args.probes))
    if not probes:
        print("[warn] 探针文件为空，无法评估。")
        return

    judge = create_eval_llm_client()
    print(f"[info] 评判端: {type(judge).__name__} | 探针数: {len(probes)} | 策略: {args.strategy}")

    results = evaluate(args.data, probes, judge)
    if not results:
        print(f"[warn] {args.data} 中无 CORE/CONSOLIDATED 记忆可评估。")
        return

    n_backed = sum(1 for r in results if r["evidence_backed"])
    hit_rate = n_backed / len(results)

    print("=" * 64)
    print(f"v0.2 证据命中评估 — 策略 {args.strategy}（仅描述，不判定理论）")
    print("=" * 64)
    print(f"评估记忆数: {len(results)} | 证据命中率: {hit_rate:.3f}")
    for r in results:
        flag = "✓" if r["evidence_backed"] else "✗"
        print(f"  {flag} [{r['layer']}] EV={r['ev']} max={r['max_hit']:.2f}  {r['content'][:40]}")
    print("=" * 64)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"eval_{args.tag}.json"
    payload = {
        "strategy": args.strategy,
        "n_memories": len(results),
        "n_evidence_backed": n_backed,
        "hit_rate": hit_rate,
        "partial_credit": Config.EVAL_PARTIAL_CREDIT,
        "results": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 机读结果 → {path}")


if __name__ == "__main__":
    main()
