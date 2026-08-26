"""One ratchet click: mutate -> rollouts -> gate -> restore (issue #2, point 4).

Structured op arguments (exactly one op per candidate — invariant 5 is
enforced by construction: the CLI accepts one op kind with one payload).
Invariant 3 (and the invariant-7 corollary) is enforced PRE-SWEEP: a
mutation motivated by a sentinel task invalidates the candidate before any
rollout, and a held-out motivation is illegal for the same mechanical
reason (mining the floor).

The op applies under trap-restore for the duration of the candidate sweep
and is ALWAYS restored afterward; a PROMOTE verdict means the operator
makes the mutation standing (config-overlay -> overlays.standing, then a
new baseline) — the click never edits personal config permanently.

The sweep runs the #12 resolution flow: held-in first then held-out,
cheapest first (decision 3); k=2 screening with two more rollouts
appended per task on a screening PROMOTE, one gate pass over the
combined four (decision 4); early abort the moment REJECT is certain
(decision 2, kernel reject_certain); sentinels only after the gate over
held-in and held-out says PROMOTE, every reject skipping them with the
skip recorded (decision 1); sweep_cost and concurrency in the manifest
(decisions 6 and 7). Gate math itself is untouched at v4.

The append-system-prompt channel may be clicked locally (with a probe on
record) but is registry-inadmissible until a finding-format version bump
(#5 amendment); its op.json is marked accordingly.
"""

import hashlib
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from ratchet.config import RatchetConfig
from ratchet.kernel.digests import canonical_json
from ratchet.kernel.era import check_era, load_registry
from ratchet.kernel.gate import (GateDataError, decide, load_results,
                                 reject_certain, write_manifest)
from ratchet.runner.base import CONCURRENCY, RolloutSpec, sweep_cost
from ratchet.runner.omp import OmpRunner

SCREENING_K = 2   # #12 decision 4: click sweeps screen at k=2 by default
FULL_K = 4        # escalation target; only a k=4 PROMOTE promotes
from ratchet.runner.ops import ConfigOverlayOp, ModelParamOp, OpError, RulesAppendOp

OP_KINDS = ("config-overlay", "model-param", "rules", "append-system-prompt")
REGISTRY_INADMISSIBLE = {"append-system-prompt"}


class ClickError(Exception):
    """Pre-sweep invalidation (invariants 3/5/7, bad op): exit 2, no rollouts."""


@dataclass
class ClickOp:
    kind: str
    payload: dict                      # kind-specific, recorded in op.json

    def digest12(self) -> str:
        doc = {"kind": self.kind, **self.payload}
        return hashlib.sha256(canonical_json(doc).encode()).hexdigest()[:12]


def check_motivation(split: dict, motivated_by: str) -> None:
    """Invariant 3: sentinel-targeted mutations are invalid. Invariant 7:
    a held-out motivation is optimizing against the floor."""
    if motivated_by in split.get("sentinel", []):
        raise ClickError(
            f"invariant 3: {motivated_by} is a sentinel; a mutation cycle "
            "targeting a sentinel invalidates the candidate")
    if motivated_by in split.get("held_out", []):
        raise ClickError(
            f"invariant 7: {motivated_by} is held-out; mining a held-out "
            "failure to design a mutation is optimizing against the floor")
    known = (split.get("held_in", []) + split.get("held_out", [])
             + split.get("sentinel", []))
    if motivated_by not in known:
        raise ClickError(f"motivating task {motivated_by!r} is not in the split")


def resolve_task_dir(cfg: RatchetConfig, task_id: str) -> Path:
    for pack in (cfg.bank_pack, cfg.bootstrap_pack):
        d = Path(pack) / task_id
        if d.is_dir():
            return d
    raise ClickError(f"task {task_id!r} not found in bank or bootstrap pack")


def build_op(cfg: RatchetConfig, runner: OmpRunner, op: ClickOp):
    """Return (surface_op_or_None, extra_config, extra_sys) for the sweep."""
    if op.kind == "config-overlay":
        overlay = Path(op.payload["overlay"])
        return ConfigOverlayOp(overlay), overlay, None
    if op.kind == "model-param":
        p = op.payload
        return ModelParamOp(runner.models_yml, p["omp_model_alias"], p["yaml_id"],
                            p["key"], p["value"]), None, None
    if op.kind == "rules":
        return RulesAppendOp(runner.rules_path, op.payload["text"],
                             op.digest12()), None, None
    if op.kind == "append-system-prompt":
        return None, None, op.payload["text"]
    raise ClickError(f"unknown op kind {op.kind!r}")


