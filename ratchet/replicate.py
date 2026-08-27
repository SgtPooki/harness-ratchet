"""The replicate verb: re-test a published finding (issue #7, amended).

Outcomes, four values in three classes, exactly as locked:
  replicated | refuted   mechanical gate verdicts; the only tally values.
  vacuous                the op changed nothing (derived strictly from the
                         apply record's vacuous flag; the gate is skipped).
  environment-mismatch   preconditions or calibration failed; never a verdict.

Lanes: EXACT needs a byte-identical weights fingerprint and a matching
inference envelope, verified before any rollouts; anything else is a
LOCAL-TRANSFER by definition (the replicator's own era baseline vs
candidate-with-op under their recorded gate params). v1 implements the
transfer lane's run path by reusing run_click (same trap-restore, same
era checks, same manifest bookkeeping); the exact lane's both-arm re-run
under the claim's pinned pack is stage-A checked here and refused with a
clear pointer until the registry hosts packs to pin against.

Broadcast: the manifest is always written locally; v1 submission is a PR
to the registry repo (printed instructions, zero infrastructure).
"""

import datetime
import json
import shutil
from pathlib import Path

from ratchet.click import ClickError, ClickOp, run_click
from ratchet.config import RatchetConfig
from ratchet.kernel.digests import canonical_json, finding_digest
from ratchet.kernel.era import load_registry
from ratchet.kernel.gate import load_results
from ratchet.kernel.schemas import validation_errors


class ReplicateError(Exception):
    """Bad finding or usage: exit 2, no manifest (distinct from an
    environment-mismatch outcome, which IS a manifest)."""


def load_finding(path: Path) -> dict:
    """Load and verify a finding directory: schema, digest, one-op."""
    path = Path(path)
    fp = path / "finding.json"
    if not fp.is_file():
        raise ReplicateError(f"replicate: {fp} missing")
    doc = json.loads(fp.read_text())
    errors = validation_errors("finding", doc)
    if errors:
        raise ReplicateError("replicate: finding fails its schema:\n  - "
                             + "\n  - ".join(errors))
    if doc["digest"] != finding_digest(path):
        raise ReplicateError("replicate: finding digest does not recompute; "
                             "the directory was modified after assembly")
    if doc["operations"][0]["kind"] != doc["declared_surface"]:
        raise ReplicateError("replicate: operation kind differs from "
                             "declared_surface (one-op invariant)")
    return doc


def determine_lane(finding: dict, replicator_fp: dict,
                   replicator_env: dict) -> tuple[str, list[str]]:
    """EXACT only with byte-identical weights and matching inference
    envelope; different weights is a LOCAL-TRANSFER by definition, not a
    failed exact. Returns (lane, reasons-the-exact-lane-was-unavailable)."""
    reasons = []
    claim = finding["claim"]
    if replicator_fp.get("weights") != claim["model_fingerprint"]["weights"]:
        reasons.append("weights fingerprint differs")
    claim_env = claim["runtime_envelope"]
    for field in ("engine", "quantization", "context_window", "max_tokens",
                  "sampling", "concurrency"):
        if replicator_env.get(field) != claim_env.get(field):
            reasons.append(f"envelope field {field} differs")
    return ("exact" if not reasons else "local-transfer"), reasons


def stage_a_exact(finding: dict, cfg: RatchetConfig) -> list[str]:
    """Exact-lane pre-run pin checks (#7 point 2). Any failure is an
    environment-mismatch outcome, never a verdict."""
    reasons = []
    for ref in finding["claim"]["packs"]:
        if ref.get("private"):
            reasons.append(f"pack {ref['name']} is private; its bytes are "
                           "unobtainable outside the submitter's machine")
            continue
        matched = False
        for root in (cfg.bootstrap_pack, cfg.bank_pack):
            mp = Path(root) / "pack.json"
            if mp.is_file():
                m = json.loads(mp.read_text())
                if m.get("digest") == ref["digest"]:
                    matched = True
                    break
        if not matched:
            reasons.append(f"pack {ref['name']} digest {ref['digest'][:12]} "
                           "not present locally")
    registry = load_registry(cfg.active_baseline)
    if registry["gate_version"] != finding["claim"]["gate"]["gate_version"]:
        reasons.append("gate_version differs")
    claim_overlays = {o["path"]: o["sha256"] for o in
                      finding["claim"]["baseline_harness"]["standing_overlays"]}
    if claim_overlays != registry.get("config_sha256", {}):
        reasons.append("standing-overlay digests differ")
    return reasons


