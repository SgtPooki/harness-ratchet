"""The `ratchet` console command: eight verbs (issue #2, point 4).

Build step 1 implements audit (the CI entry point, with --materialize).
The other verbs exist now so the command shape is stable, and exit 2 with
a pointer to the build-order step that implements them.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import ratchet
from ratchet.kernel.oracle import admit_task
from ratchet.kernel.pack import PackError, materialize_bootstrap, validate_pack

_DEFERRED = {
    "init": 2, "mint": 6, "baseline": 2, "click": 5,
    "export": 7, "replicate": 7, "probe": 2,
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

    for verb in ("init", "mint", "baseline", "click", "export", "replicate", "probe"):
        p = sub.add_parser(verb, help=f"(build step {_DEFERRED[verb]}; not yet implemented)")
        p.set_defaults(fn=_deferred(verb))

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
