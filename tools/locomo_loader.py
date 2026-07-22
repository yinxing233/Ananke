#!/usr/bin/env python3
"""LoCoMo -> Ananke 语料/探针适配器（协议 v4 §3 session 语义）。

LoCoMo（snap-research/LoCoMo, ACL 2024）：每对话含多 session（跨数月），每 session 多轮
{speaker, dia_id, text}，外加 qa（question/answer/category/evidence）。本适配器把一个对话
转成 Ananke 可喂的格式：

  - 语料 .jsonl：每行 {session_id, input, dia_id, speaker}。**两个 speaker 的轮次都喂**
    （见下方「双 speaker 裁决」）。session_id = f"{sample_id}_s{n}"，使「跨 session 再断言
    同一事实」= EV（§3：session 边界 = 话语状态重置 = 去相关事件；与哪个 speaker 无关）。
  - 探针 .jsonl：每行 {question, fact, category}（fact=answer）。供 tools/evaluate.py 独立评判端。
  - evidence-speaker 统计：每个 qa 的 evidence 落在哪个 speaker 的轮次，输出 only_a/only_b/both
    分布——双 speaker 决策的事后佐证（见下方裁决）。

**双 speaker 裁决（PI，修正单 speaker 漂移）**：LoCoMo 的两个 speaker 对 Ananke 都是**不可控外部
输入**（系统是被动观察者，§3.3），都是原则B意义上的检验源。§3.3 反身性红线防的是*系统自身输出*
污染输入流（闭环），**不是**把第二个外部说话人当系统排除——那是把红线画错了对象。更实际的是
测量层后果：LoCoMo 的 QA evidence 横跨两 speaker 轮次，只喂一个 speaker 会使相当比例探针在原理上
不可命中，给 evidence 命中率加一个与策略无关的天花板（conv-26 实测：199 探针里 95 个 evidence
全在 speaker_b，单 speaker 喂入即 48% 天花板）。故**两个 speaker 都喂**，语料量翻倍是正常代价。

**§7 数据隔离（硬约束）**：本工具只处理 --sample-id 指定的单个对话。探索阶段（冒烟）接触过
的对话**不得**进入验证集——PI 自行决定哪些 sample_id 用于探索、哪些留验证。本工具不代劳此决策。

数据获取（CC BY-NC 4.0，不入 git）：
    curl -sSL -o data/locomo/locomo10.json \\
      https://raw.githubusercontent.com/snap-research/LoCoMo/main/data/locomo10.json

用法：
    uv run python tools/locomo_loader.py --data data/locomo/locomo10.json --sample-id conv-26
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


def _ordered_sessions(conv: dict) -> list[tuple[int, list[dict]]]:
    """返回 [(n, turns), ...] 按 session 编号升序。"""
    sessions = []
    for k, v in conv.items():
        m = _SESSION_KEY.match(k)
        if m and isinstance(v, list):
            sessions.append((int(m.group(1)), v))
    sessions.sort(key=lambda x: x[0])
    return sessions


def convert_sample(sample: dict) -> tuple[list[dict], list[dict], dict]:
    """把一个 LoCoMo 对话转成 (corpus_rows, probe_rows, evidence_stat)。

    corpus_rows: [{session_id, input, dia_id, speaker}, ...] **两个 speaker 的轮次都喂**。
    probe_rows:  [{question, fact, category}, ...] 每个 qa 一条（fact=answer）。
    evidence_stat: 探针 evidence 的 speaker 分布（only_a/only_b/both/none）。
    """
    sid = sample["sample_id"]
    conv = sample["conversation"]
    speaker_a, speaker_b = conv["speaker_a"], conv["speaker_b"]
    sessions = _ordered_sessions(conv)

    # dia_id -> speaker 映射（供 evidence 统计）
    dia2speaker: dict[str, str] = {}
    corpus: list[dict] = []
    for n, turns in sessions:
        session_id = f"{sid}_s{n}"
        for tu in turns:
            did = tu.get("dia_id", "")
            spk = tu.get("speaker", "")
            if did:
                dia2speaker[did] = spk
            text = (tu.get("text") or "").strip()
            if not text:
                continue
            corpus.append({"session_id": session_id, "input": text, "dia_id": did, "speaker": spk})

    probes: list[dict] = []
    ev_stat = {"total": 0, "with_evidence": 0, "only_a": 0, "only_b": 0, "both": 0, "none": 0, "unmatched": 0}
    for qa in sample.get("qa", []):
        q = str(qa.get("question") or "").strip()
        a = str(qa.get("answer") or "").strip()  # answer 偶为 int（如年份），强转 str
        if not q:
            continue
        probes.append({"question": q, "fact": a, "category": qa.get("category")})
        ev_stat["total"] += 1
        ev = qa.get("evidence") or []
        if not ev:
            ev_stat["none"] += 1
            continue
        ev_stat["with_evidence"] += 1
        spks = {dia2speaker[e] for e in ev if e in dia2speaker}
        if not spks:
            ev_stat["unmatched"] += 1
        elif spks == {speaker_a}:
            ev_stat["only_a"] += 1
        elif spks == {speaker_b}:
            ev_stat["only_b"] += 1
        else:
            ev_stat["both"] += 1
    return corpus, probes, ev_stat


def _write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="LoCoMo -> Ananke 语料/探针适配器（协议 v4 §3，双 speaker）")
    ap.add_argument("--data", required=True, help="locomo10.json 路径")
    ap.add_argument("--sample-id", default=None, help="对话 sample_id（如 conv-26）；缺省列出全部")
    ap.add_argument("--index", type=int, default=None, help="按列表下标选对话（0-based）")
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
            n_turns = sum(len(ts) for _, ts in sess)
            print(f"  [{i}] {s['sample_id']}: {len(sess)} sessions | "
                  f"{c['speaker_a']}/{c['speaker_b']} | 总轮次(双speaker)={n_turns} | qa={len(s.get('qa', []))}")
        return

    sample = None
    if args.sample_id is not None:
        sample = next((s for s in data if s.get("sample_id") == args.sample_id), None)
        if sample is None:
            raise SystemExit(f"[err] sample_id={args.sample_id} 不在 {args.data}。可用值见无参数运行。")
    else:
        sample = data[args.index]

    conv = sample["conversation"]
    corpus, probes, ev_stat = convert_sample(sample)

    sid = sample["sample_id"]
    out_corpus = Path(args.out_corpus) if args.out_corpus else Path(f"data/locomo/{sid}_corpus.jsonl")
    out_probes = Path(args.out_probes) if args.out_probes else Path(f"data/locomo/{sid}_probes.jsonl")
    _write_jsonl(corpus, out_corpus)
    _write_jsonl(probes, out_probes)

    sessions = _ordered_sessions(conv)
    print(f"[ok] {sid} | {conv['speaker_a']}/{conv['speaker_b']} | sessions={len(sessions)} | 双 speaker 喂入")
    print(f"     语料: {len(corpus)} 条轮次(双speaker) -> {out_corpus}")
    print(f"     探针: {len(probes)} 条 qa -> {out_probes}")
    print(f"     session_id: {sid}_s1 .. {sid}_s{len(sessions)}（跨 session 重复=EV，§3，与 speaker 无关）")
    # evidence-speaker 统计（双 speaker 决策的事后佐证）
    print(f"     evidence speaker 分布: only_a={ev_stat['only_a']} only_b={ev_stat['only_b']} "
          f"both={ev_stat['both']} none={ev_stat['none']} unmatched={ev_stat['unmatched']}")
    print(f"     [佐证] 若单喂 speaker_a，{ev_stat['only_b']} 个探针({ev_stat['only_b']*100//max(ev_stat['total'],1)}%)"
          f" evidence 全在 speaker_b → 原理上不可命中")
    print(f"     下一步: uv run python tools/run_corpus.py {out_corpus} --strategy persistence --data data/p --clean")


if __name__ == "__main__":
    main()
