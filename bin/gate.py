#!/usr/bin/env python3
"""Thin transitional wrapper over the ported kernel gate (issue #2, point 1).

The v4 math and the era registry live in ratchet.kernel.gate and
ratchet.kernel.era; this wrapper only wires repo-rooted paths and the CLI
contract the bash-era gate.py had. It is deleted once the click verb
covers this workflow and the step-1 test suite is green.

Usage:
  bin/gate.py <baseline-label> <candidate-label> [--min-k 2] [--effect 0.15]
  bin/gate.py --set-active <baseline-label> [--configs a.yml,b.yml]

Exit 0 = PROMOTE, 1 = REJECT, 2 = usage/data error (era mismatches are
data errors, never verdicts).
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchet.kernel.era import EraError, build_registry, check_era, load_registry
from ratchet.kernel.gate import GateDataError, decide, load_results, write_manifest


def head_commit(root):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()


def main(root=None):
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    active = root / "runs" / "ACTIVE_BASELINE"

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

    try:
        if args.set_active:
            label = args.set_active
            results = load_results(root / "runs" / label / "results.jsonl")
            split = json.loads((root / "split.json").read_text())
            reg = build_registry(
                label=label, results=results, split=split,
                configs=[c for c in args.configs.split(",") if c],
                config_root=root, set_at_commit=head_commit(root),
                ts=int(time.time()),
            )
            active.write_text(json.dumps(reg, indent=1) + "\n")
            print(f"active baseline -> {label} (split v{split['split_version']}, "
                  f"gate v{reg['gate_version']}, model {reg['model']})")
            print(f"registry: {active} — commit it (git add -f) with the baseline's ledger entry")
            return
        if not args.baseline or not args.candidate:
            ap.error("baseline and candidate are required (or use --set-active)")

        split = json.loads((root / "split.json").read_text())
        base = load_results(root / "runs" / args.baseline / "results.jsonl")
        cand = load_results(root / "runs" / args.candidate / "results.jsonl")
        registry = load_registry(active)
        check_era(registry, baseline_label=args.baseline, split=split,
                  base=base, cand=cand, config_root=root)

        manifest, code = decide(
            split, base, cand, baseline_label=args.baseline,
            candidate_label=args.candidate, min_k=args.min_k,
            effect=args.effect, rollback_target=head_commit(root),
        )
        mpath = root / "runs" / args.candidate / "manifest.json"
        write_manifest(mpath, manifest)
    except (EraError, GateDataError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    print(f"=== GATE: {manifest['decision']} ({args.candidate} vs {args.baseline})")
    for r in manifest["reasons"]:
        print(f"  - {r}")
    for a in manifest["improved_axes"]:
        print(f"  + improved: {a}")
    print(f"manifest: {mpath}")
    sys.exit(code)


if __name__ == "__main__":
    main()
