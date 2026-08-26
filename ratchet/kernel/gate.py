"""The ratchet's pawl: mechanical promote/reject for a candidate vs baseline.

Line-faithful port of bin/gate.py at gate_version 4 (issue #2, point 6:
port, don't redesign; the math must reproduce the frozen golden fixtures
in tests/fixtures/gate/expected.json exactly).

PROMOTE requires ALL of:
  1. coverage: every held_in and held_out task present in BOTH sides with
     >= min_k rollouts each (insufficient coverage is itself a REJECT);
  2. held_out pass floor (HARD): candidate pass rate per held_out task >=
     baseline;
  3. held_in non-regression on pass (HARD);
  4. improvement: a held_in pass-rate gain counts, OR at least one soft
     axis (duration_p50, tokens_out_p50, tokens_in_p50) improves by >=
     effect (relative) on held_in aggregate, with no soft axis regressing
     by more than effect on held_in OR held_out (held-out is a floor,
     never a target);
  5. sentinel report is advisory (recorded, never gates).

Data problems (missing results, immutable-manifest overwrite) raise
GateDataError; callers map it to exit 2, never to a verdict.
"""

import json
import statistics
from pathlib import Path

GATE_VERSION = 4
SOFT_AXES = ("duration_p50", "tokens_out_p50", "tokens_in_p50")


class GateDataError(Exception):
    """Bad or missing input data: a usage/data error (exit 2), never a verdict."""


def load_results(path: Path) -> dict[str, list[dict]]:
    """Parse one results.jsonl into rows grouped by task."""
    path = Path(path)
    if not path.is_file():
        raise GateDataError(f"gate: no results at {path}")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)
    return by_task


def agg(rows: list[dict]) -> dict:
    return {
        "k": len(rows),
        "pass_rate": sum(1 for r in rows if r["pass"]) / len(rows),
        "duration_p50": statistics.median(r["duration_s"] for r in rows),
        "tokens_out_p50": statistics.median(r.get("tokens_out", 0) for r in rows),
        "tokens_in_p50": statistics.median(r.get("tokens_in", 0) for r in rows),
    }


def reject_certain(split: dict, base: dict[str, list[dict]],
                   cand_partial: dict[str, list[dict]], planned_k: int) -> str | None:
    """The #12 early-abort check: is REJECT already certain from a partial
    candidate sweep, whatever the remaining rollouts do?

    Exactly two pre-registered conditions, both pure pass-rate arithmetic
    (the #12 resolution, decision 2): for a held-in or held-out task, even
    if every remaining planned rollout passes, the candidate pass rate ends
    strictly below the baseline's (equality is non-regression and never
    aborts). Soft axes are deliberately excluded: medians can move until
    the final rollout. Returns the triggering condition as a string, or
    None. Shares no state with decide(); callers gate the partial results
    as usual (incomplete coverage is already a REJECT under v4 rules).
    """
    for role in ("held_in", "held_out"):
        for t in split[role]:
            b_rows = base.get(t)
            if not b_rows:
                continue
            base_rate = sum(1 for r in b_rows if r["pass"]) / len(b_rows)
            rows = cand_partial.get(t, [])
            passes = sum(1 for r in rows if r["pass"])
            best = (passes + (planned_k - len(rows))) / planned_k
            if best < base_rate:
                return (f"{role} pass certainty: {t} best possible "
                        f"{passes + planned_k - len(rows)}/{planned_k} < "
                        f"baseline {base_rate:.2f}")
    return None


def decide(split: dict, base: dict[str, list[dict]], cand: dict[str, list[dict]],
           *, baseline_label: str, candidate_label: str, min_k: int = 2,
           effect: float = 0.15, rollback_target: str = "") -> tuple[dict, int]:
    """Run the v4 gate math. Returns (manifest, exit_code): 0 PROMOTE, 1 REJECT."""
    reasons, evidence = [], {}

    # 1. coverage
    gated_tasks = split["held_in"] + split["held_out"]
    for t in gated_tasks:
        for side, data in (("baseline", base), ("candidate", cand)):
            k = len(data.get(t, []))
            if k < min_k:
                reasons.append(f"coverage: {side} has k={k}<{min_k} for {t}")

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
        for axis in SOFT_AXES:
            b_tot = sum(v[axis] for v in b_in.values())
            c_tot = sum(v[axis] for v in c_in.values())
            if b_tot > 0:
                delta = (b_tot - c_tot) / b_tot
                evidence.setdefault("soft_axes", {})[axis] = {
                    "baseline": b_tot, "candidate": c_tot, "rel_improvement": round(delta, 4)}
                if delta >= effect:
                    improved.append(axis)
                elif delta <= -effect:
                    reasons.append(f"soft-axis regression: {axis} {b_tot}->{c_tot}")
    if not improved and not reasons:
        reasons.append(f"no soft axis improved by >={effect:.0%}")

    # 4b. held_out soft-axis regression floor (v1.2, from the ctxslim-v1
    # promotion gap: held-out 08 tokens rose ~52% ungated). Held-out
    # improvements never count toward 'improved' — this is a floor, not a
    # target.
    if b_out and c_out:
        for axis in SOFT_AXES:
            b_tot = sum(v[axis] for v in b_out.values())
            c_tot = sum(v[axis] for v in c_out.values())
            if b_tot > 0:
                delta = (b_tot - c_tot) / b_tot
                evidence.setdefault("held_out_soft_axes", {})[axis] = {
                    "baseline": b_tot, "candidate": c_tot, "rel_change": round(delta, 4)}
                if delta <= -effect:
                    reasons.append(f"held_out soft-axis regression: {axis} {b_tot}->{c_tot}")

    # 5. sentinel report (advisory only)
    sent = {t: {"baseline": agg(base[t]) if base.get(t) else None,
                "candidate": agg(cand[t]) if cand.get(t) else None}
            for t in split["sentinel"]}

    decision = "PROMOTE" if not reasons else "REJECT"
    manifest = {
        "gate_version": GATE_VERSION, "split_version": split["split_version"],
        "baseline": baseline_label, "candidate": candidate_label,
        "min_k": min_k, "effect_threshold": effect,
        "decision": decision, "reasons": reasons, "improved_axes": improved,
        "evidence": evidence, "sentinel_advisory": sent,
        "rollback_target": rollback_target,
    }
    return manifest, 0 if decision == "PROMOTE" else 1


def write_manifest(path: Path, manifest: dict) -> None:
    """Write an immutable manifest; refusing to overwrite is invariant 4."""
    path = Path(path)
    if path.exists():
        raise GateDataError(f"gate: {path} already exists (manifests are immutable)")
    path.write_text(json.dumps(manifest, indent=1))
