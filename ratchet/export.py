"""Assemble a finding directory from a candidate run (issue #5, amended;
issue #2 point 4: the export verb).

Export is deliberately fussy: everything it refuses is a locked rule.
  - append-system-prompt candidates are registry-inadmissible (#5 amendment 3).
  - screening sweeps (final k below 4) are not claim-grade (#12 decision 4).
  - a split spanning more than one pack cannot be expressed in format v1,
    which pins ONE pack digest and vintage; export refuses rather than
    inventing an unratified extension (surface the amendment instead).
  - the model fingerprint and engine envelope come from operator-maintained
    era files (fail closed with instructions), because weights live wherever
    the engine runs and hr-mf-1 must be computed there.

Publishing a finding DISCLOSES its split (the #3 lifecycle); export prints
that consequence loudly.
"""

import datetime
import json
import re
import shutil
from pathlib import Path

from ratchet.config import RatchetConfig
from ratchet.kernel.digests import (canonical_json, finding_digest,
                                    sha256_hex, split_digest)
from ratchet.kernel.era import load_registry, sha256_file
from ratchet.kernel.schemas import validation_errors

REGISTRY_LICENSE_DEFAULT = "MIT"


class ExportError(Exception):
    """A refusal or missing input: exit 2, nothing written."""


def _redact(text: str, home: str) -> str:
    text = text.replace(home, "~")
    return re.sub(r"/(?:private/)?(?:var|tmp)/[^\s\"']*", "<workspace>", text)


def _cap_verify_tail(row: dict) -> dict:
    tail = row.get("verify_tail", "")
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    row["verify_tail"] = lines[-1] if lines else ""
    return row


def _operator_file(era_dir: Path, name: str, purpose: str) -> dict:
    p = era_dir / name
    if not p.is_file():
        raise ExportError(
            f"export: {p} missing. It carries {purpose} and is "
            "operator-maintained; create it and re-run (fail closed by design)")
    return json.loads(p.read_text())


def _pack_of(cfg: RatchetConfig, task_ids: list[str]) -> dict:
    """Resolve the ONE pack every gated task lives in, or refuse."""
    packs = []
    for root in (cfg.bank_pack, cfg.bootstrap_pack):
        mpath = Path(root) / "pack.json"
        if mpath.is_file():
            packs.append((Path(root), json.loads(mpath.read_text())))
    homes = {}
    for t in task_ids:
        for root, manifest in packs:
            if t in manifest.get("tasks", []) or (root / t).is_dir():
                homes.setdefault(t, (root, manifest))
                break
        if t not in homes:
            raise ExportError(f"export: task {t} not found in any configured pack")
    roots = {str(root) for root, _ in homes.values()}
    if len(roots) != 1:
        raise ExportError(
            "export: the split's gated tasks span more than one pack "
            f"({sorted(roots)}); finding format v1 pins ONE pack digest and "
            "vintage (#5 point on claims), so this claim cannot be expressed "
            "without a format amendment. Surface it rather than fudge it.")
    _, manifest = next(iter(homes.values()))
    return {"name": manifest["name"], "digest": manifest["digest"],
            "vintage": manifest["vintage"]}


def _channel_liveness(cfg: RatchetConfig, op_kind: str) -> dict:
    if op_kind in ("config-overlay", "model-param"):
        return {"not_required": f"{op_kind} is a file-level config channel; "
                                "the apply step verifies it mechanically"}
    probes = sorted((cfg.runs_dir / "probes").glob("*-rules.json"))
    if not probes:
        raise ExportError("export: no rules-channel probe on record; run "
                          "`ratchet probe rules` first (#5: findings require "
                          "the liveness evidence)")
    rec = json.loads(probes[-1].read_text())
    return {"method": rec.get("method", "observable-token"),
            "observed": bool(rec.get("observed")),
            "date": rec.get("date", probes[-1].name.split("-rules")[0])}


def _mutation_files(op: dict, out: Path) -> None:
    out.mkdir()
    kind, payload = op["kind"], op["payload"]
    if kind == "rules":
        (out / "rules-append.md").write_text(payload["text"].rstrip() + "\n")
    elif kind == "model-param":
        (out / "model-param.json").write_text(canonical_json(payload))
    elif kind == "config-overlay":
        src = Path(payload["overlay"])
        if not src.is_file():
            raise ExportError(f"export: overlay {src} not found")
        shutil.copy(src, out / src.name)
    else:
        raise ExportError(f"export: op kind {kind!r} is not exportable")


def _load_claim_grade_run(cfg: RatchetConfig, candidate: str,
                          kind: str) -> tuple[dict, dict]:
    """Load and gate-keep the candidate run: every refusal is a locked rule."""
    run_root = cfg.runs_dir / candidate
    manifest_p = run_root / "manifest.json"
    op_p = run_root / "op.json"
    if not manifest_p.is_file() or not op_p.is_file():
        raise ExportError(f"export: {run_root} lacks manifest.json/op.json")
    manifest = json.loads(manifest_p.read_text())
    op_rec = json.loads(op_p.read_text())

    if not op_rec.get("registry_admissible", False):
        raise ExportError("export: this candidate's channel is "
                          "registry-inadmissible until a format version bump "
                          "(#5 amendment 3)")
    final_k = manifest.get("final_k", op_rec.get("k", 0))
    if final_k < 4:
        raise ExportError(
            f"export: final k={final_k} is a screening sweep; screening "
            "verdicts are not claim-grade (#12 decision 4). Re-run the "
            "candidate with --k 4 before exporting")
    want = "PROMOTE" if kind == "improvement" else "REJECT"
    if manifest["decision"] != want:
        raise ExportError(f"export: kind {kind} requires a {want} manifest; "
                          f"this one is {manifest['decision']}")
    return manifest, op_rec


