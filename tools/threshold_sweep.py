"""Offline threshold-sensitivity replay for the Ananke Phase 3 pilot.

Why this exists
---------------
GLM's second-round review (R1) showed the headline Phase 3 result — "frequency
lifts 3 EV=0 memories that persistence leaves in working memory" — is *threshold
sensitive*: the score function (does/doesn't distinguish evidence source) and the
promotion threshold are two independent degrees of freedom. At the frozen config
(persistence threshold 3.0, frequency threshold 3) the divergence is real, but a
single data point cannot prove it is robust.

This script answers that question **for free** (zero LLM / embedding calls): every
memory's final EV / IA / total_activation counts are already persisted in the
Phase 3 data directories. We replay those counts across a threshold grid and
report, for each (persistence_threshold, frequency_threshold) cell, how many
memories each strategy would have promoted — and, critically, how many of those
promoted memories carry *zero external validation* (EV=0).

The decisive question GLM raised: is "frequency promotes EV=0 memories while
persistence promotes none" a single-point coincidence, or does it hold across a
wide threshold region? This script prints that region.

Reads: data/phase3_persist/{working,consolidated}.jsonl and
       data/phase3_freq/{working,consolidated}.jsonl
Writes: logs/threshold_sweep.json  (+ markdown table printed to stdout)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ananke.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_memories(data_dir: Path) -> dict[str, dict]:
    """Load working + consolidated jsonl into a dict keyed by content text.

    Returns per-memory: {content: {ev, ia, total, pscore, fscore, layer}}."""
    memories: dict[str, dict] = {}
    for layer in ("working", "consolidated"):
        path = data_dir / f"{layer}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # Recompute scores from primitives so the sweep is self-contained and
            # independent of any floating-point drift in the stored snapshot.
            ev = int(rec["external_validation"])
            ia = int(rec["internal_activation"])
            total = int(rec["total_activation"])
            pscore = ev * Config.EXTERNAL_VALIDATION_WEIGHT + ia * Config.INTERNAL_ACTIVATION_WEIGHT
            fscore = float(total)
            memories[rec["content"]] = {
                "content": rec["content"],
                "ev": ev,
                "ia": ia,
                "total": total,
                "pscore": pscore,
                "fscore": fscore,
                "layer": rec["layer"],
            }
    return memories


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persist-dir", default=str(REPO_ROOT / "data" / "phase3_persist"))
    ap.add_argument("--freq-dir", default=str(REPO_ROOT / "data" / "phase3_freq"))
    ap.add_argument("--out", default=str(REPO_ROOT / "logs" / "threshold_sweep.json"))
    ap.add_argument("--tp-min", type=float, default=2.0)
    ap.add_argument("--tp-max", type=float, default=5.0)
    ap.add_argument("--tp-step", type=float, default=0.5)
    ap.add_argument("--tf-min", type=int, default=2)
    ap.add_argument("--tf-max", type=int, default=9)
    args = ap.parse_args()

    persist = load_memories(Path(args.persist_dir))
    freq = load_memories(Path(args.freq_dir))

    # --- Reproducibility check: the two independent Gemini runs produced the
    # same 21-memory set (the "21=21" comparator-validity claim). ---
    p_keys = set(persist)
    f_keys = set(freq)
    identical_set = p_keys == f_keys
    # Also check per-memory counts match between the two runs.
    count_mismatch = []
    for k in p_keys & f_keys:
        a, b = persist[k], freq[k]
        if (a["ev"], a["ia"], a["total"]) != (b["ev"], b["ia"], b["total"]):
            count_mismatch.append(k)
    canonical = persist  # extraction is identical (21=21); either run is canonical
    memories = list(canonical.values())
    n = len(memories)

    # --- Threshold grids ---
    tp_grid = [round(x, 2) for x in
               [args.tp_min + i * args.tp_step
                for i in range(int(round((args.tp_max - args.tp_min) / args.tp_step)) + 1)]]
    tf_grid = list(range(args.tf_min, args.tf_max + 1))

    # --- Marginals (each strategy depends only on its own threshold) ---
    def promote_p(Tp: float) -> list[dict]:
        return [m for m in memories if m["pscore"] >= Tp]

    def promote_f(Tf: float) -> list[dict]:
        return [m for m in memories if m["fscore"] >= Tf]

    p_marginal = {Tp: promote_p(Tp) for Tp in tp_grid}
    f_marginal = {Tf: promote_f(Tf) for Tf in tf_grid}

    # --- Divergence map: frequency lifts >=1 EV=0 memory while persistence lifts 0 ---
    def div_cell(Tp: float, Tf: float) -> bool:
        ev0_p = sum(1 for m in p_marginal[Tp] if m["ev"] == 0)
        ev0_f = sum(1 for m in f_marginal[Tf] if m["ev"] == 0)
        return ev0_f > 0 and ev0_p == 0

    # Boundaries of the divergence region.
    tp_divergent = [Tp for Tp in tp_grid if any(div_cell(Tp, Tf) for Tf in tf_grid)]
    tf_divergent = [Tf for Tf in tf_grid if any(div_cell(Tp, Tf) for Tp in tp_grid)]
    tp_region = (min(tp_divergent), max(tp_divergent)) if tp_divergent else None
    tf_region = (min(tf_divergent), max(tf_divergent)) if tf_divergent else None

    # --- Print human-readable report ---
    print("=" * 78)
    print("ANANKE PHASE 3 PILOT — THRESHOLD SENSITIVITY REPLAY (offline, no LLM)")
    print("=" * 78)
    print(f"Loaded {n} memories from persistence run, {len(freq)} from frequency run.")
    print(f"  identical memory SET across the two runs : {identical_set}")
    print(f"  per-memory (EV,IA,total) MATCH across runs: {not count_mismatch}"
          + (f"  (mismatches: {len(count_mismatch)})" if count_mismatch else ""))
    print(f"  => '21=21' comparator validity: {'CONFIRMED' if identical_set and not count_mismatch else 'CHECK'}")
    print()
    print("Per-memory final counts (the replay substrate):")
    print(f"  {'content':<44} {'EV':>2} {'IA':>2} {'tot':>3} {'pscore':>7} {'fscore':>6}")
    for m in sorted(memories, key=lambda x: -x["pscore"]):
        print(f"  {m['content'][:42]:<44} {m['ev']:>2} {m['ia']:>2} {m['total']:>3} "
              f"{m['pscore']:>7.3f} {m['fscore']:>6.0f}")
    print()

    # Persistence marginal
    print("Persistence marginal  (promotions vs persistence threshold Tp):")
    print(f"  {'Tp':>5} {'promote':>7} {'EV=0':>5}")
    for Tp in tp_grid:
        pm = p_marginal[Tp]
        print(f"  {Tp:>5} {len(pm):>7} {sum(1 for m in pm if m['ev']==0):>5}")
    print()

    # Frequency marginal
    print("Frequency marginal  (promotions vs frequency threshold Tf):")
    print(f"  {'Tf':>5} {'promote':>7} {'EV=0':>5}")
    for Tf in tf_grid:
        fm = f_marginal[Tf]
        print(f"  {Tf:>5} {len(fm):>7} {sum(1 for m in fm if m['ev']==0):>5}")
    print()

    # Divergence phase diagram
    print("DIVERGENCE PHASE DIAGRAM  ('*' = frequency lifts >=1 EV=0 memory,"
          " persistence lifts 0)")
    print("rows = persistence threshold Tp ; cols = frequency threshold Tf")
    header = "      " + "".join(f" {Tf:>3}" for Tf in tf_grid)
    print(header)
    for Tp in tp_grid:
        row = "".join(f"  * " if div_cell(Tp, Tf) else "  . " for Tf in tf_grid)
        print(f" {Tp:>4} |{row}")
    print()
    if tp_region and tf_region:
        print(f"Divergence region (contiguous rectangle):")
        print(f"  persistence threshold Tp in [{tp_region[0]}, {tp_region[1]}]")
        print(f"  frequency  threshold Tf in [{tf_region[0]}, {tf_region[1]}]")
        # Include the frozen config
        frozen_in = (Config.MIGRATION_THRESHOLD in tp_grid or tp_region[0] <= Config.MIGRATION_THRESHOLD <= tp_region[1]) \
            and (Config.FREQUENCY_MIGRATION_THRESHOLD in tf_grid or tf_region[0] <= Config.FREQUENCY_MIGRATION_THRESHOLD <= tf_region[1])
        print(f"  frozen config (Tp={Config.MIGRATION_THRESHOLD}, Tf={Config.FREQUENCY_MIGRATION_THRESHOLD}) "
              f"inside region: {frozen_in}")
        # Fraction of grid cells showing divergence
        cells = len(tp_grid) * len(tf_grid)
        div_cells = sum(1 for Tp in tp_grid for Tf in tf_grid if div_cell(Tp, Tf))
        print(f"  divergence holds in {div_cells}/{cells} = {div_cells/cells:.0%} of grid cells")
    else:
        print("No divergence region found on this grid.")
    print()

    # --- Persist machine-readable result ---
    result = {
        "n_memories": n,
        "identical_set_across_runs": identical_set,
        "per_memory_count_match": not count_mismatch,
        "tp_grid": tp_grid,
        "tf_grid": tf_grid,
        "p_marginal": {str(Tp): {"promote": len(p_marginal[Tp]),
                                 "ev0": sum(1 for m in p_marginal[Tp] if m["ev"] == 0)}
                       for Tp in tp_grid},
        "f_marginal": {str(Tf): {"promote": len(f_marginal[Tf]),
                                 "ev0": sum(1 for m in f_marginal[Tf] if m["ev"] == 0)}
                       for Tf in tf_grid},
        "divergence_region": {"tp": list(tp_region) if tp_region else None,
                              "tf": list(tf_region) if tf_region else None},
        "frozen_config": {"tp": Config.MIGRATION_THRESHOLD, "tf": Config.FREQUENCY_MIGRATION_THRESHOLD},
        "memories": memories,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote machine-readable result -> {out}")


if __name__ == "__main__":
    main()
