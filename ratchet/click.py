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

The append-system-prompt channel may be clicked locally (with a probe on
record) but is registry-inadmissible until a finding-format version bump
(#5 amendment); its op.json is marked accordingly.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ratchet.config import RatchetConfig
from ratchet.kernel.digests import canonical_json
from ratchet.kernel.era import check_era, load_registry
from ratchet.kernel.gate import GateDataError, decide, load_results, write_manifest
from ratchet.runner.base import RolloutSpec
from ratchet.runner.omp import OmpRunner
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

    surface_op, extra_config, extra_sys = build_op(cfg, runner, op)
    k = k or cfg.k
    gated = split["held_in"] + split["held_out"] + split["sentinel"]

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
        for task_id in gated:
            task_dir = resolve_task_dir(cfg, task_id)
            for i in range(1, k + 1):
                row = runner.run_rollout(RolloutSpec(
                    task_dir=task_dir, task_id=task_id, rollout=i,
                    label=candidate, run_root=run_root, model=cfg.model,
                    timeout_s=cfg.timeout_s,
                    standing_overlays=cfg.standing_overlays,
                    extra_config=extra_config, extra_sys=extra_sys))
                print(f"[{task_id} r{i}] pass={str(row.passed).lower()} "
                      f"rc={row.agent_rc} {row.duration_s}s")
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
        "k": k, "min_k": min_k, "effect_threshold": effect,
    }
    (run_root / "op.json").write_text(json.dumps(op_record, indent=1) + "\n")

    cand = load_results(run_root / "results.jsonl")
    check_era(registry, baseline_label=baseline_label, split=split, base=base,
              cand=cand, config_root=cfg.root, gate_version=registry["gate_version"])
    manifest, code = decide(split, base, cand, baseline_label=baseline_label,
                            candidate_label=candidate, min_k=min_k,
                            effect=effect, rollback_target=rollback_target)
    write_manifest(run_root / "manifest.json", manifest)
    return manifest, code
