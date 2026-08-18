"""跨模型探针：旧 qwen 判过 duplicate 的句对，用冻结 prompt 分别过 qwen 和 mistral。

目的（诊断性，不入正式运行）：区分 EV=0 的 (a1) prompt 本身弱 vs (a2) prompt×模型交互。
- 若 qwen 判 duplicate、mistral 不判 → 模型差异（冻结 prompt 在 qwen 上可触发 duplicate）
- 若 qwen 也不判 → prompt 本身弱

用法：
  python tools/probe_cross_model.py
环境变量：
  QWEN_BASE_URL / QWEN_API_KEY / QWEN_MODEL  (默认走 .env 的 LLM_* 用 mistral)
  MISTRAL_BASE_URL / MISTRAL_API_KEY / MISTRAL_MODEL (默认 .env 当前驱动)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ananke.relation import (
    RELATION_USER_PREFIX,
    _LLM_SYSTEM_PROMPT,
    parse_relation_label,
)

# 冻结 prompt 的 4 对（从 cache/pairs.jsonl 旧 qwen duplicate 条目提取）
PAIRS = [
    ("carolines goal is to give kids a loving home",
     "caroline has a dream of having a family and providing a loving home to children in need through adoption"),
    ("caroline is thrilled to create a family for kids who need one",
     "caroline has a dream of having a family and providing a loving home to children in need through adoption"),
    ("caroline treasures a necklace",
     "caroline owns a necklace"),
    ("caroline attended a parade supporting the lgbtq community",
     "caroline went to an lgbtq pride parade last week"),
]


def call(base_url: str, api_key: str, model: str, new: str, existing: str) -> str:
    import urllib.request
    import urllib.error

    user_prompt = RELATION_USER_PREFIX.format(existing=existing, new=new)
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 6,
        }).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
            raw = data["choices"][0]["message"]["content"].strip()
            return raw, parse_relation_label(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        return f"__HTTP_{e.code}__", f"ERROR: {body}"
    except Exception as e:
        return f"__ERR__", f"ERROR: {type(e).__name__} {str(e)[:150]}"


def main() -> int:
    # qwen 配置（环境变量，缺省走 .env 值）
    qwen_base = os.getenv("QWEN_BASE_URL", "")
    qwen_key = os.getenv("QWEN_API_KEY", "")
    qwen_model = os.getenv("QWEN_MODEL", "qwen3.7-max-2026-05-20")

    # mistral 配置（读 .env 当前驱动）
    from dotenv import load_dotenv
    load_dotenv()
    mistral_base = os.getenv("LLM_BASE_URL", "")
    mistral_key = os.getenv("LLM_API_KEY", "")
    mistral_model = os.getenv("LLM_MODEL", "mistral-small-2603")

    if not (qwen_base and qwen_key):
        print("ERROR: 需要 QWEN_BASE_URL 和 QWEN_API_KEY 环境变量", file=sys.stderr)
        return 2

    print(f"qwen    : {qwen_model} @ {qwen_base}")
    print(f"mistral : {mistral_model} @ {mistral_base}")
    print(f"句对数量: {len(PAIRS)}（3 个独特对）")
    print()

    results = []
    for i, (new, existing) in enumerate(PAIRS):
        print(f"--- 句对 [{i}] ---")
        print(f"  new: {new}")
        print(f"  old: {existing}")
        for side, base, key, model in [
            ("qwen", qwen_base, qwen_key, qwen_model),
            ("mistral", mistral_base, mistral_key, mistral_model),
        ]:
            raw, label = call(base, key, model, new, existing)
            print(f"  {side:>8}: raw={raw[:40]!r} -> {label}")
            results.append({
                "pair_idx": i, "new": new, "existing": existing,
                "side": side, "model": model, "raw": raw, "label": label,
            })
        print()

    out = Path("logs/cross_model_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已存: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
