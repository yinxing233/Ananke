#!/usr/bin/env python3
"""LoCoMo -> Ananke 语料/探针适配器（协议 v4 §3 session 语义）。

LoCoMo（snap-research/LoCoMo, ACL 2024）：每对话含多 session（跨数月），每 session 多轮
{speaker, dia_id, text}，外加 qa（question/answer/category/evidence）。本适配器把一个对话
转成 Ananke 可喂的格式：

  - 语料 .jsonl：每行 {session_id, input, dia_id}。session_id = f"{sample_id}_s{n}"，
    使「跨 session 再断言同一事实」= EV（§3：session 边界 = 话语状态重置 = 去相关事件）。
  - 探针 .jsonl：每行 {question, fact}（fact=answer）。供 tools/evaluate.py 的独立评判端。

**视角选择（PI 决策点，默认 speaker_a）**：LoCoMo 是两个 agent 对话。Ananke 是被动观察者
（§3.3 闭环未检验），只把**一个 speaker** 的轮次当「外部用户输入」喂入（跨 session 重复=EV）；
另一 speaker 视为系统自身历史输出，**不喂**（喂了会形成系统行为污染输入流，违反反身性红线）。
默认 user=speaker_a（如 Caroline），可用 --user-speaker speaker_b 或显式名字切换。

**§7 数据隔离（硬约束）**：本工具只处理 --sample-id 指定的单个对话。探索阶段（冒烟）接触过
的对话**不得**进入验证集——PI 自行决定哪些 sample_id 用于探索、哪些留验证。本工具不代劳此决策。

数据获取（CC BY-NC 4.0，不入 git）：
    curl -sSL -o data/locomo/locomo10.json \\
      https://raw.githubusercontent.com/snap-research/LoCoMo/main/data/locomo10.json

用法：
    # 转换单个对话（默认 speaker_a 为 user）
    uv run python tools/locomo_loader.py --data data/locomo/locomo10.json --sample-id conv-26 \
        --out-corpus data/locomo/conv-26_corpus.jsonl --out-probes data/locomo/conv-26_probes.jsonl
    # 切换视角
    uv run python tools/locomo_loader.py --data data/locomo/locomo10.json --sample-id conv-26 \
        --user-speaker speaker_b --out-corpus ... --out-probes ...
    # 跑通后：
    uv run python tools/run_corpus.py data/locomo/conv-26_corpus.jsonl --strategy persistence --data data/p --clean
    uv run python tools/evaluate.py --data data/p --probes data/locomo/conv-26_probes.jsonl --strategy persistence --tag p
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

_SESSION_KEY = re.compile(r"^session_(\d+)$")


def _resolve_user_speaker(name: str, conv: dict) -> str:
    """--user-speaker 接受 speaker_a/speaker_b 或显式名字。"""
    if name in ("speaker_a", "a"):
        return conv["speaker_a"]
    if name in ("speaker_b", "b"):
        return conv["speaker_b"]
    if name in (conv["speaker_a"], conv["speaker_b"]):
        return name
    raise ValueError(
        f"--user-speaker {name!r} 无法解析；可用 speaker_a/speaker_b 或 "
        f"{conv['speaker_a']!r}/{conv['speaker_b']!r}"
    )


def _ordered_sessions(conv: dict) -> list[tuple[int, list[dict]]]:
    """返回 [(n, turns), ...] 按 session 编号升序。"""
    sessions = []
    for k, v in conv.items():
        m = _SESSION_KEY.match(k)
        if m and isinstance(v, list):
            sessions.append((int(m.group(1)), v))
    sessions.sort(key=lambda x: x[0])
    return sessions


def convert_sample(sample: dict, user_speaker_name: str) -> tuple[list[dict], list[dict]]:
    """把一个 LoCoMo 对话转成 (corpus_rows, probe_rows)。

    corpus_rows: [{session_id, input, dia_id}, ...] 每个 user 轮次一条。
    probe_rows:  [{question, fact, category}, ...] 每个 qa 一条（fact=answer）。
    """
    sid = sample["sample_id"]
    conv = sample["conversation"]
    sessions = _ordered_sessions(conv)

    corpus: list[dict] = []
    for n, turns in sessions:
        session_id = f"{sid}_s{n}"
        for tu in turns:
            if tu.get("speaker") != user_speaker_name:
                continue  # 只喂 user 轮次；另一 speaker = 系统输出，不喂（反身性红线）
            text = (tu.get("text") or "").strip()
            if not text:
                continue
            corpus.append({"session_id": session_id, "input": text, "dia_id": tu.get("dia_id", "")})

    probes: list[dict] = []
    for qa in sample.get("qa", []):
        q = str(qa.get("question") or "").strip()
        a = str(qa.get("answer") or "").strip()  # answer 偶为 int（如年份），强转 str
        if not q:
            continue
        probes.append({"question": q, "fact": a, "category": qa.get("category")})
    return corpus, probes


def _write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="LoCoMo -> Ananke 语料/探针适配器（协议 v4 §3）")
    ap.add_argument("--data", required=True, help="locomo10.json 路径")
    ap.add_argument("--sample-id", default=None, help="对话 sample_id（如 conv-26）；缺省列出全部")
    ap.add_argument("--index", type=int, default=None, help="按列表下标选对话（0-based）")
    ap.add_argument("--user-speaker", default="speaker_a",
                    help="视角：speaker_a(默认)/speaker_b 或显式名字。该 speaker 的轮次作外部输入")
    ap.add_argument("--out-corpus", default=None, help="语料 .jsonl 输出路径")
    ap.add_argument("--out-probes", default=None, help="探针 .jsonl 输出路径")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{args.data} 顶层应为 list，实为 {type(data).__name__}")

    # 仅列出（不选定对话）——供 PI 挑探索/验证对话用
    if args.sample_id is None and args.index is None:
        print(f"[info] {args.data} 共 {len(data)} 个对话。用 --sample-id 或 --index 选一个：")
        for i, s in enumerate(data):
            c = s["conversation"]
            sess = _ordered_sessions(c)
            n_user_a = sum(1 for _, ts in sess for t in ts if t.get("speaker") == c["speaker_a"])
            print(f"  [{i}] {s['sample_id']}: {len(sess)} sessions | "
                  f"{c['speaker_a']}/{c['speaker_b']} | user({c['speaker_a']})轮次={n_user_a} | qa={len(s.get('qa', []))}")
        return

    sample = None
    if args.sample_id is not None:
        sample = next((s for s in data if s.get("sample_id") == args.sample_id), None)
        if sample is None:
            raise SystemExit(f"[err] sample_id={args.sample_id} 不在 {args.data}。可用值见无参数运行。")
    else:
        sample = data[args.index]

    conv = sample["conversation"]
    user_name = _resolve_user_speaker(args.user_speaker, conv)
    corpus, probes = convert_sample(sample, user_name)

    sid = sample["sample_id"]
    out_corpus = Path(args.out_corpus) if args.out_corpus else Path(f"data/locomo/{sid}_corpus.jsonl")
    out_probes = Path(args.out_probes) if args.out_probes else Path(f"data/locomo/{sid}_probes.jsonl")
    _write_jsonl(corpus, out_corpus)
    _write_jsonl(probes, out_probes)

    sessions = _ordered_sessions(conv)
    n_sessions = len(sessions)
    print(f"[ok] {sid} | user={user_name} | sessions={n_sessions}")
    print(f"     语料: {len(corpus)} 条 user 轮次 -> {out_corpus}")
    print(f"     探针: {len(probes)} 条 qa -> {out_probes}")
    print(f"     session_id 示例: {sid}_s1 .. {sid}_s{n_sessions}（跨 session 重复=EV，§3）")
    print(f"     下一步: uv run python tools/run_corpus.py {out_corpus} --strategy persistence --data data/p --clean")


if __name__ == "__main__":
    main()