def _difficulty_band(rows: list[dict]) -> str:
    return "passing" if all(r["pass"] for r in rows) else "headroom"


def _anonymize(cfg: RatchetConfig, task_ids: list[str]) -> dict[str, str]:
    """Stable anonymous ids per replicator+bank (#7 amendment): the mapping
    persists in the era dir and only ever grows."""
    p = cfg.era_dir / "task-anon-map.json"
    mapping = json.loads(p.read_text()) if p.is_file() else {}
    for t in sorted(task_ids):
        if t not in mapping:
            mapping[t] = f"t{len(mapping) + 1}"
    p.write_text(json.dumps(mapping, indent=1) + "\n")
    return mapping


def _replicator_block(cfg: RatchetConfig) -> dict:
    return {
        "model_fingerprint": json.loads(
            (cfg.era_dir / "model-fingerprint.json").read_text()),
        "runtime_envelope": json.loads(
            (cfg.era_dir / "engine-envelope.json").read_text()
        ).get("runtime_envelope", {}),
    }


def _seal_replication(out_root: Path, doc: dict, finding_digest12: str,
                      write_extras=None) -> Path:
    """Write replication.json (digest null), any extras, then the hr-fd-1
    self-referenced digest, and rename to the final digest-named dir."""
    rdir = out_root / f".repl-{finding_digest12}-building"
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)
    try:
        (rdir / "replication.json").write_text(canonical_json(doc))
        if write_extras is not None:
            write_extras(rdir)
        digest = finding_digest(rdir, meta_name="replication.json")
        doc["digest"] = digest
        (rdir / "replication.json").write_text(canonical_json(doc))
        final = out_root / f"{finding_digest12}-repl-{digest[:12]}"
        if final.exists():
            raise ReplicateError(f"replicate: {final} already exists")
        rdir.rename(final)
        return final
    except Exception:
        shutil.rmtree(rdir, ignore_errors=True)
        raise


def _private_tasks(cfg: RatchetConfig, task_ids: list[str]) -> list[str]:
    """Tasks living in the bank pack: their ids never leave the machine."""
    return [t for t in task_ids if (Path(cfg.bank_pack) / t).is_dir()]