def _pass_rate(rows: list[dict]) -> float:
    return sum(1 for r in rows if r["pass"]) / len(rows)


@dataclass
class SweepResult:
    """Everything one #12-flow candidate sweep produced and decided."""
    screening_k: int
    final_k: int
    escalated: bool
    screening_verdict: str | None
    aborted: bool
    abort_condition: str | None
    promote_so_far: bool          # held-in + held-out gate said PROMOTE
    rows: list                    # TelemetryRow, in execution order
    task_order: list[str]
    elapsed_wall_s: int


def run_sweep(split: dict, base: dict[str, list[dict]], rollout, *,
              screening_k: int, baseline_label: str, candidate: str,
              min_k: int, effect: float) -> SweepResult:
    """The #12 sweep flow: screen at screening_k over held-in then held-out
    (cheapest first), abort on certainty, escalate to FULL_K only on a
    screening PROMOTE, and run sentinels only once the gate over held-in
    plus held-out says PROMOTE. `rollout(task_id, i)` runs one rollout and
    returns its TelemetryRow; gate math itself is untouched."""
    order = sweep_order(split, base)
    res = SweepResult(screening_k=screening_k, final_k=screening_k,
                      escalated=False, screening_verdict=None, aborted=False,
                      abort_condition=None, promote_so_far=False, rows=[],
                      task_order=[], elapsed_wall_s=0)
    cand: dict[str, list[dict]] = {}
    t0 = time.monotonic()

    def record(task_id: str, i: int) -> None:
        row = rollout(task_id, i)
        res.rows.append(row)
        cand.setdefault(task_id, []).append(row.to_json())
        if task_id not in res.task_order:
            res.task_order.append(task_id)

    def stage(planned_k: int, start_i: int) -> None:
        for task_id in order:
            for i in range(start_i + 1, planned_k + 1):
                record(task_id, i)
                reason = reject_certain(split, base, cand, planned_k)
                if reason:
                    res.aborted, res.abort_condition = True, reason
                    print(f"abort: {reason} (remaining rollouts skipped; "
                          "incomplete coverage is already a REJECT)")
                    return

    def gated_verdict() -> str:
        manifest, _ = decide(split, base, cand, baseline_label=baseline_label,
                             candidate_label=candidate, min_k=min_k,
                             effect=effect)
        return manifest["decision"]

    stage(screening_k, 0)
    if not res.aborted:
        res.screening_verdict = gated_verdict()
        # #12 decision 4: only a screening PROMOTE earns the appended pair
        if res.screening_verdict == "PROMOTE" and screening_k < FULL_K:
            res.escalated, res.final_k = True, FULL_K
            stage(FULL_K, screening_k)
        res.promote_so_far = not res.aborted and (
            res.screening_verdict if not res.escalated else gated_verdict()
        ) == "PROMOTE"
    # #12 decision 1: sentinels only on the promotion path
    if res.promote_so_far:
        for task_id in split["sentinel"]:
            for i in range(1, res.final_k + 1):
                record(task_id, i)
    res.elapsed_wall_s = int(time.monotonic() - t0)
    return res


def sweep_order(split: dict, base: dict[str, list[dict]]) -> list[str]:
    """#12 decision 3: held-in first, then held-out, cheapest first within
    each role (ascending baseline duration_p50; tasks without baseline rows
    sort last in their role). Pure scheduling; gate math is order-insensitive."""
    def dur(t):
        rows = base.get(t)
        return (statistics.median(r["duration_s"] for r in rows)
                if rows else float("inf"))
    return sorted(split["held_in"], key=dur) + sorted(split["held_out"], key=dur)


