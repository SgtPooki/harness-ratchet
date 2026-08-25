#!/usr/bin/env python3
"""The ratchet's pawl: mechanical promote/reject for a candidate run vs baseline.

Usage:
  bin/gate.py <baseline-label> <candidate-label> [--min-k 2] [--effect 0.15]
  bin/gate.py --set-active <baseline-label> [--configs a.yml,b.yml]

Era registry (v1.3): runs/ACTIVE_BASELINE pins the comparison baseline —
label, split_version, gate_version, model, and sha256 of the standing config
overlays. Every gate invocation verifies the requested baseline against the
registry instead of operator memory; mismatches are data errors (exit 2),
never verdicts. Re-point deliberately with --set-active after recording a new
baseline (a split or gate change REQUIRES a new baseline first).

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
       by more than --effect on held_in OR held_out (held-out is a floor,
       never a target);
    5. sentinel report is advisory (printed, never gates) — sentinels are
       monitored for drift, not optimized.

Emits runs/<candidate>/manifest.json (immutable: refuses to overwrite) with
the decision, per-task evidence, split_version, and rollback target.
Exit 0 = PROMOTE, 1 = REJECT, 2 = usage/data error.
"""

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_VERSION = 4
ACTIVE = ROOT / "runs" / "ACTIVE_BASELINE"


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


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def set_active(label, configs):
    rows = load_results(label)
    models = sorted({r["model"] for rs in rows.values() for r in rs})
    if len(models) != 1:
        sys.exit(f"gate: {label} mixes models {models}; a baseline must be single-model")
    split = json.loads((ROOT / "split.json").read_text())
    cfg_hashes = {}
    for c in configs:
        p = ROOT / c
        if not p.is_file():
            sys.exit(f"gate: config {c} not found")
        cfg_hashes[c] = sha256_file(p)
    reg = {
        "label": label, "split_version": split["split_version"],
        "gate_version": GATE_VERSION, "model": models[0],
        "config_sha256": cfg_hashes, "set_at_commit": head_commit(),
        "ts": int(time.time()),
    }
    ACTIVE.write_text(json.dumps(reg, indent=1) + "\n")
    print(f"active baseline -> {label} (split v{split['split_version']}, "
          f"gate v{GATE_VERSION}, model {models[0]})")
    print(f"registry: {ACTIVE} — commit it (git add -f) with the baseline's ledger entry")


def check_era(args, split, base, cand):
    """Registry checks: all failures are data errors (exit 2), never verdicts."""
    if not ACTIVE.is_file():
        sys.exit("gate: no runs/ACTIVE_BASELINE — record one with "
                 "bin/gate.py --set-active <label>")
    reg = json.loads(ACTIVE.read_text())
    errs = []
    if args.baseline != reg["label"]:
        errs.append(f"baseline {args.baseline!r} is not the active baseline "
                    f"{reg['label']!r} (re-point with --set-active if deliberate)")
    if reg["split_version"] != split["split_version"]:
        errs.append(f"era mismatch: registry split v{reg['split_version']} vs "
                    f"split.json v{split['split_version']} — record a new baseline first")
    if reg["gate_version"] != GATE_VERSION:
        errs.append(f"gate changed (registry v{reg['gate_version']} vs v{GATE_VERSION}) "
                    "— re-record the baseline under the current gate")
    for c, want in reg.get("config_sha256", {}).items():
        p = ROOT / c
        have = sha256_file(p) if p.is_file() else "<missing>"
        if have != want:
            errs.append(f"config ancestry broken: {c} changed since the baseline "
                        "was recorded — the comparison is cross-era")
    models = sorted({r["model"] for rs in list(base.values()) + list(cand.values()) for r in rs})
    if models != [reg["model"]]:
        errs.append(f"model mismatch: registry {reg['model']!r} vs run rows {models}")
    if errs:
        sys.exit("gate: era-registry check failed:\n  - " + "\n  - ".join(errs))
    return reg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", nargs="?")
    ap.add_argument("candidate", nargs="?")
    ap.add_argument("--min-k", type=int, default=2)
    ap.add_argument("--effect", type=float, default=0.15,
                    help="minimum relative improvement on a soft axis")
    ap.add_argument("--set-active", metavar="LABEL",
                    help="point runs/ACTIVE_BASELINE at LABEL and exit")
    ap.add_argument("--configs", default="mutations/eval-isolation.yml,mutations/ctxslim-v1.yml",
                    help="comma-separated standing config overlays to pin (with --set-active)")
    args = ap.parse_args()

    if args.set_active:
        set_active(args.set_active, [c for c in args.configs.split(",") if c])
        return
    if not args.baseline or not args.candidate:
        ap.error("baseline and candidate are required (or use --set-active)")

    split = json.loads((ROOT / "split.json").read_text())
    base, cand = load_results(args.baseline), load_results(args.candidate)
    check_era(args, split, base, cand)

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

    # 4b. held_out soft-axis regression floor (v1.2, from the ctxslim-v1
    # promotion gap: held-out 08 tokens rose ~52% ungated). Held-out
    # improvements never count toward 'improved' — this is a floor, not a
    # target.
    if b_out and c_out:
        for axis in ("duration_p50", "tokens_out_p50", "tokens_in_p50"):
            b_tot = sum(v[axis] for v in b_out.values())
            c_tot = sum(v[axis] for v in c_out.values())
            if b_tot > 0:
                delta = (b_tot - c_tot) / b_tot
                evidence.setdefault("held_out_soft_axes", {})[axis] = {
                    "baseline": b_tot, "candidate": c_tot, "rel_change": round(delta, 4)}
                if delta <= -args.effect:
                    reasons.append(f"held_out soft-axis regression: {axis} {b_tot}->{c_tot}")

    # 5. sentinel report (advisory only)
    sent = {t: {"baseline": agg(base[t]) if base.get(t) else None,
                "candidate": agg(cand[t]) if cand.get(t) else None}
            for t in split["sentinel"]}

    decision = "PROMOTE" if not reasons else "REJECT"
    rollback = head_commit()
    manifest = {
        "gate_version": GATE_VERSION, "split_version": split["split_version"],
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