def replicate_transfer(cfg: RatchetConfig, finding: dict, *,
                       submitter: str, out_root: Path,
                       k: int | None = None,
                       runner=None) -> tuple[Path, str]:
    """LOCAL-TRANSFER lane: the finding's op through the replicator's own
    loop, reusing run_click (same trap-restore, era checks, and manifest
    bookkeeping; motivated_by is None because the op came from a published
    finding). Returns (replication_dir, outcome)."""
    op_doc = finding["operations"][0]
    op = ClickOp(kind=op_doc["kind"], payload=dict(op_doc["payload"]))
    split = json.loads(cfg.split_file.read_text())
    if not split.get("held_in"):
        raise ReplicateError("replicate: the local split has no held_in "
                             "tasks; record an era first")
    label = f"repl-{finding['digest'][:12]}"
    k = k or max(finding["claim"]["k"], 4)

    outcome, reasons, op_application = None, [], {"vacuous": False}
    manifest = None
    try:
        manifest, _code = run_click(
            cfg, candidate=label, op=op, motivated_by=None,
            replication_of=finding["digest"], k=k,
            min_k=finding["claim"]["gate"]["min_k"],
            effect=finding["claim"]["gate"]["effect_threshold"],
            runner=runner)
        # replicated means the replicator's gate agrees with the CLAIM: a
        # PROMOTE replicates an improvement, and a REJECT replicates a
        # negative result (both verdicts are mechanical either way)
        agrees = manifest["decision"] == finding["claim"]["decision"]
        outcome = "replicated" if agrees else "refuted"
    except ClickError as e:
        if "vacuous" not in str(e):
            raise ReplicateError(f"replicate: {e}") from e
        # the four-outcome rule: vacuous derives STRICTLY from the apply
        # flag; the gate is skipped, nothing tallies
        outcome = "vacuous"
        op_application = {"vacuous": True}
        reasons = [str(e)]

    registry = load_registry(cfg.active_baseline)
    base = load_results(cfg.runs_dir / registry["label"] / "results.jsonl")
    gated = split["held_in"] + split["held_out"]
    anon = _anonymize(cfg, _private_tasks(cfg, gated))
    bands = {anon[t]: {"band": _difficulty_band(base.get(t, []))}
             for t in anon if base.get(t)}

    doc = {
        "format_version": 1,
        "digest": None,
        "target_finding": finding["digest"],
        "lane": "local-transfer",
        "outcome": outcome,
        "reasons": reasons,
        "created": datetime.date.today().isoformat(),
        "submitter_identity": submitter,
        "replicator": _replicator_block(cfg),
        "gate": finding["claim"]["gate"],
        "k": k,
        "op_application": op_application,
        "task_anonymization": bands,
    }
    errors = [e for e in validation_errors("replication", doc)
              if "digest" not in e]
    if errors:
        raise ReplicateError("replicate: manifest fails its schema:\n  - "
                             + "\n  - ".join(errors))

    def extras(rdir: Path) -> None:
        if manifest is not None:
            _write_replication_evidence(rdir / "evidence", cfg, manifest,
                                        cfg.runs_dir / label, split, anon)

    final = _seal_replication(out_root, doc, finding["digest"][:12], extras)
    return final, outcome


def _write_replication_evidence(ev: Path, cfg: RatchetConfig, manifest: dict,
                                run_root: Path, split: dict,
                                anon: dict[str, str]) -> None:
    """The replication's own gate manifest and redacted rows, with
    private-bank task ids anonymized before anything leaves the machine."""
    from ratchet.export import _cap_verify_tail, _redact

    ev.mkdir()
    home = str(Path.home())
    wanted = set(split["held_in"] + split["held_out"] + split["sentinel"])
    (ev / "manifest.json").write_text(
        _anonymize_text(json.dumps(manifest, indent=1), anon))
    registry = load_registry(cfg.active_baseline)
    for label, src in (("candidate", run_root),
                       ("baseline", cfg.runs_dir / registry["label"])):
        rows = [_cap_verify_tail(json.loads(line))
                for line in (src / "results.jsonl").read_text().splitlines()
                if line.strip() and json.loads(line)["task"] in wanted]
        text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
        (ev / f"{label}.results.jsonl").write_text(
            _anonymize_text(_redact(text, home), anon))


def _anonymize_text(text: str, mapping: dict[str, str]) -> str:
    """Private-bank task ids never leave the machine (#7 amendment)."""
    for real, anon in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(real, anon)
    return text


def write_mismatch(cfg: RatchetConfig, finding: dict, *, submitter: str,
                   out_root: Path, reasons: list[str]) -> Path:
    """An environment-mismatch manifest: recorded, broadcast, never
    tallied. No rollouts ran; there is no evidence directory."""
    doc = {
        "format_version": 1,
        "digest": None,
        "target_finding": finding["digest"],
        "lane": "exact",
        "outcome": "environment-mismatch",
        "reasons": reasons,
        "created": datetime.date.today().isoformat(),
        "submitter_identity": submitter,
        "replicator": _replicator_block(cfg),
        "gate": finding["claim"]["gate"],
        "k": finding["claim"]["k"],
        "op_application": {"vacuous": False},
    }
    return _seal_replication(out_root, doc, finding["digest"][:12])