def run_click(cfg: RatchetConfig, *, candidate: str, op: ClickOp,
              motivated_by: str, k: int | None = None,
              min_k: int = 2, effect: float = 0.15,
              runner: OmpRunner | None = None,
              rollback_target: str = "") -> tuple[dict, int]:
    """Execute one full click. Returns (manifest, exit_code 0|1).

    Raises ClickError/EraError/GateDataError (callers map to exit 2) for
    anything that is a data problem rather than a verdict.
    """
    runner = runner or OmpRunner()
    split = json.loads(cfg.split_file.read_text())
    registry = load_registry(cfg.active_baseline)
    baseline_label = registry["label"]

    # Pre-sweep enforcement: invariants 3/7 (motivation) and 5 (one op, by
    # construction of ClickOp), plus era sanity against the BASELINE side
    # before any GPU time is spent.
    check_motivation(split, motivated_by)
    base = load_results(cfg.runs_dir / baseline_label / "results.jsonl")
    check_era(registry, baseline_label=baseline_label, split=split, base=base,
              cand={}, config_root=cfg.root, gate_version=registry["gate_version"])

    run_root = cfg.runs_dir / candidate
    if (run_root / "manifest.json").exists():
        raise GateDataError(f"{run_root / 'manifest.json'} already exists "
                            "(manifests are immutable; pick a new candidate label)")
    run_root.mkdir(parents=True, exist_ok=True)

    # #12 decision 6: refuse mismatched arms before any rollout runs
    if registry.get("concurrency", CONCURRENCY) != CONCURRENCY:
        raise ClickError(
            f"envelope mismatch: baseline recorded concurrency "
            f"{registry['concurrency']} vs runner {CONCURRENCY}; the arms "
            "are incomparable and the gate never runs over incomparable arms")

    # #12 decision 5: one informational line, never blocking
    held_in_base = [base[t] for t in split["held_in"] if base.get(t)]
    if held_in_base and all(_pass_rate(rows) == 1.0 for rows in held_in_base):
        print("note: held-in is already 100% at baseline; no pass gain is "
              "available and this candidate can only win on soft axes")

    surface_op, extra_config, extra_sys = build_op(cfg, runner, op)

    def rollout(task_id: str, i: int):
        row = runner.run_rollout(RolloutSpec(
            task_dir=resolve_task_dir(cfg, task_id), task_id=task_id,
            rollout=i, label=candidate, run_root=run_root, model=cfg.model,
            timeout_s=cfg.timeout_s,
            standing_overlays=cfg.standing_overlays,
            extra_config=extra_config, extra_sys=extra_sys))
        print(f"[{task_id} r{i}] pass={str(row.passed).lower()} "
              f"rc={row.agent_rc} {row.duration_s}s")
        return row

    apply_record = None
    try:
        if surface_op is not None:
            apply_record = surface_op.apply() if op.kind != "config-overlay" \
                else surface_op.apply(standing_overlays=cfg.standing_overlays)
            if apply_record.vacuous:
                raise ClickError(
                    f"vacuous op: the {op.kind} payload matches the current "
                    "state (prior value "
                    f"{apply_record.prior_value!r}); both arms would be "
                    "identical — nothing to test")
        sweep = run_sweep(split, base, rollout, screening_k=k or SCREENING_K,
                          baseline_label=baseline_label, candidate=candidate,
                          min_k=min_k, effect=effect)
    finally:
        if surface_op is not None:
            surface_op.restore()

    op_record = {
        "candidate": candidate, "op": {"kind": op.kind, **op.payload},
        "op_digest12": op.digest12(), "motivated_by": motivated_by,
        "declared_surface": op.kind,
        "registry_admissible": op.kind not in REGISTRY_INADMISSIBLE,
        "apply": None if apply_record is None else {
            "vacuous": apply_record.vacuous,
            "prior_value": apply_record.prior_value,
        },
        "k": sweep.final_k, "min_k": min_k, "effect_threshold": effect,
    }
    (run_root / "op.json").write_text(json.dumps(op_record, indent=1) + "\n")

    cand = load_results(run_root / "results.jsonl")
    check_era(registry, baseline_label=baseline_label, split=split, base=base,
              cand=cand, config_root=cfg.root, gate_version=registry["gate_version"])
    manifest, code = decide(split, base, cand, baseline_label=baseline_label,
                            candidate_label=candidate, min_k=min_k,
                            effect=effect, rollback_target=rollback_target)
    if not sweep.promote_so_far:
        reason = sweep.abort_condition if sweep.aborted \
            else "rejected before sentinels"
        manifest["sentinel_advisory"] = {"skipped": reason}
    gated_n = len(split["held_in"]) + len(split["held_out"])
    sentinel_n = len(split["sentinel"]) if sweep.promote_so_far else 0
    manifest.update({
        "screening_k": sweep.screening_k, "final_k": sweep.final_k,
        "escalated": sweep.escalated,
        "screening_verdict": sweep.screening_verdict,
        "aborted_at": len(sweep.rows) if sweep.aborted else None,
        "abort_condition": sweep.abort_condition,
        "concurrency": CONCURRENCY,
        "sweep_cost": sweep_cost(
            sweep.rows, elapsed_wall_s=sweep.elapsed_wall_s,
            rollouts_planned=(gated_n + sentinel_n) * sweep.final_k,
            aborted=sweep.aborted, task_order=sweep.task_order),
    })
    write_manifest(run_root / "manifest.json", manifest)
    return manifest, code
