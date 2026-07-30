#!/usr/bin/env python3
"""v0.2 证据命中评估（协议 v4 §5 评估独立性）。

用**不同家族** LLM 主裁判（评判端，Config.EVAL_LLM_*）独立判定：
    「记忆 M 是否包含支持标准事实 F、从而正确回答问题 Q 所需的事实？」
仅允许回复：包含 / 部分 / 不包含。

为什么需要独立评判端（v4 §5 核心纪律）：
    驱动端 = embedding + Gemini 提取，已经决定了「哪些记忆被留下来」。
    若再用同一套 embedding/LLM 度量「记忆好不好」，就形成了
    **驱动-评判度量循环**（self-fulfilling），结论不可信。
    因此评判端必须是不同家族 LLM，且**禁止出现嵌入模型**。

证据命中率（evidence hit rate）定义：
    对每个记忆 M，取其在所有探针问题上判定的最大值（包含=1.0 / 部分=EVAL_PARTIAL_CREDIT / 不包含=0）。
    某记忆「被证据命中」 ⇔ 其最大命中 > 0（至少部分包含某外部问题答案所需事实）。
    证据命中率 = 被命中记忆数 / 有有效 judge 判定的记忆数；全失败记忆标记 unscored，
    仍保留在 P/F 升层集合但退出命中率分母。

输入：
    --data      一次运行产出的记忆存储目录（CORE/CONSOLIDATED 层记忆）
    --probes    探针文件（.jsonl，每行 {"question": "...", "fact": "..."}）；fact 是评判依据
    --strategy  标注用（persistence / frequency），仅写入结果文件
输出：
    1) stdout 摘要：评估记忆数、证据命中率、逐记忆明细。
    2) logs/eval_<tag>.json：机读结果，供 divergence_analysis 汇总。

诚实边界（v4 §5）：本工具只产出「评判端对记忆的外部一致性判定」，不判定理论。
    真实评估需配置 EVAL_LLM_API_KEY（不同家族）；mock 仅可通过 --allow-mock 显式用于冒烟。

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
_VERDICT_PATTERN = re.compile(r"不包含|部分|包含")


def load_probes(path: Path) -> list[dict]:
    probes: list[dict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        q = obj.get("question") or obj.get("q") or obj.get("text")
        if q:
            reference_fact = (
                obj.get("reference_fact")
                or obj.get("fact")
                or obj.get("answer")
            )
            if not isinstance(reference_fact, str) or not reference_fact.strip():
                raise ValueError(
                    f"{path}:{line_number} missing required reference_fact/fact"
                )
            probes.append(
                {
                    "question": q.strip(),
                    "reference_fact": reference_fact.strip(),
                }
            )
    return probes


def parse_verdict(text: str) -> float:
    """Parse exactly one verdict label without substring collisions."""
    labels = set(_VERDICT_PATTERN.findall(text))
    if not labels:
        raise ValueError(f"unparseable judge verdict: {text!r}")
    if len(labels) != 1:
        raise ValueError(f"ambiguous judge verdict: {text!r}")
    return _LABEL_SCORE[labels.pop()]


def judge_single(
    judge,
    content: str,
    question: str,
    reference_fact: str,
) -> float | None:
    prompt = (
        f"记忆={content}。\n"
        f"问题={question}。\n"
        f"标准事实={reference_fact}。\n"
        f"请判定：该记忆是否包含支持标准事实、从而正确回答该问题所需的事实？\n"
        f"仅回复以下之一，不要解释：包含 / 部分 / 不包含"
    )
    try:
        reply = judge.call_llm(prompt)
        return parse_verdict(reply)
    except Exception as e:  # 单条失败剔除并计数，不折算为不命中
        print(f"    [warn] 评判失败: {e}")
        return None


def evaluate(data_dir: str, probes: list[dict], judge) -> dict:
    store = MemoryStore(data_dir)
    # 仅评估升层记忆（CORE/CONSOLIDATED）；MemoryStore 无 get_all_memories，
    # 用两层 getter 拼合（原 get_all_memories 调用会 AttributeError 崩溃——P0-B 修复）。
    memories = store.get_core_memories() + store.get_consolidated_memories()
    results: list[dict] = []
    judge_failures = 0
    for mem in memories:
        per_probe = [
            judge_single(
                judge,
                mem.content,
                p["question"],
                p["reference_fact"],
            )
            for p in probes
        ]
        judge_failures += sum(score is None for score in per_probe)
        valid_scores = [score for score in per_probe if score is not None]
        max_hit = max(valid_scores) if valid_scores else None
        results.append({
            "memory_id": mem.id,
            "content": mem.content,
            "layer": mem.layer.value.upper(),
            "ev": mem.external_validation,
            "per_probe_scores": per_probe,
            "max_hit": max_hit,
            "evidence_backed": (max_hit > 0) if max_hit is not None else None,
            "status": "scored" if max_hit is not None else "unscored",
        })
    planned_calls = len(memories) * len(probes)
    failure_rate = judge_failures / planned_calls if planned_calls else 0.0
    scored = [result for result in results if result["status"] == "scored"]
    n_backed = sum(result["evidence_backed"] is True for result in scored)
    hit_rate = (n_backed / len(scored)) if scored else None
    return {
        "n_memories": len(results),
        "n_scored_memories": len(scored),
        "n_unscored_memories": len(results) - len(scored),
        "n_evidence_backed": n_backed,
        "hit_rate": hit_rate,
        "planned_calls": planned_calls,
        "judge_failures": judge_failures,
        "judge_failure_rate": failure_rate,
        "evaluation_valid": failure_rate <= 0.05,
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="v0.2 证据命中评估（协议 v4 §5，独立评判端）")
    ap.add_argument("--data", required=True, help="记忆存储目录（CORE/CONSOLIDATED 层）")
    ap.add_argument("--probes", required=True, help="探针文件 .jsonl（question/fact）")
    ap.add_argument("--strategy", default="persistence", help="标注用策略名")
    ap.add_argument("--tag", default="eval", help="输出文件标签")
    ap.add_argument("--out", default="logs", help="JSON 结果输出目录")
    ap.add_argument(
        "--allow-mock",
        action="store_true",
        help="仅冒烟：显式允许 MockEvaluationJudge；正式评估禁止使用",
    )
    args = ap.parse_args()

    try:
        probes = load_probes(Path(args.probes))
    except (ValueError, json.JSONDecodeError) as error:
        print(f"[abort] 探针契约无效: {error}")
        raise SystemExit(2) from error
    if not probes:
        print("[warn] 探针文件为空，无法评估。")
        return

    try:
        judge = create_eval_llm_client(allow_mock=args.allow_mock)
    except RuntimeError as error:
        print(f"[abort] {error}")
        raise SystemExit(2) from error
    print(f"[info] 评判端: {type(judge).__name__} | 探针数: {len(probes)} | 策略: {args.strategy}")

    report = evaluate(args.data, probes, judge)
    results = report["results"]
    if not results:
        print(f"[warn] {args.data} 中无 CORE/CONSOLIDATED 记忆可评估。")
        return

    print("=" * 64)
    print(f"v0.2 证据命中评估 — 策略 {args.strategy}（仅描述，不判定理论）")
    print("=" * 64)
    hit_rate_text = (
        f"{report['hit_rate']:.3f}"
        if report["hit_rate"] is not None
        else "unscored"
    )
    print(
        f"记忆数: {report['n_memories']} | 有效评分: {report['n_scored_memories']} | "
        f"未评分: {report['n_unscored_memories']} | 证据命中率: {hit_rate_text}"
    )
    print(
        f"judge 失败: {report['judge_failures']}/{report['planned_calls']} "
        f"({report['judge_failure_rate']:.1%}) | "
        f"评估有效: {report['evaluation_valid']}"
    )
    for r in results:
        flag = "?" if r["status"] == "unscored" else ("✓" if r["evidence_backed"] else "✗")
        max_text = "n/a" if r["max_hit"] is None else f"{r['max_hit']:.2f}"
        print(f"  {flag} [{r['layer']}] EV={r['ev']} max={max_text}  {r['content'][:40]}")
    print("=" * 64)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"eval_{args.tag}.json"
    payload = {
        "strategy": args.strategy,
        "partial_credit": Config.EVAL_PARTIAL_CREDIT,
        **report,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 机读结果 → {path}")
    if not report["evaluation_valid"]:
        print("[abort] judge_failure_rate > 5%，本次评估无效。")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
