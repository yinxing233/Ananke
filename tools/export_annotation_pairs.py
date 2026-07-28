#!/usr/bin/env python3
"""从两级缓存导出「关系分类标注对」——供人工标注 + 后续方案甲/乙准确率拍板。

研究用途（协议 v4 §2.2 / plan/v0.2_recall_classification.md:49）：
    关系分类器最终在「本地 NLI cross-encoder（方案甲）vs LLM 五选一（方案乙）」
    之间，用 **50 对人工标注准确率**拍板。本工具产出这 50 对的标注模板：
      - 每对含 (new_memory, existing_memory) 与方案乙(LLM 五选一)的预测标签；
      - 人工填 human_label 列即得金标准；
      - 后续分别算方案甲 / 方案乙 vs 人工的准确率，高者胜出。

数据源 = cache/pairs.jsonl（分类对缓存，协议 v4 §8）：
    每行 {"key": "<model_tag>|<hash>|pairs|<norm_new>||<norm_existing>", "value": "<label>"}
    key 末段 normalized_input 用 "||" 分隔两段归一化记忆，可还原 (new, existing)。

分层（默认 relation 均衡）：
    5 类关系在真实语料上频率极不均衡（unrelated 占多数，contradict/mergeable
    稀少但理论最关键）。纯随机抽 50 几乎全是不相关，无法检验稀有类的分类质量。
    故默认按 PREDICTED 标签均衡取样，确保每类都被人工覆盖；某类不足配额则取尽并
    把余量结转给仍有余量的类。亦可 --strata proportional 按真实分布比例取样。

key 解析陷阱（务必用 rpartition + rsplit，不能用整体 split("|")）：
    - 外层段分隔符是 "|"，但 model_tag 本身含 "|"（如 openai-compatible|deepseek-chat），
      且两段记忆之间用 "||" 分隔。若整体按 "|" 切，嵌入的 "||" 会塌成一个空段，
      导致 norm_input 解析错位。故：先 rpartition("||") 取末段为 existing、其余为 head；
      再 head.rsplit("|", 2) 得 [model_tag含|, category, norm_new]。
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELATION_LABELS = ["duplicate", "contradict", "mergeable", "related", "unrelated"]


def parse_pairs_cache(cache_dir: Path) -> tuple[list[dict], int]:
    """从 pairs.jsonl 解析出 [(new_norm, existing_norm, label), ...]。

    返回 (pairs, skipped)。skipped = 无法解析（结构不合法 / 非 pairs 类 / 缺 "||"）的行数。
    key 解析见模块 docstring：rpartition("||") + rsplit("|", 2)。
    """
    p = cache_dir / "pairs.jsonl"
    if not p.exists():
        return [], 0
    pairs: list[dict] = []
    skipped = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        key = rec.get("key", "")
        label = rec.get("value", "")
        # 末段 "||" 分隔两段记忆；用 rpartition 取最后一个 "||"（norm_existing 不含 "||"）。
        head, sep, existing_norm = key.rpartition("||")
        if not sep:
            skipped += 1
            continue
        # head = "<model_tag含|>|<hash>|pairs|<norm_new>"；从右切 2 刀得 [model_tag, category, norm_new]。
        prefix, cat_sep, norm_new = head.rsplit("|", 2)
        if cat_sep != "pairs":
            skipped += 1
            continue
        if label not in RELATION_LABELS:
            # 已知 5 类之外（理论上不应发生）；跳过取样以保持分层纯净，仅计入 skipped。
            skipped += 1
            continue
        pairs.append({
            "new_memory": norm_new,
            "existing_memory": existing_norm,
            "model_predicted": label,
        })
    return pairs, skipped


def _sample_balanced(by_label: dict[str, list[dict]], n: int) -> list[dict]:
    """均衡取样：每步把名额给当前配额最小（仍有余量）的类 → 计数尽量均匀，受可用量封顶。"""
    quota = {lab: 0 for lab in RELATION_LABELS}
    remaining_cap = {lab: len(by_label[lab]) for lab in RELATION_LABELS}
    for _ in range(n):
        cand = [lab for lab in RELATION_LABELS if remaining_cap[lab] > 0]
        if not cand:
            break
        # 配额最小者优先（均衡）；平票按标签名定序保证确定性。
        lab = min(cand, key=lambda l: (quota[l], l))
        quota[lab] += 1
        remaining_cap[lab] -= 1
    selected: list[dict] = []
    for lab in RELATION_LABELS:
        selected.extend(by_label[lab][: quota[lab]])
    return selected


def _sample_proportional(by_label: dict[str, list[dict]], n: int) -> list[dict]:
    """按比例取样：配额 ≈ n × 该类可用量 / 总可用量，再修正为恰等于 n。"""
    total = sum(len(v) for v in by_label.values()) or 1
    quota = {
        lab: min(len(by_label[lab]), round(n * len(by_label[lab]) / total))
        for lab in RELATION_LABELS
    }
    diff = n - sum(quota.values())
    # diff>0：从仍有余量的类补；diff<0：从配额>0 的类减。
    if diff > 0:
        pool = [l for l in RELATION_LABELS if len(by_label[l]) > quota[l]]
        i = 0
        while diff > 0 and pool:
            l = pool[i % len(pool)]
            quota[l] += 1
            diff -= 1
            if len(by_label[l]) <= quota[l]:
                pool = [x for x in pool if x != l]
            i += 1
    elif diff < 0:
        pool = [l for l in RELATION_LABELS if quota[l] > 0]
        j = 0
        while diff < 0 and pool:
            l = pool[j % len(pool)]
            quota[l] -= 1
            diff += 1
            if quota[l] == 0:
                pool = [x for x in pool if x != l]
            j += 1
    selected: list[dict] = []
    for lab in RELATION_LABELS:
        selected.extend(by_label[lab][: quota[lab]])
    return selected


def main() -> None:
    ap = argparse.ArgumentParser(
        description="从分类对缓存分层导出 50 对标注模板（人工标注 + 方案甲/乙拍板用）"
    )
    ap.add_argument("--cache", default="cache", help="两级缓存目录（须含 pairs.jsonl）")
    ap.add_argument("--out", default="annotations/pairs_50",
                    help="输出前缀；同前缀写 .jsonl 与 .csv（默认 annotations/pairs_50）")
    ap.add_argument("--n", type=int, default=50, help="导出对数（默认 50）")
    ap.add_argument("--strata", choices=["relation", "proportional"], default="relation",
                    help="relation=按预测标签均衡（默认）；proportional=按真实分布比例")
    ap.add_argument("--seed", type=int, default=20260722, help="取样随机种子（确定性复现）")
    args = ap.parse_args()

    cache_dir = Path(args.cache)
    pairs, skipped = parse_pairs_cache(cache_dir)
    if not pairs:
        print(f"[abort] 在 {cache_dir / 'pairs.jsonl'} 找不到任何可用的分类对。\n"
              f"  请先跑一次语料（uv run python tools/run_corpus.py <语料>）生成缓存后再导出。")
        sys.exit(1)

    # 按标签分组并确定性打乱（仅影响每层内部取哪些样本，不影响分层配额）。
    rng = random.Random(args.seed)
    by_label = {lab: [] for lab in RELATION_LABELS}
    for pr in pairs:
        by_label[pr["model_predicted"]].append(pr)
    for lab in by_label:
        rng.shuffle(by_label[lab])

    selected = (
        _sample_proportional(by_label, args.n)
        if args.strata == "proportional"
        else _sample_balanced(by_label, args.n)
    )
    # 最终顺序再确定性打乱，避免输出按标签成块。
    rng.shuffle(selected)
    selected = selected[: args.n]

    # 写标注模板（JSONL 规范 + CSV 表格友好）。
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "id": f"p{i:03d}",
            "new_memory": pr["new_memory"],
            "existing_memory": pr["existing_memory"],
            "model_predicted": pr["model_predicted"],  # 方案乙（LLM 五选一）预测
            "human_label": "",                        # 人工金标准（待填）
            "notes": "",
        }
        for i, pr in enumerate(selected, 1)
    ]
    with out_path.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # utf-8-sig：Excel 直接打开中文不乱码。
    with out_path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "new_memory", "existing_memory",
                           "model_predicted", "human_label", "notes"]
        )
        w.writeheader()
        for r in records:
            w.writerow(r)

    # 报告：可用量 vs 抽样量。
    avail = {lab: len(by_label[lab]) for lab in RELATION_LABELS}
    got = {lab: 0 for lab in RELATION_LABELS}
    for r in records:
        got[r["model_predicted"]] += 1
    print(f"[导出] 缓存可用分类对={len(pairs)}（跳过无法解析 {skipped} 行）")
    print(f"  分层方式={args.strata} | 抽样={len(records)} 对 | seed={args.seed}")
    print(f"  可用量 / 抽样量（按 predicted 标签）:")
    for lab in RELATION_LABELS:
        print(f"    {lab:12s} avail={avail[lab]:4d}  sampled={got[lab]:3d}")
    print(f"  输出:\n    {out_path.with_suffix('.jsonl')}\n    {out_path.with_suffix('.csv')}")
    print(f"\n[下一步] 在 human_label 列填入人工判定（5 选 1: {'/'.join(RELATION_LABELS)}）。\n"
          f"  填完即可算方案乙(本列 model_predicted)准确率；再喂 NLI cross-encoder 得方案甲\n"
          f"  准确率，两者对比拍板分类器方案。")


if __name__ == "__main__":
    main()
