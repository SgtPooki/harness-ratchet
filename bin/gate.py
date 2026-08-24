#!/usr/bin/env python3
"""The ratchet's pawl: mechanical promote/reject for a candidate run vs baseline.

Usage: bin/gate.py <baseline-label> <candidate-label> [--min-k 2] [--effect 0.15]

Reads runs/<label>/results.jsonl for both labels and split.json, then decides:

  PROMOTE requires ALL of:
    1. coverage: every held_in and held_out task present in BOTH labels with
       >= min-k rollouts each (insufficient coverage is itself a REJECT);
    2. held_out pass floor (HARD): candidate pass rate per held_out task >=
       baseline — laziness that breaks correctness dies here;
    3. held_in non-regression on pass (HARD);
    4. improvement: a held_in pass-rate gain counts, OR at least one soft
       axis (duration_p50, tokens_out_p50, tokens_in_p50) improves by >=
       --effect (relative) on held_in aggregate, with no soft axis regressing
       by more than --effect;
    5. sentinel report is advisory (printed, never gates) — sentinels are
       monitored for drift, not optimized.

Emits runs/<candidate>/manifest.json (immutable: refuses to overwrite) with
the decision, per-task evidence, split_version, and rollback target.
Exit 0 = PROMOTE, 1 = REJECT, 2 = usage/data error.
"""

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_results(label):
    p = ROOT / "runs" / label / "results.jsonl"
    if not p.is_file():
        sys.exit(f"gate: no results at {p}")
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    by_task = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)
    return by_task


def agg(rows):
    return {
        "k": len(rows),
        "pass_rate": sum(1 for r in rows if r["pass"]) / len(rows),
        "duration_p50": statistics.median(r["duration_s"] for r in rows),
        "tokens_out_p50": statistics.median(r.get("tokens_out", 0) for r in rows),
        "tokens_in_p50": statistics.median(r.get("tokens_in", 0) for r in rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--min-k", type=int, default=2)
    ap.add_argument("--effect", type=float, default=0.15,
                    help="minimum relative improvement on a soft axis")
    args = ap.parse_args()

    split = json.loads((ROOT / "split.json").read_text())
    base, cand = load_results(args.baseline), load_results(args.candidate)

    reasons, evidence = [], {}

    # 1. coverage
    gated_tasks = split["held_in"] + split["held_out"]
    for t in gated_tasks:
        for side, data in (("baseline", base), ("candidate", cand)):
            k = len(data.get(t, []))
            if k < args.min_k:
                reasons.append(f"coverage: {side} has k={k}<{args.min_k} for {t}")

    def side_agg(data, tasks):
        return {t: agg(data[t]) for t in tasks if data.get(t)}

    b_in, c_in = side_agg(base, split["held_in"]), side_agg(cand, split["held_in"])
    b_out, c_out = side_agg(base, split["held_out"]), side_agg(cand, split["held_out"])
    evidence = {"held_in": {"baseline": b_in, "candidate": c_in},
                "held_out": {"baseline": b_out, "candidate": c_out}}

    # 2. held_out hard floor
    for t in split["held_out"]:
        if t in b_out and t in c_out and c_out[t]["pass_rate"] < b_out[t]["pass_rate"]:
            reasons.append(f"held_out regression: {t} pass "
                           f"{b_out[t]['pass_rate']:.2f}->{c_out[t]['pass_rate']:.2f}")

    # 3. held_in pass non-regression
    for t in split["held_in"]:
        if t in b_in and t in c_in and c_in[t]["pass_rate"] < b_in[t]["pass_rate"]:
            reasons.append(f"held_in regression: {t} pass "
                           f"{b_in[t]['pass_rate']:.2f}->{c_in[t]['pass_rate']:.2f}")

    # 4. improvement: a held_in pass-rate GAIN counts (a mutation that fixes a
    # failing task must be promotable even at unchanged duration/tokens), else
    # at least one soft axis must improve by the effect threshold.
    improved = []
    if b_in and c_in:
        b_pass = sum(v["pass_rate"] for v in b_in.values())
        c_pass = sum(v["pass_rate"] for v in c_in.values())
        if c_pass > b_pass:
            improved.append("pass_rate")
    if b_in and c_in and not any(r.startswith("coverage") for r in reasons):
        for axis in ("duration_p50", "tokens_out_p50", "tokens_in_p50"):
            b_tot = sum(v[axis] for v in b_in.values())
            c_tot = sum(v[axis] for v in c_in.values())
            if b_tot > 0:
                delta = (b_tot - c_tot) / b_tot
                evidence.setdefault("soft_axes", {})[axis] = {
                    "baseline": b_tot, "candidate": c_tot, "rel_improvement": round(delta, 4)}
                if delta >= args.effect:
                    improved.append(axis)
                elif delta <= -args.effect:
                    reasons.append(f"soft-axis regression: {axis} {b_tot}->{c_tot}")
    if not improved and not reasons:
        reasons.append(f"no soft axis improved by >={args.effect:.0%}")

    # 5. sentinel report (advisory only)
    sent = {t: {"baseline": agg(base[t]) if base.get(t) else None,
                "candidate": agg(cand[t]) if cand.get(t) else None}
            for t in split["sentinel"]}

    decision = "PROMOTE" if not reasons else "REJECT"
    rollback = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    manifest = {
        "gate_version": 2, "split_version": split["split_version"],
        "baseline": args.baseline, "candidate": args.candidate,
        "min_k": args.min_k, "effect_threshold": args.effect,
        "decision": decision, "reasons": reasons, "improved_axes": improved,
        "evidence": evidence, "sentinel_advisory": sent,
        "rollback_target": rollback,
    }
    mpath = ROOT / "runs" / args.candidate / "manifest.json"
    if mpath.exists():
        sys.exit(f"gate: {mpath} already exists (manifests are immutable)")
    mpath.write_text(json.dumps(manifest, indent=1))

    print(f"=== GATE: {decision} ({args.candidate} vs {args.baseline})")
    for r in reasons:
        print(f"  - {r}")
    for a in improved:
        print(f"  + improved: {a}")
    print(f"manifest: {mpath}")
    sys.exit(0 if decision == "PROMOTE" else 1)


if __name__ == "__main__":
    main()
