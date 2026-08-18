"""重测 50 对：用新分类 prompt（三层判定 + R1/R2）重新分类，与闭包金标准比对。

用途：协议 v4 校准——验证 12 例裁决产出的规则（三层判定结构 + 模态一致性 R1 +
同谓词 R2）写进 relation.py prompt 后，能否拉高 Mistral 与金标准的一致率/κ。

- 输入：docs/calibration/relation_labels/cases.jsonl（50 对，new_memory/existing_memory
  为归一化文本；金标准 = final_label 兜底 human_label）。
- 输出：stdout 报告一致率 + Cohen's κ + 混淆矩阵；结果 JSON 存到
  logs/relation_retest_prompt_v2.json（只增不删）。
- 计量：真实 API 调用写入 usage 日志（与正式运行同格式），不推测价格。
- 注意：新 prompt 的 prompt_hash 与旧缓存不同，故 50 对全部 miss 旧 pairs 缓存、
  产生真实 relation 调用（约 50 次，无重试则各 1 次 HTTP）；旧缓存条目保留不删。

运行：USE_MOCK_LLM=false .venv/Scripts/python.exe tools/retest_relation_50.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ananke.config import Config
from ananke.llm_client import create_llm_client
from ananke.relation import LLMRelationClassifier, RelationParseError

CASES_PATH = Path("docs/calibration/relation_labels/cases.jsonl")
OUT_PATH = Path("logs/relation_retest_prompt_v2.json")
USAGE_PATH = Path("logs/relation_retest_prompt_v2_llm_usage.jsonl")

LABELS = ["duplicate", "contradict", "mergeable", "related", "unrelated"]


def kappa(a: list[str], b: list[str]) -> tuple[float, float]:
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    return po, (po - pe) / (1 - pe) if 1 - pe > 0 else float("nan")


def main() -> int:
    cases = [json.loads(l) for l in open(CASES_PATH, encoding="utf-8")]
    assert len(cases) == 50, f"expected 50 cases, got {len(cases)}"
    gold = [c["final_label"] if c["final_label"] else c["human_label"] for c in cases]

    if Config.USE_MOCK_LLM:
        print("ERROR: USE_MOCK_LLM=true —— 本工具必须用真实 LLM 重测分类 prompt。", file=sys.stderr)
        return 2

    llm_client = create_llm_client(usage_log=USAGE_PATH)
    classifier = LLMRelationClassifier(llm_client, temperature=0.0)

    preds: list[str] = []
    failures: list[dict] = []
    for c in cases:
        try:
            label = classifier.classify(c["new_memory"], c["existing_memory"])
            preds.append(label)
        except RelationParseError as e:
            failures.append({"case_id": c["case_id"], "error": str(e)})
            preds.append("__parse_fail__")

    print(f"完成 {len(preds)} 对；解析失败 {len(failures)} 条")

    if failures:
        print("解析失败明细（B7 重试耗尽仍失败，须报告）：")
        for f in failures:
            print("  -", f)

    valid = [(g, p) for g, p in zip(gold, preds) if p != "__parse_fail__"]
    valid_gold = [g for g, _ in valid]
    valid_pred = [p for _, p in valid]

    po, k = kappa(valid_gold, valid_pred)
    print(f"\n=== 新 prompt（三层判定 + R1/R2）vs 闭包金标准 ===")
    print(f"有效对 {len(valid)}/50 | 一致率 {po:.2%} | κ {k:.3f}")

    print("\n=== 混淆矩阵：金标准(行) x 新预测(列) ===")
    print("          " + "".join(f"{l[:4]:>6}" for l in LABELS))
    for g in LABELS:
        row = [sum(1 for gg, pp in valid if gg == g and pp == m) for m in LABELS]
        print(f"{g[:4]:>10}" + "".join(f"{v:>6}" for v in row))

    result = {
        "n": len(valid),
        "n_total": len(preds),
        "n_parse_fail": len(failures),
        "agreement": po,
        "kappa": k,
        "parse_failures": failures,
        "prompt": "three-layer + R1/R2 (2026-08-11)",
        "gold_rule": "final_label fallback human_label (input closure)",
        "labels": LABELS,
        "confusion": {
            g: {m: sum(1 for gg, pp in valid if gg == g and pp == m) for m in LABELS}
            for g in LABELS
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已存: {OUT_PATH}")
    print(f"usage 日志: {USAGE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
