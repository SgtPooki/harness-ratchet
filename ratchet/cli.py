"""The `ratchet` console command: eight verbs (issue #2, point 4).

Implemented: audit (step 1), init, baseline sweep / set-active, probe
(step 2). Still deferred: click (step 5), mint (step 6), export and
replicate (step 7) — they exit 2 with a pointer to their build-order step.
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path

import ratchet
from ratchet.click import ClickError, ClickOp, run_click
from ratchet.config import ConfigError, load_config
from ratchet.kernel.era import EraError, build_registry
from ratchet.kernel.gate import GateDataError
from ratchet.kernel.oracle import admit_task
from ratchet.kernel.pack import PackError, materialize_bootstrap, validate_pack
from ratchet.runner.ops import OpError

_DEFERRED = {"mint": 6, "export": 7, "replicate": 7}

SPLIT_TEMPLATE = {
    "_comment": ("Pinned task split for this bank's era. Roles: held_in "
                 "(visible to proposers), held_out (non-regression floor, "
                 "never shown to proposers), sentinel (drift canary, never "
                 "optimized against). Bump split_version on any change and "
                 "record a new baseline."),
    "split_version": 0,
    "held_in": [],
    "held_out": [],
    "sentinel": [],
}


def cmd_audit(args) -> int:
    """Oracle re-audit of a pack (or a plain tasks directory, pre-pack)."""
    root = Path(args.pack)
    if not root.is_dir():
        print(f"audit: {root} is not a directory", file=sys.stderr)
        return 2
    task_dirs = sorted(p for p in root.iterdir() if p.is_dir()
                       and not p.name.startswith(".") and p.name != "__pycache__")
    if not task_dirs:
        print(f"audit: no task directories under {root}", file=sys.stderr)
        return 2

    fail = False
    admissions = {}
    for tdir in task_dirs:
        res = admit_task(tdir)
        admissions[res.task_id] = res
        if res.ok:
            print(f"oracle ok   [{res.task_id}]"
                  + ("  (sabotage ok)" if res.sabotage == "present" else ""))
        else:
            fail = True
            for reason in res.reasons:
                print(f"ORACLE FAIL [{res.task_id}]: {reason}")

    has_manifest = (root / "pack.json").is_file()
    if has_manifest and not args.materialize:
        # A published pack must also match its own metadata: structure,
        # digest, and admission records vs the re-executed audit.
        errs = validate_pack(root)
        for task_id, adm in sorted(admissions.items()):
            apath = root / task_id / "admission.json"
            if not apath.is_file():
                continue
            rec = json.loads(apath.read_text(encoding="utf-8"))
            got = {"unmodified_fails": adm.unmodified_fails,
                   "solution_passes": adm.solution_passes,
                   "sabotage_fails": adm.sabotage_fails}
            if rec.get("oracle") != got:
                errs.append(f"{task_id}: admission.json oracle triple "
                            f"{rec.get('oracle')} != re-executed {got}")
            if rec.get("sabotage") != adm.sabotage:
                errs.append(f"{task_id}: admission.json sabotage {rec.get('sabotage')!r}"
                            f" != audited {adm.sabotage!r}")
        for e in errs:
            print(f"PACK FAIL: {e}")
            fail = True

    if args.materialize:
        if fail:
            print("audit: refusing to materialize a pack with oracle failures",
                  file=sys.stderr)
            return 1
        today = datetime.date.today().isoformat()
        try:
            manifest = materialize_bootstrap(
                root, name=args.name, vintage_number=args.vintage,
                vintage_date=today, minted_date=today, admissions=admissions,
                miner_name="ratchet-audit", miner_version=ratchet.__version__,
                force=args.force,
            )
        except PackError as e:
            print(f"audit: {e}", file=sys.stderr)
            return 2
        print(f"materialized pack {manifest['name']!r} vintage "
              f"{manifest['vintage']['number']} ({manifest['vintage']['date']}) "
              f"digest {manifest['digest']}")
        errs = validate_pack(root)
        if errs:
            for e in errs:
                print(f"PACK FAIL: {e}")
            return 1

    return 1 if fail else 0


def _kit_overlay_sources() -> list:
    """The kit's standing overlays, for migration into a bank at init.

    Installed wheels carry them as package data (ratchet/data/overlays,
    force-included from mutations/); editable/dev checkouts fall back to
    the repo's mutations/ directory.
    """
    pkg = resources.files("ratchet") / "data" / "overlays"
    if pkg.is_dir():
        return sorted(p for p in pkg.iterdir() if p.name.endswith(".yml"))
    repo = Path(ratchet.__file__).resolve().parent.parent / "mutations"
    if repo.is_dir():
        return sorted(repo.glob("*.yml"))
    return []


def cmd_init(args) -> int:
    """Scaffold a personal bank: dirs, era state, ratchet.toml (issue #2 pt 3)."""
    root = Path(args.path)
    toml_path = root / "ratchet.toml"
    if toml_path.exists():
        print(f"init: {toml_path} already exists", file=sys.stderr)
        return 2
    for d in ("tasks", "runs", "era", "overlays"):
        (root / d).mkdir(parents=True, exist_ok=True)

    overlay_rels = []
    for src in _kit_overlay_sources():
        dst = root / "overlays" / src.name
        dst.write_bytes(src.read_bytes())
        overlay_rels.append(f"overlays/{src.name}")

    (root / "era" / "split.json").write_text(json.dumps(SPLIT_TEMPLATE, indent=1) + "\n")
    (root / ".gitignore").write_text("/runs/\n")

    bootstrap = args.bootstrap_pack
    if bootstrap is None:
        kit_tasks = Path(ratchet.__file__).resolve().parent.parent / "tasks"
        bootstrap = str(kit_tasks) if (kit_tasks / "pack.json").is_file() \
            else "CHANGE-ME/path/to/bootstrap-pack"
    overlay_lines = "".join(f'  "{p}",\n' for p in overlay_rels)
    toml_path.write_text(f'''# harness-ratchet operator config (v1 schema, issue #2 point 3).
# Relative paths resolve against this file's directory.

[paths]
runs_dir = "runs"   # local rollout evidence; gitignored
era_dir = "era"     # split.json + ACTIVE_BASELINE: the comparison era

[packs]
bootstrap = "{bootstrap}"
bank = "tasks"      # this bank's own pack root; starts empty

[runner]
harness = "omp"
model = "{args.model}"
timeout_s = 900
k = 2

[overlays.standing]
# Applied identically to BOTH arms of every comparison; never a mutation.
paths = [
{overlay_lines}]
''')
    print(f"bank scaffolded at {root}")
    print(f"  config:   {toml_path}")
    print(f"  overlays: {len(overlay_rels)} standing overlay(s) migrated from the kit")
    print("  era:      split.json v0 (empty; roles fill as tasks are minted)")
    return 0


def _load_cfg(args):
    return load_config(getattr(args, "config", None))


def _select_tasks(pack_root: Path, selector: list[str], split_file: Path) -> list[str]:
    on_disk = sorted(p.name for p in pack_root.iterdir()
                     if p.is_dir() and not p.name.startswith(".")
                     and p.name != "__pycache__")
    if selector == ["all"]:
        return on_disk
    if selector == ["held-in"]:
        if not split_file.is_file():
            raise ConfigError(f"held-in selection needs {split_file}")
        held = json.loads(split_file.read_text())["held_in"]
        missing = sorted(set(held) - set(on_disk))
        if missing:
            raise ConfigError(f"held_in tasks not in pack: {missing}")
        return held
    missing = sorted(set(selector) - set(on_disk))
    if missing:
        raise ConfigError(f"tasks not in pack {pack_root}: {missing}")
    return selector


def cmd_baseline_sweep(args) -> int:
    from ratchet.runner.base import RolloutSpec
    from ratchet.runner.omp import OmpRunner

    cfg = _load_cfg(args)
    pack_root = Path(args.pack) if args.pack else cfg.bootstrap_pack
    tasks = _select_tasks(pack_root, args.tasks, cfg.split_file)
    k = args.k or cfg.k
    model = args.model or cfg.model
    timeout_s = args.timeout_s or cfg.timeout_s
    run_root = cfg.runs_dir / args.label
    run_root.mkdir(parents=True, exist_ok=True)
    runner = OmpRunner()
    for task_id in tasks:
        for i in range(1, k + 1):
            row = runner.run_rollout(RolloutSpec(
                task_dir=pack_root / task_id, task_id=task_id, rollout=i,
                label=args.label, run_root=run_root, model=model,
                timeout_s=timeout_s,
                standing_overlays=cfg.standing_overlays,
                extra_config=Path(args.extra_config) if args.extra_config else None,
                extra_sys=args.extra_sys,
            ))
            print(f"[{task_id} r{i}] pass={str(row.passed).lower()} "
                  f"rc={row.agent_rc} {row.duration_s}s")
    print(f"results: {run_root / 'results.jsonl'}")
    return 0


def cmd_baseline_set_active(args) -> int:
    from ratchet.kernel.gate import load_results

    cfg = _load_cfg(args)
    results = load_results(cfg.runs_dir / args.label / "results.jsonl")
    split = json.loads(cfg.split_file.read_text())
    if args.configs is not None:
        configs = [c for c in args.configs.split(",") if c]
    else:
        configs = [str(p.relative_to(cfg.root)) for p in cfg.standing_overlays]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cfg.root,
                            capture_output=True, text=True).stdout.strip()
    reg = build_registry(label=args.label, results=results, split=split,
                         configs=configs, config_root=cfg.root,
                         set_at_commit=commit, ts=int(time.time()))
    cfg.era_dir.mkdir(parents=True, exist_ok=True)
    cfg.active_baseline.write_text(json.dumps(reg, indent=1) + "\n")
    print(f"active baseline -> {args.label} (split v{split['split_version']}, "
          f"gate v{reg['gate_version']}, model {reg['model']})")
    print(f"registry: {cfg.active_baseline} — commit it with the baseline's ledger entry")
    return 0


