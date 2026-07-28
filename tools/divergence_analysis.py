#!/usr/bin/env python3
"""v0.2 分歧集分析（协议 v4 §6）——消费 evaluate.py 输出，禁止自算命中率。

**测量链纪律（PI 裁决，P1-A）**：
    conjecture 中的「evidence 命中率」≡ 评判端主裁判判定（协议 v4 §5/§6 line 170-171：
    命中 = 主裁判判「包含」或「部分」）。本工具**必须消费 tools/evaluate.py 的输出**来取
    每条记忆的 judge 命中，**自身不得计算任何命中率**。
    理由：用 EV>0（系统自产的驱动信号）当"证据命中"= 用系统自己给自己打分，正是 §5
    「驱动-评判度量循环」防线存在的唯一理由所要防的事；且它击穿在主测量量上——§0(b)
    反驳条件、推测 1、推测 2 全挂在"evidence 命中率"这个词上，若此量在冻结时仍是 EV>0，
    整个预登记结构形同虚设。
    EV>0 在本工具的**唯一合法用途** = 推测 2 机制签名检查里作**被解释项**（用 EV 把 F∖P
    分段为 EV=0 / EV>0 两个子集，再比它们的 judge 命中率），**不是评判标准**。

输入：两遍独立运行（仅 --strategy 不同）各自经 evaluate.py 产出的评判结果 JSON：
    --eval-p <logs/eval_p.json>   persistence 策略的评判输出
    --eval-f <logs/eval_f.json>   frequency  策略的评判输出
（evaluate.py 输出含每条升层记忆的 memory_id/content/layer/ev/max_hit/evidence_backed。）

输出：
  1) stdout 摘要：|P| |F| |D| Jaccard、judge 端命中率（推测 1）、机制签名（推测 2）。
  2) logs/divergence_<tag>.json：可机读结果。

统计严谨性（v4 §6 / §8）：|D| ≥ 20 才达功效下限可做二项推断；否则打印欠功效警告。
本工具只做**描述 + 提示**，不做理论判定（分析器纪律）。

用法：
    # 先跑两遍语料（仅切策略），再各跑 evaluate，最后比对
    uv run python tools/run_corpus.py corpus_phase2.jsonl --strategy persistence --data data/p --log logs/p.jsonl --clean
    uv run python tools/run_corpus.py corpus_phase2.jsonl --strategy frequency   --data data/f --log logs/f.jsonl --clean
    uv run python tools/evaluate.py --data data/p --probes corpus_phase2_probes.jsonl --strategy persistence --tag p
    uv run python tools/evaluate.py --data data/f --probes corpus_phase2_probes.jsonl --strategy frequency   --tag f
    uv run python tools/divergence_analysis.py --eval-p logs/eval_p.json --eval-f logs/eval_f.json --tag phase2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 功效下限（v4 §8）：分歧集规模达到此值才做二项推断。
POWER_FLOOR = 20


# §6 记忆同一性判据的**唯一**实现来源：ananke/text_norm.normalize。
# 此处仅做别名以保持既有内部引用（_norm）不变，绝不再复制一份（B1：双拷贝=协议
# 条款出现两个可独立漂移的实现，同 P0-A 三方矛盾病灶）。守护测试
# test_protocol_2_6_single_norm_source 钉死 cache.normalize is divergence_analysis._norm。
from ananke.text_norm import normalize as _norm


def load_eval(path: str) -> dict[str, dict]:
    """读 evaluate.py 输出 JSON，返回 {_norm(content): {...}}。

    evaluate.py 已只保留 CORE/CONSOLIDATED 升层记忆，并附 judge 端判定（max_hit /
    evidence_backed）与 ev。故升层集合 P/F 与每条记忆的 judge 命中**均来自评判端**，
    本工具不再读 MemoryStore、不再自算命中率（P1-A 测量链纪律）。
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for r in payload.get("results", []):
        out[_norm(r["content"])] = {
            "content": r["content"],
            "layer": r.get("layer", ""),
            "ev": r.get("ev", 0),
            "judge_hit": float(r.get("max_hit", 0.0)),
            "evidence_backed": bool(r.get("evidence_backed", False)),
        }
    return out