def _claim_block(cfg: RatchetConfig, manifest: dict, registry: dict,
                 split: dict, pack: dict, op_kind: str, final_k: int) -> dict:
    fingerprint = _operator_file(cfg.era_dir, "model-fingerprint.json",
                                 "the hr-mf-1 block (compute weights_digest "
                                 "where the weights live)")
    engine = _operator_file(cfg.era_dir, "engine-envelope.json",
                            "engine name/version, quantization, context "
                            "window, max tokens, and sampling")
    overlays = [{"path": p, "sha256": h}
                for p, h in sorted(registry["config_sha256"].items())]
    return engine, {
        "kit_commit": manifest["rollback_target"] or registry["set_at_commit"],
        "decision": manifest["decision"],
        "improved_axes": manifest["improved_axes"],
        "gate": {"gate_version": manifest["gate_version"],
                 "min_k": manifest["min_k"],
                 "effect_threshold": manifest["effect_threshold"]},
        "k": final_k,
        "baseline_label": manifest["baseline"],
        "candidate_label": manifest["candidate"],
        "pack": pack,
        "split": {"algorithm": "hr-sd-1",
                  "digest": split_digest(split["split_version"],
                                         split["held_in"], split["held_out"],
                                         split["sentinel"]),
                  "split_version": split["split_version"],
                  "roles": {r: split[r] for r in
                            ("held_in", "held_out", "sentinel")}},
        "baseline_harness": {"standing_overlays": overlays},
        "channel_liveness": _channel_liveness(cfg, op_kind),
        "model_fingerprint": fingerprint,
        "runtime_envelope": {**engine.get("runtime_envelope", {}),
                             "omp_model_alias": cfg.model,
                             "timeout_s": cfg.timeout_s,
                             "concurrency": manifest.get("concurrency", 1)},
        "sweep_cost": {"baseline": registry.get("sweep_cost", {}),
                       "candidate": manifest.get("sweep_cost", {})},
    }


def _write_evidence(ev: Path, cfg: RatchetConfig, manifest: dict,
                    run_root: Path, wanted: set[str], home: str) -> None:
    ev.mkdir()
    shutil.copy(run_root / "manifest.json", ev / "manifest.json")
    for label, src in (("candidate", run_root),
                       ("baseline", cfg.runs_dir / manifest["baseline"])):
        rows = [_cap_verify_tail(json.loads(line))
                for line in (src / "results.jsonl").read_text().splitlines()
                if line.strip() and json.loads(line)["task"] in wanted]
        text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
        (ev / f"{label}.results.jsonl").write_text(_redact(text, home))


def export_finding(cfg: RatchetConfig, *, candidate: str, slug: str,
                   kind: str, submitter: str, out_root: Path,
                   target_finding: str | None = None,
                   home: str | None = None) -> Path:
    """Build <out_root>/<slug>-<digest12>/ from runs/<candidate>. Returns the
    finding directory path."""
    home = home or str(Path.home())
    manifest, op_rec = _load_claim_grade_run(cfg, candidate, kind)
    final_k = manifest.get("final_k", op_rec.get("k", 0))

    registry = load_registry(cfg.active_baseline)
    split = json.loads(cfg.split_file.read_text())
    if split["split_version"] != manifest["split_version"]:
        raise ExportError("export: split.json version differs from the "
                          "manifest's; the era moved on")
    all_tasks = split["held_in"] + split["held_out"] + split["sentinel"]
    pack = _pack_of(cfg, all_tasks)

    op = {"kind": op_rec["op"]["kind"],
          "payload": {k: v for k, v in op_rec["op"].items() if k != "kind"}}
    engine, claim = _claim_block(cfg, manifest, registry, split, pack,
                                 op["kind"], final_k)
    doc = {
        "format_version": 1,
        "digest": None,
        "kind": kind,
        "slug": slug,
        "created": datetime.date.today().isoformat(),
        "license": REGISTRY_LICENSE_DEFAULT,
        "submitter_identity": submitter,
        "harness": {"id": "omp",
                    "version": engine.get("harness_version", "unknown"),
                    "surface_digest": sha256_hex(canonical_json(op).encode())},
        "declared_surface": op["kind"],
        "operations": [op],
        "claim": claim,
    }
    if target_finding:
        doc["target_finding"] = target_finding

    # the digest is filled after assembly; a null digest is valid mid-build
    errors = [e for e in validation_errors("finding", doc) if "digest" not in e]
    if errors:
        raise ExportError("export: finding.json fails its own schema:\n  - "
                          + "\n  - ".join(errors))

    tmp = out_root / f".{slug}-building"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        (tmp / "finding.json").write_text(canonical_json(doc))
        _mutation_files(op, tmp / "mutation")
        _write_evidence(tmp / "evidence", cfg, manifest,
                        cfg.runs_dir / candidate, set(all_tasks), home)
        digest = finding_digest(tmp)
        doc["digest"] = digest
        (tmp / "finding.json").write_text(canonical_json(doc))
        final = out_root / f"{slug}-{digest[:12]}"
        if final.exists():
            raise ExportError(f"export: {final} already exists")
        tmp.rename(final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print("NOTE: publishing this finding DISCLOSES split "
          f"v{split['split_version']} (roles and task ids); disclosed splits "
          "stay valid for exact replication but new claims needing held-out "
          "secrecy must move to a fresh split (#3 lifecycle)")
    return final