def cmd_probe(args) -> int:
    from ratchet.runner.omp import OmpRunner
    from ratchet.runner.probe import probe_channel

    cfg = _load_cfg(args)
    runner = OmpRunner()
    result = probe_channel(runner, args.channel, model=cfg.model,
                           timeout_s=cfg.timeout_s,
                           out_dir=cfg.runs_dir / "probes",
                           standing_overlays=cfg.standing_overlays)
    verdict = "LIVE" if result.observed else "DEAD"
    print(f"channel {args.channel}: {verdict} (token {result.token}, "
          f"agent rc={result.rc}, record in {cfg.runs_dir / 'probes'})")
    return 0 if result.observed else 1


def _parse_value(raw: str):
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def cmd_click(args) -> int:
    cfg = _load_cfg(args)
    payloads = {
        "config-overlay": {"overlay": args.overlay},
        "model-param": {"omp_model_alias": args.selector.split(":")[0] if args.selector else None,
                        "yaml_id": args.selector.split(":")[1] if args.selector and ":" in args.selector else None,
                        "key": args.key,
                        "value": _parse_value(args.value) if args.value is not None else None},
        "rules": {"text": args.text},
        "append-system-prompt": {"text": args.text},
    }
    payload = payloads[args.op]
    missing = [k for k, v in payload.items() if v is None]
    if missing:
        raise ClickError(f"op {args.op} needs {missing} "
                         "(--overlay | --selector alias:yaml_id --key --value | --text)")
    stray = {"config-overlay": args.selector or args.key or args.value or args.text,
             "model-param": args.overlay or args.text,
             "rules": args.overlay or args.selector or args.key or args.value,
             "append-system-prompt": args.overlay or args.selector or args.key or args.value}
    if stray[args.op]:
        raise ClickError(f"op {args.op} got flags belonging to a different op "
                         "(one mutation, one surface: invariant 5)")

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cfg.root,
                            capture_output=True, text=True).stdout.strip()
    manifest, code = run_click(
        cfg, candidate=args.candidate, op=ClickOp(kind=args.op, payload=payload),
        motivated_by=args.motivated_by, k=args.k, min_k=args.min_k,
        effect=args.effect, rollback_target=commit)
    print(f"=== GATE: {manifest['decision']} ({args.candidate} vs {manifest['baseline']})")
    for r in manifest["reasons"]:
        print(f"  - {r}")
    for a in manifest["improved_axes"]:
        print(f"  + improved: {a}")
    if manifest["decision"] == "PROMOTE":
        print("promote bookkeeping: make the mutation standing (config-overlay -> "
              "[overlays.standing]; model-param/rules -> apply permanently), then "
              "record a new baseline and `baseline set-active` it")
    print(f"manifest: {cfg.runs_dir / args.candidate / 'manifest.json'}")
    return code