def _judge_hit_rate(items: list[dict]) -> float:
    """judge 端证据命中率 = 被 evidence_backed 的记忆占比（evidence_backed 来自评判端）。"""
    if not items:
        return float("nan")
    return sum(1 for m in items if m["evidence_backed"]) / len(items)


def analyze(persistence: dict, frequency: dict) -> dict:
    P = set(persistence)
    F = set(frequency)
    D = (P - F) | (F - P)          # 分歧集（对称差）
    only_P = P - F                 # 仅 persistence 升层 (P∖F)
    only_F = F - P                 # 仅 frequency 升层 (F∖P)
    union = P | F
    inter = P & F
    jaccard = (len(inter) / len(union)) if union else float("nan")

    # ---- 推测 1（主推测）：judge 端 evidence 命中率，P∖F vs F∖P ----
    # 命中定义 = 评判端 evidence_backed（§6 line 170-171）。反驳条件：h_onlyP ≤ h_onlyF。
    items_only_P = [persistence[m] for m in only_P]
    items_only_F = [frequency[m] for m in only_F]
    h_only_P = _judge_hit_rate(items_only_P)
    h_only_F = _judge_hit_rate(items_only_F)
    # 整体（上下文，非反驳量）
    h_P = _judge_hit_rate([persistence[m] for m in P])
    h_F = _judge_hit_rate([frequency[m] for m in F])

    # ---- 推测 2（机制签名）：F∖P 用 EV 分段（EV=被解释项，非评判标准），比 judge 命中率 ----
    only_F_ev0 = [frequency[m] for m in only_F if frequency[m]["ev"] == 0]
    only_F_evpos = [frequency[m] for m in only_F if frequency[m]["ev"] > 0]
    enrichment_ev0 = (len(only_F_ev0) / len(only_F)) if only_F else float("nan")
    h_onlyF_ev0 = _judge_hit_rate(only_F_ev0)
    h_onlyF_evpos = _judge_hit_rate(only_F_evpos)
    # 预测：F∖P 富集 EV=0，且 EV=0 子集 judge 命中率 < EV>0 子集

    underpowered = len(D) < POWER_FLOOR
    return {
        "n_promoted_P": len(P),
        "n_promoted_F": len(F),
        "n_divergence_D": len(D),
        "n_only_P": len(only_P),
        "n_only_F": len(only_F),
        "jaccard": jaccard,
        # 推测 1（judge 端，主测量）
        "hit_rate_onlyP_judge": h_only_P,
        "hit_rate_onlyF_judge": h_only_F,
        "hit_rate_P_judge": h_P,
        "hit_rate_F_judge": h_F,
        "conjecture1_held": (not (only_P and only_F)) or (h_only_P > h_only_F),
        # 推测 2（机制签名；EV 仅作分段被解释项）
        "signature_onlyF_ev0_fraction": enrichment_ev0,
        "signature_onlyF_ev0_judge_hit": h_onlyF_ev0,
        "signature_onlyF_evpos_judge_hit": h_onlyF_evpos,
        "conjecture2_held": (len(only_F_ev0) > 0 and len(only_F_evpos) > 0
                             and h_onlyF_ev0 < h_onlyF_evpos),
        "underpowered": underpowered,
        "power_floor": POWER_FLOOR,
        "only_P": [persistence[m]["content"] for m in only_P],
        "only_F": [frequency[m]["content"] for m in only_F],
    }


