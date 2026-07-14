#!/usr/bin/env python3
"""Ananke 动力学分析：把事件日志重建为 per-memory Trajectory。

读 logs/events.jsonl（设计文档 §九 的审计日志），按 memory_id 把所有状态转移
聚合成单条记忆的 **Memory Trajectory**（GPT 强调的真正分析单元，而非 Log File）。

本工具定位（GPT 硬性边界）：
    **只描述系统发生了什么（状态转移 + 分数），不判定理论是否正确。**
    理论是否成立由实验设计（含允许失败的反例）决定，不是分析器能回答的。

输出：
  1) 文本摘要（stdout）：系统行为事实 + 迁移规则(config) + 未迁移/失败样本。
  2) 自包含 HTML 报告 logs/trajectory_report.html：每条记忆一张卡片，
     含「状态轨迹(State)」+ SVG 事件时间线 + 事件明细表 + 失败样本分区。

纯观测工具，**不修改 pipeline，不碰核心逻辑**，只为提升理论 A/B 的可验证性。

用法：
    uv run python tools/analyze_trajectory.py
    uv run python tools/analyze_trajectory.py --log logs/dev_events.jsonl --data data/dev
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ananke.config import Config
from ananke.memory_store import MemoryStore

# event -> (归属角色, 中文标签, 颜色, 字形)
EVENT_META = {
    "memory_write": ("self", "写入", "#2e7d32", "W"),
    "internal_activation": ("self", "内部激活", "#1565c0", "I"),
    "external_validation": ("self", "外部验证", "#ef6c00", "E"),
    "working_to_consolidated": ("self", "→巩固层", "#6a1b9a", "C"),
    "consolidated_to_core": ("self", "→慢层", "#212121", "K"),
    "local_reorganization": ("trigger", "重组", "#c62828", "R"),
    "working_eviction": ("self", "淘汰", "#9e9e9e", "X"),
}

EXTERNAL_W = 1.0
INTERNAL_W = Config.INTERNAL_ACTIVATION_WEIGHT  # 1/e


def _parse(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.min


def load_records(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def group_by_memory(records: list[dict]) -> dict[str, list[dict]]:
    """按 memory_id 聚合；local_reorganization 用 trigger_memory_id 归属到触发源。"""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        mid = rec.get("memory_id") or rec.get("trigger_memory_id")
        if not mid:
            continue
        grouped[mid].append(rec)
    for mid in grouped:
        grouped[mid].sort(key=lambda r: _parse(r.get("timestamp", "")))
    return grouped


def final_layer(events: list[dict]) -> str:
    layer = "WORKING"
    evicted = False
    for ev in events:
        if ev["event"] == "working_to_consolidated":
            layer = "CONSOLIDATED"
        elif ev["event"] == "consolidated_to_core":
            layer = "CORE"
        elif ev["event"] == "working_eviction":
            evicted = True
    return "EVICTED" if evicted else layer


def compute_state_trace(events: list[dict]) -> list[dict]:
    """逐事件重建运行态：层 + 累计外部验证 + 累计内部激活 + persistence 分数。
    GPT 要点：事件只是离散点，真正发生迁移的是「状态」。分析对象是状态空间。"""
    layer = "WORKING"
    ext = 0
    intl = 0
    trace = []
    for ev in events:
        e = ev["event"]
        if e == "memory_write":
            layer = "WORKING"
        elif e == "external_validation":
            ext = ev.get("external_validation", ext)
        elif e == "internal_activation":
            intl = ev.get("internal_activation", intl)
        elif e == "working_to_consolidated":
            layer = "CONSOLIDATED"
        elif e == "consolidated_to_core":
            layer = "CORE"
        elif e == "working_eviction":
            layer = "EVICTED"
        score = ext * EXTERNAL_W + intl * INTERNAL_W
        trace.append({"event": e, "layer": layer, "ext": ext, "intl": intl, "score": score})
    return trace


def state_trace_str(trace: list[dict]) -> str:
    return " → ".join(f"{t['layer']}({t['score']:.2f})" for t in trace)


def final_counts(events: list[dict]) -> tuple[int, int]:
    ext = max([e.get("external_validation", 0) for e in events if e["event"] == "external_validation"] + [0])
    intl = max([e.get("internal_activation", 0) for e in events if e["event"] == "internal_activation"] + [0])
    return ext, intl


def failure_samples(grouped: dict[str, list[dict]], content_map: dict[str, str], store=None) -> list[str]:
    """GPT 要点：失败样本（未迁移/被淘汰）通常比成功样本更重要。
    明确回答「为什么没进去 / 为什么被淘汰」。
    注意：停留巩固层记忆的 local_reorganization_trigger 必须从 MemoryStore 取
    （consolidated_to_core 事件只在真正升慢层时才写，未晋升者查不到）。"""
    out = []
    for mid, evs in grouped.items():
        fl = final_layer(evs)
        if fl == "CORE":
            continue
        ext, intl = final_counts(evs)
        score = ext * EXTERNAL_W + intl * INTERNAL_W
        content = (content_map.get(mid, "") or "(无内容)")[:22]
        if fl == "EVICTED":
            ev = [e for e in evs if e["event"] == "working_eviction"][-1]
            out.append(
                f"  · 淘汰: 「{content}」 — persistence_score={ev.get('persistence_score')} "
                f"（从未获得外部/内部检验，最低优先级被清出快层）"
            )
        elif fl == "WORKING":
            gap = Config.MIGRATION_THRESHOLD - score
            out.append(
                f"  · 未晋升(快层): 「{content}」 — 当前 persistence={score:.2f}，"
                f"距阈值 {Config.MIGRATION_THRESHOLD:.1f} 还差 {gap:.2f}；"
                f"若无新的外部验证将保持此状态"
            )
        elif fl == "CONSOLIDATED":
            trig = 0
            if store is not None:
                mem = store.find(mid)
                if mem is not None:
                    trig = mem.local_reorganization_trigger
            if trig == 0:
                # 兜底：从重组事件计数（trigger_memory_id 指向该记忆）
                trig = sum(1 for e in evs if e["event"] == "local_reorganization")
            out.append(
                f"  · 停留巩固层: 「{content}」 — local_reorganization_trigger={trig} "
                f"（需 ≥ {Config.LOCAL_REORG_THRESHOLD} 才进慢层）"
            )
    return out


def summarize(records, grouped, content_map, store=None) -> str:
    total = len(records)
    promotions = [r for r in records if r["event"] == "working_to_consolidated"]
    to_core = [r for r in records if r["event"] == "consolidated_to_core"]
    evictions = [r for r in records if r["event"] == "working_eviction"]
    external = [r for r in records if r["event"] == "external_validation"]
    internal = [r for r in records if r["event"] == "internal_activation"]
    reorg = [r for r in records if r["event"] == "local_reorganization"]
    modes = Counter(p.get("migration_strategy") for p in promotions)
    failed = failure_samples(grouped, content_map, store)

    L = []
    L.append("=" * 64)
    L.append("Ananke 动力学分析 (Memory Trajectory) — 仅描述系统发生了什么")
    L.append("=" * 64)
    L.append(f"事件总数: {total} | 外部验证 {len(external)} | 内部激活 {len(internal)} | 局部重组 {len(reorg)}")
    L.append(
        f"迁移规则(config): 升层策略={dict(modes) or '无升层'} 阈值={Config.MIGRATION_THRESHOLD}；"
        f"中→慢需 local_reorganization_trigger ≥ {Config.LOCAL_REORG_THRESHOLD}"
    )
    L.append(f"系统行为: 升巩固层 {len(promotions)} 次 | 升慢层 {len(to_core)} 次 | 淘汰 {len(evictions)} 次")
    L.append("")
    L.append("— 本分析器定位 —")
    L.append("只报告「系统实际发生了什么」（状态转移 + 分数），")
    L.append("不判定理论是否正确；理论是否成立由实验设计（含允许失败的反例）决定。")
    L.append("")
    L.append(f"— 未迁移 / 失败样本（通常比成功样本更重要）: 共 {len(failed)} 条 —")
    L.extend(failed if failed else ["  （全部记忆都进入了慢层）"])
    L.append("=" * 64)
    return "\n".join(L)


def render_timeline(events: list[dict]) -> str:
    n = len(events)
    if n == 0:
        return ""
    width = max(380, 70 + n * 72)
    height = 64
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMinYMin meet" style="max-width:{width}px">']
    parts.append(f'<line x1="40" y1="32" x2="{width-20}" y2="32" stroke="#cfcfcf" stroke-width="2"/>')
    gap = (width - 60) / max(1, n - 1) if n > 1 else 0
    for i, ev in enumerate(events):
        x = 40 + (i * gap if n > 1 else (width - 80) / 2)
        _, label, color, glyph = EVENT_META.get(ev["event"], ("self", ev["event"], "#888", "?"))
        title = _event_title(ev)
        parts.append(f'<circle cx="{x:.0f}" cy="32" r="15" fill="{color}"><title>{html.escape(title)}</title></circle>')
        parts.append(f'<text x="{x:.0f}" y="37" text-anchor="middle" font-size="13" fill="#fff" font-family="sans-serif">{glyph}</text>')
        parts.append(f'<text x="{x:.0f}" y="58" text-anchor="middle" font-size="10" fill="#999" font-family="sans-serif">{i+1}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _event_title(ev: dict) -> str:
    e = ev["event"]
    t = ev.get("timestamp", "")
    if e == "memory_write":
        return f"[{t}] 写入\n{ev.get('content_summary','')}"
    if e == "internal_activation":
        return f"[{t}] 内部激活 #{ev.get('internal_activation')}\ncosine={ev.get('cosine_similarity')}\n{ev.get('input_summary','')}"
    if e == "external_validation":
        return f"[{t}] 外部验证 #{ev.get('external_validation')}\ncosine={ev.get('cosine_similarity')}\n{ev.get('input_summary','')}"
    if e == "working_to_consolidated":
        return f"[{t}] 升巩固层\nstrategy={ev.get('migration_strategy')} score={ev.get('migration_score')}\npersist={ev.get('persistence_score')} freq={ev.get('frequency_score')}"
    if e == "consolidated_to_core":
        return f"[{t}] 升慢层\ntrigger={ev.get('local_reorganization_trigger')}"
    if e == "local_reorganization":
        return f"[{t}] 局部重组: {ev.get('action')}\n配对 {ev.get('paired_memory_id','')[:8]}\ncosine={ev.get('cosine_similarity')}"
    if e == "working_eviction":
        return f"[{t}] 淘汰\npersist={ev.get('persistence_score')}"
    return f"[{t}] {e}"


def render_card(mid: str, events: list[dict], content: str, trace: list[dict]) -> str:
    layer = final_layer(events)
    counters = f"最终层={layer}"
    rows = []
    for i, (ev, st) in enumerate(zip(events, trace)):
        _, label, color, _ = EVENT_META.get(ev["event"], ("self", ev["event"], "#888", "?"))
        detail = _event_title(ev).replace("\n", " ⏎ ")
        rows.append(
            f'<tr>'
            f'<td style="color:{color};font-weight:600;white-space:nowrap">{i+1}. {label}</td>'
            f'<td style="font-size:12px;color:#555;white-space:nowrap">{st["layer"]}</td>'
            f'<td style="font-size:12px;color:#555;white-space:nowrap">{st["score"]:.2f}</td>'
            f'<td style="font-size:12px;color:#555">{html.escape(detail)}</td>'
            f'</tr>'
        )
    rows_html = "".join(rows)
    content_html = html.escape(content or "(无内容)")
    timeline = render_timeline(events)
    state_html = html.escape(state_trace_str(trace))
    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px;margin-bottom:14px;background:#fff">
      <div style="font-weight:700;margin-bottom:4px">{content_html}</div>
      <div style="font-size:12px;color:#666;margin-bottom:6px">{html.escape(mid[:12])}… · {counters}</div>
      <div style="font-size:12px;color:#1565c0;margin-bottom:6px;font-family:monospace;word-break:break-all">状态轨迹: {state_html}</div>
      {timeline}
      <table style="width:100%;border-collapse:collapse;margin-top:8px">
        <thead><tr style="text-align:left;color:#888;font-size:11px">
          <th>事件</th><th>层</th><th>persist</th><th>明细</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


def render_failure_section(grouped, content_map, store=None) -> str:
    failed = failure_samples(grouped, content_map, store)
    if not failed:
        return '<p style="color:#2e7d32">全部记忆都进入了慢层，无失败样本。</p>'
    items = "".join(f"<li style='margin-bottom:4px'>{html.escape(x.strip())}</li>" for x in failed)
    return f'<ul style="font-size:13px;color:#555;line-height:1.5">{items}</ul>'


def build_html(records, grouped, content_map, log_path, store=None) -> str:
    cards = []
    for mid, events in sorted(grouped.items(), key=lambda kv: _parse(kv[1][0].get("timestamp", "")) if kv[1] else datetime.min):
        trace = compute_state_trace(events)
        cards.append(render_card(mid, events, content_map.get(mid, ""), trace))
    cards_html = "\n".join(cards)
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>Ananke Trajectory Report</title></head>
<body style="font-family:-apple-system,Segoe UI,sans-serif;background:#f5f6f8;color:#222;max-width:920px;margin:0 auto;padding:20px">
<h2>Ananke · Memory Trajectory 报告</h2>
<p style="color:#666;font-size:13px">数据源: {html.escape(log_path)} · 共 {len(grouped)} 条记忆的动力学轨迹。
图例: <span style="color:#2e7d32">W 写入</span> · <span style="color:#1565c0">I 内部激活</span> ·
<span style="color:#ef6c00">E 外部验证</span> · <span style="color:#6a1b9a">C 升巩固层</span> ·
<span style="color:#212121">K 升慢层</span> · <span style="color:#c62828">R 重组</span> · <span style="color:#9e9e9e">X 淘汰</span></p>
<p style="color:#c62828;font-size:12px">本分析器只描述系统发生了什么，不判定理论是否正确。</p>

<h3 style="margin-top:24px">未迁移 / 失败样本（通常比成功样本更重要）</h3>
{render_failure_section(grouped, content_map, store)}

<h3 style="margin-top:24px">各记忆状态轨迹</h3>
{cards_html}
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="重建 Ananke 事件日志为 Memory Trajectory")
    ap.add_argument("--log", default="logs/events.jsonl", help="事件日志路径 (默认 logs/events.jsonl)")
    ap.add_argument("--data", default="data", help="记忆存储目录，用于取完整 content (默认 data)")
    ap.add_argument("--out", default="logs/trajectory_report.html", help="HTML 报告输出路径")
    args = ap.parse_args()

    log_path = Path(args.log)
    records = load_records(log_path)
    if not records:
        print(f"[warn] 未在 {log_path} 找到事件。请先跑一段语料生成日志。")
        return

    grouped = group_by_memory(records)

    content_map: dict[str, str] = {}
    try:
        store = MemoryStore(args.data)
        for mid in grouped:
            mem = store.find(mid)
            if mem:
                content_map[mid] = mem.content
    except Exception:
        pass
    for mid, evs in grouped.items():
        if mid not in content_map:
            for ev in evs:
                if ev["event"] == "memory_write" and ev.get("content_summary"):
                    content_map[mid] = ev["content_summary"]
                    break

    print(summarize(records, grouped, content_map, store))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(records, grouped, content_map, str(log_path), store), encoding="utf-8")
    print(f"\n[ok] HTML 报告已写出: {out}  ({len(grouped)} 条记忆轨迹)")


if __name__ == "__main__":
    main()