def _deferred(verb: str):
    def run(_args) -> int:
        print(f"ratchet {verb}: not implemented yet — arrives in build step "
              f"{_DEFERRED[verb]} of the runner-rewrite build order (issue #2)",
              file=sys.stderr)
        return 2
    return run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ratchet",
        description="CI for your harness: mechanical evidence gates around a frozen local model",
    )
    ap.add_argument("--version", action="version",
                    version=f"ratchet {ratchet.__version__} (gate v4)")
    sub = ap.add_subparsers(dest="verb", required=True)

    p_audit = sub.add_parser("audit", help="oracle re-audit of a pack (CI entry point)")
    p_audit.add_argument("--pack", default="tasks", help="pack root (default: tasks)")
    p_audit.add_argument("--materialize", action="store_true",
                         help="write pack.json/task.json/admission.json wrappers")
    p_audit.add_argument("--name", default="bootstrap", help="pack name (with --materialize)")
    p_audit.add_argument("--vintage", type=int, default=1,
                         help="vintage number (with --materialize)")
    p_audit.add_argument("--force", action="store_true",
                         help="re-materialize over an existing pack.json")
    p_audit.set_defaults(fn=cmd_audit)

    p_init = sub.add_parser("init", help="scaffold a personal bank (dirs, era state, ratchet.toml)")
    p_init.add_argument("path", help="bank root to create")
    p_init.add_argument("--bootstrap-pack", default=None,
                        help="path to the bootstrap pack (default: autodetect the kit's tasks/)")
    p_init.add_argument("--model", default="vllm/homelab-default",
                        help="omp model alias written into ratchet.toml")
    p_init.set_defaults(fn=cmd_init)

    p_base = sub.add_parser("baseline", help="record and pin comparison baselines")
    base_sub = p_base.add_subparsers(dest="subverb", required=True)
    p_sweep = base_sub.add_parser("sweep", help="run rollouts and append results.jsonl")
    p_sweep.add_argument("label")
    p_sweep.add_argument("--tasks", nargs="+", default=["all"],
                         help="task ids, or 'all' / 'held-in' (default: all)")
    p_sweep.add_argument("--k", type=int, default=None, help="rollouts per task (default: config)")
    p_sweep.add_argument("--pack", default=None, help="pack root (default: config bootstrap)")
    p_sweep.add_argument("--model", default=None, help="model alias override (default: config)")
    p_sweep.add_argument("--timeout-s", type=int, default=None,
                         help="rollout timeout override (default: config)")
    p_sweep.add_argument("--extra-config", default=None,
                         help="candidate omp --config overlay (the mutation artifact)")
    p_sweep.add_argument("--extra-sys", default=None,
                         help="trust-header-wrapped --append-system-prompt text (loop-only channel)")
    p_sweep.add_argument("--config", default=None, help="ratchet.toml path")
    p_sweep.set_defaults(fn=cmd_baseline_sweep)
    p_setactive = base_sub.add_parser("set-active", help="pin the era's comparison baseline")
    p_setactive.add_argument("label")
    p_setactive.add_argument("--configs", default=None,
                             help="comma-separated overlay paths to pin (default: config standing overlays)")
    p_setactive.add_argument("--config", default=None, help="ratchet.toml path")
    p_setactive.set_defaults(fn=cmd_baseline_set_active)

    p_click = sub.add_parser(
        "click", help="one mutation cycle: mutate -> rollouts -> gate -> restore")
    p_click.add_argument("candidate", help="candidate run label (manifest is immutable per label)")
    p_click.add_argument("--op", required=True,
                         choices=["config-overlay", "model-param", "rules",
                                  "append-system-prompt"],
                         help="the ONE surface operation (invariant 5)")
    p_click.add_argument("--motivated-by", required=True, metavar="TASK",
                         help="the failure-pattern task motivating this mutation "
                              "(sentinel: invalid per invariant 3; held-out: "
                              "illegal per invariant 7)")
    p_click.add_argument("--overlay", default=None, help="config-overlay: overlay file")
    p_click.add_argument("--selector", default=None, metavar="ALIAS:YAML_ID",
                         help="model-param: omp_model_alias:yaml_id")
    p_click.add_argument("--key", default=None, help="model-param: key to set")
    p_click.add_argument("--value", default=None, help="model-param: payload value")
    p_click.add_argument("--text", default=None, help="rules / append-system-prompt: block text")
    p_click.add_argument("--k", type=int, default=None, help="rollouts per task (default: config)")
    p_click.add_argument("--min-k", type=int, default=2)
    p_click.add_argument("--effect", type=float, default=0.15)
    p_click.add_argument("--config", default=None, help="ratchet.toml path")
    p_click.set_defaults(fn=cmd_click)

    p_probe = sub.add_parser("probe", help="channel liveness: observable-token test")
    p_probe.add_argument("channel", choices=["rules", "append-system-prompt"])
    p_probe.add_argument("--config", default=None, help="ratchet.toml path")
    p_probe.set_defaults(fn=cmd_probe)

    for verb in ("mint", "export", "replicate"):
        p = sub.add_parser(verb, help=f"(build step {_DEFERRED[verb]}; not yet implemented)")
        p.set_defaults(fn=_deferred(verb))

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ConfigError, EraError, GateDataError, ClickError, OpError) as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