def _fmt(x: float) -> str:
    return "nan" if x != x else f"{x:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="v0.2 分歧集分析（协议 v4 §6，消费 evaluate 输出）")
    ap.add_argument("--eval-p", required=True, help="persistence 策略的 evaluate.py 输出 JSON")
    ap.add_argument("--eval-f", required=True, help="frequency  策略的 evaluate.py 输出 JSON")
    ap.add_argument("--tag", default="phase2", help="输出文件标签")
    ap.add_argument("--out", default="logs", help="JSON 结果输出目录")
    args = ap.parse_args()

    P = load_eval(args.eval_p)
    F = load_eval(args.eval_f)
    if not P and not F:
        print("[warn] 两遍 evaluate 输出均无升层记忆，无法比对。")
        print("       请确认已跑通两遍 run_corpus + evaluate，且仅 --strategy 不同。")
        return

    res = analyze(P, F)

    print("=" * 64)
    print("v0.2 分歧集分析 (Divergence Analysis) — 仅描述，不判定理论")
    print("测量链：evidence 命中率 = 评判端（消费 evaluate.py），EV>0 仅用于推测2分段")
    print("=" * 64)
    print(f"升层集合规模:  P(persistence)={res['n_promoted_P']}  F(frequency)={res['n_promoted_F']}"
          f"  Jaccard={_fmt(res['jaccard'])}")
    print(f"分歧集 |D|   = {res['n_divergence_D']}   (仅P∖F={res['n_only_P']}, 仅F∖P={res['n_only_F']})")
    print("-" * 64)
    print("[推测1·主] judge 端 evidence 命中率（反驳条件：h_onlyP ≤ h_onlyF → 反驳）")
    print(f"  仅P∖F={_fmt(res['hit_rate_onlyP_judge'])}  仅F∖P={_fmt(res['hit_rate_onlyF_judge'])}"
          f"  | 整体 P={_fmt(res['hit_rate_P_judge'])} F={_fmt(res['hit_rate_F_judge'])}")
    print(f"  → 推测1 {'成立(探索性)' if res['conjecture1_held'] else '不成立'}"
          f"（仅当两侧独有集均非空时才有意义）")
    print("-" * 64)
    print("[推测2·机制签名] F∖P 按 EV 分段（EV=被解释项），比 judge 命中率")
    print(f"  F∖P 中 EV=0 占比={_fmt(res['signature_onlyF_ev0_fraction'])} (理论预测→高)")
    print(f"  F∖P 中 EV=0 子集 judge命中={_fmt(res['signature_onlyF_ev0_judge_hit'])}"
          f"  vs  EV>0 子集 judge命中={_fmt(res['signature_onlyF_evpos_judge_hit'])} (预测 前者<后者)")
    print(f"  → 推测2 {'成立(探索性)' if res['conjecture2_held'] else '不成立/不可判'}")
    if res["underpowered"]:
        print("-" * 64)
        print(f"[!] 欠功效: |D|={res['n_divergence_D']} < 下限 {POWER_FLOOR}。")
        print("    当前结论**不可做二项推断**。建议：扩大语料/session 数至 |D|≥20；")
        print("    或执行阈值 sweep 预案，在 R_RECALL 网格上重估 |D| 稳定性。")
    else:
        print("-" * 64)
        print(f"[ok] |D|={res['n_divergence_D']} ≥ 功效下限 {POWER_FLOOR}，可做二项推断。")
    if res["only_P"]:
        print(f"\n仅 persistence 升层 P∖F（应富集 judge 命中）:")
        for c in res["only_P"]:
            print(f"    · {c}")
    if res["only_F"]:
        print(f"\n仅 frequency 升层 F∖P（应富集 EV=0 / judge 未命中）:")
        for c in res["only_F"]:
            print(f"    · {c}")
    print("=" * 64)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"divergence_{args.tag}.json"
    # NaN 非合法 JSON，递归转 None（缺值/空集时命中率为 nan）
    import math
    def _sanitize(o):
        if isinstance(o, float) and math.isnan(o):
            return None
        if isinstance(o, dict):
            return {k: _sanitize(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_sanitize(v) for v in o]
        return o
    path.write_text(json.dumps(_sanitize(res), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] 机读结果 → {path}")


if __name__ == "__main__":
    main()
