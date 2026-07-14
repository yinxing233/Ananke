#!/usr/bin/env python3
"""一次性 Phase 3 对照对比：同语料两策略，仅切 Migration Rule。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_store(data_dir):
    """返回 {memory_id: record} 跨 working+consolidated。"""
    store = {}
    for fn in ("working.jsonl", "consolidated.jsonl"):
        p = data_dir / fn
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    d = json.loads(line)
                    store[d["id"]] = d
    return store


def migrations(log_path):
    """返回 [(step, memory_id, migration_score, persistence_score, frequency_score)]。"""
    out = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("event") == "working_to_consolidated":
                out.append((
                    d.get("input_index"),
                    d["memory_id"],
                    d.get("migration_score"),
                    d.get("persistence_score"),
                    d.get("frequency_score"),
                ))
    return out


def all_memories(log_path, data_dir):
    """从日志 memory_write + dedup_skip + store 还原两遍提取的记忆内容集合。"""
    contents = set()
    store = load_store(data_dir)
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("event") == "memory_write":
                contents.add(d.get("content_summary", ""))
    return contents


def promote_detail(log_path, data_dir):
    store = load_store(data_dir)
    rows = []
    for step, mid, ms, ps, fs in migrations(log_path):
        rec = store.get(mid, {})
        rows.append({
            "step": step,
            "content": rec.get("content", "<not found>"),
            "migration_score": ms,
            "persistence_score": ps,
            "frequency_score": fs,
            "ev": rec.get("external_validation"),
            "ia": rec.get("internal_activation"),
            "total": rec.get("total_activation"),
        })
    return rows


P = ROOT / "logs" / "phase3_persist.jsonl"
F = ROOT / "logs" / "phase3_freq.jsonl"
DP = ROOT / "data" / "phase3_persist"
DF = ROOT / "data" / "phase3_freq"

p_mig = promote_detail(P, DP)
f_mig = promote_detail(F, DF)

print("=" * 70)
print(f"PERSISTENCE (External Selection): {len(p_mig)} 次升层")
print("=" * 70)
for r in p_mig:
    print(f"  step={r['step']} | persist={r['persistence_score']:.2f} freq={r['frequency_score']} "
          f"(EV={r['ev']},IA={r['ia']},total={r['total']}) | {r['content']}")

print()
print("=" * 70)
print(f"FREQUENCY (Internal Selection): {len(f_mig)} 次升层")
print("=" * 70)
for r in f_mig:
    print(f"  step={r['step']} | freq={r['frequency_score']} persist={r['persistence_score']:.2f} "
          f"(EV={r['ev']},IA={r['ia']},total={r['total']}) | {r['content']}")

# 提取记忆集一致性（验证唯一变量=策略）
p_contents = all_memories(P, DP)
f_contents = all_memories(F, DF)
print()
print("=" * 70)
print("提取记忆集一致性检查（应高度重合，否则违反比较器）")
print("=" * 70)
print(f"  persistence 提取条数: {len(p_contents)}")
print(f"  frequency  提取条数: {len(f_contents)}")
print(f"  交集条数: {len(p_contents & f_contents)}")
print(f"  仅在 persistence: {len(p_contents - f_contents)}")
print(f"  仅在 frequency:   {len(f_contents - p_contents)}")
only_p = sorted(p_contents - f_contents)
only_f = sorted(f_contents - p_contents)
for c in only_p:
    print(f"    [P-only] {c}")
for c in only_f:
    print(f"    [F-only] {c}")

# 频率升层但持久化未升层的记忆：检查它们是否存在于持久化 run 的 store（未升层）
p_store = load_store(DP)
f_store = load_store(DF)
f_promoted_contents = {r["content"] for r in f_mig}
p_promoted_contents = {r["content"] for r in p_mig}
print()
print("=" * 70)
print("频率升层 ⊃ 持久化未升层 的记忆（被内部选择过度推广的）")
print("=" * 70)
for r in f_mig:
    if r["content"] not in p_promoted_contents:
        # 在 persist store 中找同内容记忆，看其分数
        match = [s for s in p_store.values() if s.get("content") == r["content"]]
        if match:
            s = match[0]
            print(f"  [OVER-PROMOTED] {r['content']}")
            print(f"      persist-run: persist={s.get('persistence_score',0):.2f} freq={s.get('frequency_score')} "
                  f"(EV={s.get('external_validation')},IA={s.get('internal_activation')},total={s.get('total_activation')}) "
                  f"-> 在 persist 下停留快层")
        else:
            print(f"  [F-ONLY-MEM] {r['content']}  (persist 跑里无此记忆，提取差异)")
