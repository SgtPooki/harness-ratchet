"""Assemble a finding directory from a candidate run (issue #5, amended;
issue #2 point 4: the export verb).

Export is deliberately fussy: everything it refuses is a locked rule.
  - append-system-prompt candidates are registry-inadmissible (#5 amendment 3).
  - screening sweeps (final k below 4) are not claim-grade (#12 decision 4).
  - a split may span packs (the #5 amendment 2026-08-26): the claim lists
    one reference per pack, the bank marked private, and any claim
    touching a private pack is transfer-lane only.
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


def _packs_of(cfg: RatchetConfig, task_ids: list[str]) -> list[dict]:
    """Resolve every pack contributing tasks to the split (#5 amendment
    2026-08-26): one reference per pack, the bank marked private (its bytes
    never leave the operator's machine, so digest and vintage are all a
    claim reveals, and any claim touching it is transfer-lane only)."""
    packs = []
    for root in (cfg.bank_pack, cfg.bootstrap_pack):
        mpath = Path(root) / "pack.json"
        if mpath.is_file():
            packs.append((Path(root), json.loads(mpath.read_text())))
    used: dict[str, tuple[Path, dict]] = {}
    for t in task_ids:
        for root, manifest in packs:
            if t in manifest.get("tasks", []) or (root / t).is_dir():
                used[str(root)] = (root, manifest)
                break
        else:
            raise ExportError(f"export: task {t} not found in any configured pack")
    refs = []
    for root, manifest in used.values():
        refs.append({"name": manifest["name"], "digest": manifest["digest"],
                     "vintage": manifest["vintage"],
                     "private": root == Path(cfg.bank_pack)})
    return sorted(refs, key=lambda r: r["name"])


def _private_tasks(cfg: RatchetConfig, task_ids: list[str]) -> list[str]:
    """Tasks living in the bank pack: their ids never leave the machine."""
    return [t for t in task_ids if (Path(cfg.bank_pack) / t).is_dir()]


def _anonymize(cfg: RatchetConfig, task_ids: list[str]) -> dict[str, str]:
    """Stable anonymous ids per operator (#7 amendment, extended to
    findings by the 2026-08-27 amendment on #5): the mapping persists in
    the era dir and only ever grows, so findings and replications stay
    mutually auditable."""
    p = cfg.era_dir / "task-anon-map.json"
    mapping = json.loads(p.read_text()) if p.is_file() else {}
    for t in sorted(task_ids):
        if t not in mapping:
            mapping[t] = f"t{len(mapping) + 1}"
    p.write_text(json.dumps(mapping, indent=1) + "\n")
    return mapping


def _anonymize_text(text: str, mapping: dict[str, str]) -> str:
    """Private-pack task ids never leave the machine."""
    for real, anon in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(real, anon)
    return text


def _anonymize_obj(obj, mapping: dict[str, str]):
    """The same replacement over any JSON value (e.g. sweep_cost with its
    task_order list)."""
    return json.loads(_anonymize_text(json.dumps(obj), mapping))


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
                 split: dict, packs: list[dict], op_kind: str,
                 final_k: int, anon: dict[str, str]) -> dict:
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
        "packs": packs,
        "split": {"algorithm": "hr-sd-1",
                  "digest": split_digest(split["split_version"],
                                         split["held_in"], split["held_out"],
                                         split["sentinel"]),
                  "split_version": split["split_version"],
                  "roles": {r: [anon.get(t, t) for t in split[r]] for r in
                            ("held_in", "held_out", "sentinel")}},
        "baseline_harness": {"standing_overlays": overlays},
        "channel_liveness": _channel_liveness(cfg, op_kind),
        "model_fingerprint": fingerprint,
        "runtime_envelope": {**engine.get("runtime_envelope", {}),
                             "omp_model_alias": cfg.model,
                             "timeout_s": cfg.timeout_s,
                             "concurrency": manifest.get("concurrency", 1)},
        "sweep_cost": {
            "baseline": _anonymize_obj(registry.get("sweep_cost", {}), anon),
            "candidate": _anonymize_obj(manifest.get("sweep_cost", {}), anon),
        },
    }


def _write_evidence(ev: Path, cfg: RatchetConfig, manifest: dict,
                    run_root: Path, wanted: set[str], home: str,
                    anon: dict[str, str]) -> None:
    ev.mkdir()
    (ev / "manifest.json").write_text(_anonymize_text(
        (run_root / "manifest.json").read_text(), anon))
    for label, src in (("candidate", run_root),
                       ("baseline", cfg.runs_dir / manifest["baseline"])):
        rows = [_cap_verify_tail(json.loads(line))
                for line in (src / "results.jsonl").read_text().splitlines()
                if line.strip() and json.loads(line)["task"] in wanted]
        text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
        (ev / f"{label}.results.jsonl").write_text(
            _anonymize_text(_redact(text, home), anon))


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
    packs = _packs_of(cfg, all_tasks)
    anon = _anonymize(cfg, _private_tasks(cfg, all_tasks))

    op = {"kind": op_rec["op"]["kind"],
          "payload": {k: v for k, v in op_rec["op"].items() if k != "kind"}}
    engine, claim = _claim_block(cfg, manifest, registry, split, packs,
                                 op["kind"], final_k, anon)
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
                        cfg.runs_dir / candidate, set(all_tasks), home, anon)
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
