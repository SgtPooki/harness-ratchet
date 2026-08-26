#!/usr/bin/env python3
"""Freeze golden gate fixtures from the pre-port bin/gate.py (gate_version 4).

Run ONCE, before the Python port of the gate exists, per the runner-rewrite
resolution (issue #2, point 6): expected outputs are derived from the current
bin/gate.py and frozen as committed fixtures; the ported gate must reproduce
them exactly. Never re-run this script against the ported code — that would
turn the port into its own oracle.

What it does:
  1. Copies every runs/<label>/results.jsonl and split.json into this
     directory (runs/ is gitignored, so CI needs committed copies).
  2. For every ordered pair of distinct labels, runs the v4 gate MATH
     (era-registry check bypassed: it depends on live operator state, not
     math; its exit-2 behavior is covered by dedicated era tests) with the
     default parameters min_k=2, effect=0.15.
  3. Writes expected.json: {"<baseline>__<candidate>": {"exit": 0|1,
     "manifest": {...}}} with rollback_target pinned to 40 zeros.
"""

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PINNED_COMMIT = "0" * 40


def load_gate_module(path):
    spec = importlib.util.spec_from_file_location("legacy_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    labels = sorted(
        p.parent.name for p in (REPO / "runs").glob("*/results.jsonl")
    )
    if not labels:
        sys.exit("freeze: no runs/*/results.jsonl found")

    # 1. snapshot inputs
    (HERE / "runs").mkdir(exist_ok=True)
    for label in labels:
        dst = HERE / "runs" / label
        dst.mkdir(exist_ok=True)
        shutil.copy(REPO / "runs" / label / "results.jsonl", dst / "results.jsonl")
    shutil.copy(REPO / "split.json", HERE / "split.json")

    gate = load_gate_module(REPO / "bin" / "gate.py")

    # 2. run the math in a scratch ROOT so real manifests stay untouched
    scratch = Path(tempfile.mkdtemp(prefix="gate-freeze-"))
    shutil.copy(REPO / "split.json", scratch / "split.json")
    for label in labels:
        d = scratch / "runs" / label
        d.mkdir(parents=True)
        shutil.copy(REPO / "runs" / label / "results.jsonl", d / "results.jsonl")

    gate.ROOT = scratch
    gate.check_era = lambda *a, **k: None
    gate.head_commit = lambda: PINNED_COMMIT

    expected = {}
    for base in labels:
        for cand in labels:
            if base == cand:
                continue
            sys.argv = ["gate.py", base, cand]
            code = 2
            try:
                gate.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
            mpath = scratch / "runs" / cand / "manifest.json"
            manifest = json.loads(mpath.read_text())
            mpath.unlink()
            expected[f"{base}__{cand}"] = {"exit": code, "manifest": manifest}

    (HERE / "expected.json").write_text(
        json.dumps(expected, indent=1, sort_keys=True) + "\n"
    )
    shutil.rmtree(scratch)
    print(f"froze {len(expected)} pairs over {len(labels)} labels -> expected.json")


if __name__ == "__main__":
    main()
