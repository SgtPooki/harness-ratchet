"""Pack I/O: load, validate, and materialize task packs (pack format v1, #3).

Layout: <pack-root>/pack.json plus one <pack-root>/<task-id>/ directory per
task (for the kit's bootstrap pack the root IS the tasks/ directory, which
is what lets materialization satisfy the zero-content-change constraint:
pack.json, task.json, and admission.json are additive wrappers; the task
surfaces — prompt.md, workspace/, verify/, solution/, sabotage/ — stay
byte-identical).

The tasks array in pack.json must be set-equal with the task directories
(array order is display-only). The pack digest is hr-pd-1; pack.json is
excluded from the digest input and carries the digest. Admission records
are non-authoritative attestations: consumers re-execute the audit (the
CLI's audit verb) and fail on mismatch.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ratchet.kernel.digests import pack_digest
from ratchet.kernel.oracle import GRANDFATHERED_SABOTAGE, AdmissionResult
from ratchet.kernel.schemas import validation_errors

SURFACE_NAMES = ("agent", "scoring", "admission")


class PackError(Exception):
    """A pack is structurally invalid or fails its pinned digest."""


@dataclass
class Pack:
    root: Path
    manifest: dict

    @property
    def task_ids(self) -> list[str]:
        return list(self.manifest["tasks"])

    def task_dir(self, task_id: str) -> Path:
        return self.root / task_id


def _task_dirs(root: Path) -> set[str]:
    return {p.name for p in Path(root).iterdir()
            if p.is_dir() and not p.name.startswith(".")
            and p.name != "__pycache__"}


def validate_pack(root: Path) -> list[str]:
    """Structural validation; returns a list of errors (empty = valid)."""
    root = Path(root)
    errs: list[str] = []
    mpath = root / "pack.json"
    if not mpath.is_file():
        return [f"no pack.json at {root}"]
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"pack.json is not valid JSON: {e}"]
    errs += [f"pack.json {e}" for e in validation_errors("pack", manifest)]
    if errs:
        return errs

    declared = set(manifest["tasks"])
    on_disk = _task_dirs(root)
    for missing in sorted(declared - on_disk):
        errs.append(f"pack.json lists task {missing!r} with no directory")
    for stray in sorted(on_disk - declared):
        errs.append(f"task directory {stray!r} not listed in pack.json")

    for task_id in sorted(declared & on_disk):
        tdir = root / task_id
        for name, schema in (("task.json", "task"), ("admission.json", "admission")):
            fpath = tdir / name
            if not fpath.is_file():
                errs.append(f"{task_id}: missing {name}")
                continue
            try:
                doc = json.loads(fpath.read_text(encoding="utf-8"))
            except ValueError as e:
                errs.append(f"{task_id}/{name}: not valid JSON: {e}")
                continue
            errs += [f"{task_id}/{name} {e}" for e in validation_errors(schema, doc)]
            key = "id" if schema == "task" else "task"
            if isinstance(doc, dict) and doc.get(key) != task_id:
                errs.append(f"{task_id}/{name}: {key} is {doc.get(key)!r}")
            if schema == "admission" and isinstance(doc, dict):
                errs += _sabotage_consistency(task_id, tdir, doc)

    want = manifest["digest"]
    have = pack_digest(root)
    if have != want:
        errs.append(f"pack digest mismatch: pack.json pins {want}, content is {have}")
    return errs


def _sabotage_consistency(task_id: str, tdir: Path, admission: dict) -> list[str]:
    """The grandfather allowlist is kernel-side; a pack cannot self-declare it."""
    errs = []
    has_dir = (tdir / "sabotage").is_dir()
    declared = admission.get("sabotage")
    if has_dir and declared != "present":
        errs.append(f"{task_id}: sabotage/ exists but admission.json says {declared!r}")
    if not has_dir:
        if declared == "present":
            errs.append(f"{task_id}: admission.json claims sabotage but sabotage/ is missing")
        elif task_id not in GRANDFATHERED_SABOTAGE:
            errs.append(f"{task_id}: sabotage absent and not on the kernel grandfather allowlist")
    return errs


def load_pack(root: Path) -> Pack:
    """Load and fully validate a pack; raises PackError on any problem."""
    errs = validate_pack(root)
    if errs:
        raise PackError(f"invalid pack at {root}:\n  - " + "\n  - ".join(errs))
    manifest = json.loads((Path(root) / "pack.json").read_text(encoding="utf-8"))
    return Pack(root=Path(root), manifest=manifest)


def infer_requires(task_dir: Path) -> list[str]:
    """Derive the requires list from the verifier entrypoint's actual tools.

    Vocabulary v1 (issue #3 amendment): python3 | uv | node | bash | git.
    The executable verifier stays authoritative; requires only enables
    fail-fast preflight.
    """
    task_dir = Path(task_dir)
    if (task_dir / "verify" / "verify.mjs").is_file():
        return ["node"]
    py = task_dir / "verify" / "verify.py"
    if py.is_file():
        req = ["python3"]
        src = py.read_text(encoding="utf-8")
        if '"uv"' in src or "'uv'" in src:
            req.append("uv")
        if '"bash"' in src or "'bash'" in src:
            req.append("bash")
        return req
    raise PackError(f"no verifier found in {task_dir}")


def materialize_bootstrap(root: Path, *, name: str, vintage_number: int,
                          vintage_date: str, minted_date: str,
                          admissions: dict[str, AdmissionResult],
                          miner_name: str, miner_version: str,
                          force: bool = False) -> dict:
    """Write the additive wrapper files that make a tasks/ directory a pack.

    Writes <root>/<id>/task.json and admission.json for every task in
    admissions, then <root>/pack.json pinning the hr-pd-1 digest. Never
    touches task surfaces. Every admission must have passed (ok=True).
    Returns the pack manifest.
    """
    root = Path(root)
    mpath = root / "pack.json"
    if mpath.exists() and not force:
        raise PackError(f"{mpath} already exists (pass force to re-materialize; "
                        "any content change is a new vintage)")
    bad = sorted(t for t, a in admissions.items() if not a.ok)
    if bad:
        raise PackError(f"refusing to materialize with failed admissions: {bad}")
    on_disk = _task_dirs(root)
    if set(admissions) != on_disk:
        raise PackError(f"admissions {sorted(admissions)} != task dirs {sorted(on_disk)}")

    for task_id, adm in sorted(admissions.items()):
        tdir = root / task_id
        task_doc = {
            "id": task_id,
            "requires": infer_requires(tdir),
            "surfaces": {s: {"encryption": "plaintext"} for s in SURFACE_NAMES},
        }
        admission_doc = {
            "task": task_id,
            "oracle": {
                "unmodified_fails": adm.unmodified_fails,
                "solution_passes": adm.solution_passes,
                "sabotage_fails": adm.sabotage_fails,
            },
            "sabotage": adm.sabotage,
            "mutants": None,
            "stability_runs": None,
            "miner": {"name": miner_name, "version": miner_version},
            "minted": minted_date,
            "source": None,
        }
        (tdir / "task.json").write_text(json.dumps(task_doc, indent=1) + "\n")
        (tdir / "admission.json").write_text(json.dumps(admission_doc, indent=1) + "\n")

    manifest = {
        "format_version": 1,
        "name": name,
        "vintage": {"number": vintage_number, "date": vintage_date},
        "digest_algorithm": "hr-pd-1",
        "digest": pack_digest(root),
        "tasks": sorted(admissions),
    }
    mpath.write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest
